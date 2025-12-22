import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import difflib  # (新增) Python 內建的差異比對工具，不用安裝

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (智慧防呆版)")

# --- (新增) 步驟 0: 建立正確的產品資料庫 ---
# 這是您的「標準答案」。系統會拿 AI 看到的字跟這裡比對。
# 您可以隨時把正確的產品名稱加進來。
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級",
    "白雲杉-特級"
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

# --- (新增) 步驟 1: 建立檢查邏輯函式 ---
def check_product_name(ai_input_name):
    """
    輸入 AI 看到的名稱，回傳 (是否完全正確, 建議名稱)
    """
    if ai_input_name in KNOWN_PRODUCTS:
        return True, None
    
    # 使用 Python 內建的 get_close_matches 找最像的
    # n=1 表示只找 1 個，cutoff=0.4 表示相似度只要 40% 就抓進來
    matches = difflib.get_close_matches(ai_input_name, KNOWN_PRODUCTS, n=1, cutoff=0.4)
    
    if matches:
        return False, matches[0] # 回傳最像的那個
    return False, None

# --- 2. 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型路徑", available_models)

st.info(f"💡 目前連線路徑：`{selected_model}`")
uploaded_files = st.file_uploader("選取照片 (建議正面+側面各一張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# 初始化 session state
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在分析標籤細節...'):
                prompt = """你是一位極度細心的倉管員。請從圖中提取精確資訊：
                1. **名稱**：標籤第一行「品名:」後的繁體中文。
                2. **售價**：標籤上的金額數字（只留數字）。
                3. **容量**：標籤上的 ML 數。
                4. **保存期限**：尋找 'Sell by date' 或日期，格式轉為 YYYY-MM。
                5. **Batch no.**：務必尋找 "Batch no.:" 之後的批號。

                僅回傳格式：名稱,售價,容量,保存期限,Batch no.
                請僅回傳一行文字，逗號隔開。若無資訊則填寫 N/A。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    # 簡單的清洗
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    # 防止 AI 回傳多餘的 Markdown 符號
                    clean_res = clean_res.replace("```csv", "").replace("```", "")
                    
                    st.session_state.edit_data = clean_res.split(",")
                    # 若欄位不足 5 個，補齊空字串以免報錯
                    while len(st.session_state.edit_data) < 5:
                        st.session_state.edit_data.append("")
                        
                    st.success("辨識完成！請檢查下方欄位。")
        except Exception as e:
            st.warning(f"AI 暫時無法辨識：{e}")

# --- 3. 確認與入庫區 (大幅優化) ---
st.divider()
st.subheader("📝 確認入庫資訊")

# 取得目前 session 中的資料
current_name = st.session_state.edit_data[0]
current_date = st.session_state.edit_data[3] if len(st.session_state.edit_data) > 3 else ""

# --- (新增) 智慧提醒區塊 ---
# 1. 檢查名稱
is_known, suggestion = check_product_name(current_name)
if current_name and not is_known:
    if suggestion:
        st.warning(f"⚠️ 系統辨識為「{current_name}」，庫存清單中找不到。")
        st.info(f"💡 您是否是指： **{suggestion}** ？")
        # 讓使用者一鍵修正 (這裡做成提示，使用者手動改即可，避免太複雜)
    else:
        st.error(f"❌ 「{current_name}」不在已知產品清單中，請確認是否為新品或辨識錯誤。")

# 2. 檢查過期 (簡易版)
if current_date and len(current_date) >= 7: # 確保有 YYYY-MM
    try:
        # 抓取系統現在時間 (YYYY-MM)
        now_ym = datetime.now().strftime("%Y-%m")
        if current_date < now_ym:
            st.error(f"🛑 警告：此商品保存期限 ({current_date}) 已過期！(目前：{now_ym})")
    except:
        pass # 日期格式如果不對，就跳過檢查不報錯

# --- 輸入欄位區 ---
f1 = st.text_input("產品名稱", value=current_name)
f2 = st.text_input("售價", value=st.session_state.edit_data[1] if len(st.session_state.edit_data)>1 else "")
f3 = st.text_input("容量", value=st.session_state.edit_data[2] if len(st.session_state.edit_data)>2 else "")
f4 = st.text_input("保存期限 (YYYY-MM)", value=current_date)
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認正確，正式入庫"):
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success(f"✅ {f1} 存入成功！")
        # 清空
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
