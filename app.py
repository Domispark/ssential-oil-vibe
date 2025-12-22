import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import difflib
import re # 引入正規表達式套件，用於精準抓取

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (強力修正版)")

# --- 步驟 0: 建立正確的產品資料庫 ---
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級",
    "胡椒薄荷-一般",
    "綠薄荷精油",
    "白雲杉精油",
    "甜橙精油",
    "薰衣草精油-高地",
    "茶樹精油"
]

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

@st.cache_data(ttl=600)
def get_working_models():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        models.sort(key=lambda x: 'flash' not in x.lower())
        return models
    except Exception:
        return ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

def save_to_sheet(data_list):
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_list.append(now_str)
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
        sheet.append_row(data_list)
        return True
    except Exception as e:
        st.error(f"寫入表格失敗：{e}")
        return False

# --- 步驟 1: 建立檢查邏輯函式 ---
def check_product_name(ai_input_name):
    if ai_input_name in KNOWN_PRODUCTS:
        return True, None
    matches = difflib.get_close_matches(ai_input_name, KNOWN_PRODUCTS, n=1, cutoff=0.4)
    if matches:
        return False, matches[0]
    return False, None

# --- (核心修改) 步驟 2: 強力資料清洗函式 ---
def parse_and_clean_data(raw_text, ai_list_result):
    """
    優先使用 Regex 從原始文字中精準提取，如果抓不到，才退回使用 AI 原本的列表結果。
    """
    # 預設使用 AI 的結果
    final_data = list(ai_list_result)
    # 確保列表長度足夠
    while len(final_data) < 5:
        final_data.append("")

    # --- 1. 強力修正：售價 (尋找 $ 符號後面的數字) ---
    # pattern: 找 $ 或 售價，後面可能跟著冒號或空白，然後抓取數字
    price_match = re.search(r'(?:\$|售價)\s*[:.]?\s*(\d{3,})', raw_text)
    if price_match:
        # 如果 Regex 抓到了，就覆蓋掉 AI 的結果
        final_data[1] = price_match.group(1)

    # --- 2. 強力修正：Batch no. (尋找 "Batch no." 後面的特定格式) ---
    # pattern: 找 Batch no，後面跟著特定格式 (例如 14-開頭)
    batch_match = re.search(r'Batch\s*no\.?\s*[:.]?\s*([0-9]{2}-[0-9A-Z]+)', raw_text, re.IGNORECASE)
    if batch_match:
        final_data[4] = batch_match.group(1)

    # --- 3. 強力修正：保存期限 (處理 MM-YY 格式) ---
    # pattern: 找 Sell by date，抓取 MM-YY 格式 (例如 04-24)
    date_match = re.search(r'Sell\s*by\s*date\s*[:.]?\s*(\d{2})[-/](\d{2})', raw_text, re.IGNORECASE)
    if date_match:
        month, year_short = date_match.groups()
        # 假設是 20xx 年，組合成 YYYY-MM
        final_data[3] = f"20{year_short}-{month}"
    
    return final_data

# --- 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型路徑", available_models)

uploaded_files = st.file_uploader("選取照片 (建議正面+側面各一張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# 初始化 session state，多存一個 raw_text
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]
if 'raw_ocr_text' not in st.session_state:
    st.session_state.raw_ocr_text = ""

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在分析標籤細節...'):
                # 更新提示詞，強調關鍵錨點
                prompt = """你是一位專業的資料擷取員。請讀取圖片中的所有文字，並特別關注以下標籤特徵：
                1. **名稱**：在「品名:」之後的中文。
                2. **售價**：緊跟在錢字號「$」後面的數字。
                3. **容量**：數字後面跟著「ML」。
                4. **保存期限**：在「Sell by date:」後面的日期 (通常是 MM-YY 格式)。
                5. **Batch no.**：緊跟在「Batch no.:」後面的編號 (通常是 數字-數字 的格式)。

                請先輸出你看到的所有原始文字，然後再以 CSV 格式輸出摘要。
                摘要格式：名稱,售價,容量,保存期限,Batch no.
                """
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.raw_ocr_text = response.text # 儲存原始文字以供 Regex 分析
                    
                    # 嘗試找出 AI 生成的 CSV 行
                    lines = response.text.strip().split('\n')
                    csv_line = lines[-1] # 通常 AI 會把摘要放在最後一行
                    
                    # 初步清洗
                    clean_res = csv_line.replace(" ", "").replace("```csv", "").replace("```", "")
                    initial_list = clean_res.split(",")
                    
                    # --- 呼叫強力清洗函式 ---
                    # 傳入原始文字 和 AI初步判斷的列表
                    cleaned_data = parse_and_clean_data(st.session_state.raw_ocr_text, initial_list)
                    
                    st.session_state.edit_data = cleaned_data
                        
                    st.success("辨識完成！已套用強力格式修正。")
        except Exception as e:
            st.warning(f"AI 暫時無法辨識：{e}")

# --- 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
# 確保日期格式正確再進行比較，避免報錯
current_date = st.session_state.edit_data[3] if len(st.session_state.edit_data) > 3 and len(st.session_state.edit_data[3]) >= 7 else ""

# --- 智慧提醒區塊 ---
# 1. 檢查名稱
is_known, suggestion = check_product_name(current_name)
final_suggested_name = current_name # 預設為辨識結果

if current_name and not is_known:
    if suggestion:
        st.warning(f"⚠️ 系統辨識為「{current_name}」，庫存清單中找不到。")
        # 提供一個按鈕讓使用者快速採納建議
        if st.button(f"💡 點此修正為：{suggestion}"):
             final_suggested_name = suggestion
             st.session_state.edit_data[0] = suggestion # 更新 session
             st.rerun() # 重新整理頁面以套用變更
    else:
        st.error(f"❌ 「{current_name}」不在已知產品清單中。")

# 2. 檢查過期
if current_date:
    try:
        now_ym = datetime.now().strftime("%Y-%m")
        if current_date < now_ym:
            st.error(f"🛑 警告：此商品保存期限 ({current_date}) 已過期！(目前：{now_ym})")
    except:
        pass

# --- 輸入欄位區 ---
# 使用 final_suggested_name 來顯示名稱，如果使用者點了建議按鈕，這裡就會自動變更
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1] if len(st.session_state.edit_data)>1 else "")
f3 = st.text_input("容量", value=st.session_state.edit_data[2] if len(st.session_state.edit_data)>2 else "")
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3] if len(st.session_state.edit_data)>3 else "")
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認正確，正式入庫"):
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success(f"✅ {f1} 存入成功！")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.session_state.raw_ocr_text = ""
        st.rerun()
