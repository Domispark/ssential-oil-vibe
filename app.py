import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import difflib
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (通用防呆版)")

# --- 步驟 0: 產品資料庫 ---
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
        # 修改這裡：將 'flash' 排在最前面，因為它免費額度高，不易報錯
        models.sort(key=lambda x: 'flash' not in x.lower())
        return models
    except Exception:
        # 如果抓不到清單，預設回傳這兩個，Flash 在前
        return ["models/gemini-1.5-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-pro"]

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

# --- 步驟 1: 檢查名稱 ---
def check_product_name(ai_input_name):
    if ai_input_name in KNOWN_PRODUCTS:
        return True, None
    matches = difflib.get_close_matches(ai_input_name, KNOWN_PRODUCTS, n=1, cutoff=0.4)
    if matches:
        return False, matches[0]
    return False, None

# --- (核心修改) 步驟 2: 通用型資料清洗函式 ---
def parse_and_clean_data(raw_text):
    """
    使用「相對位置」與「邏輯排除」來抓取資料，不寫死特定開頭。
    """
    data = ["", "", "", "", ""] 

    # --- A. 售價 (通用邏輯) ---
    # 邏輯：找 $ 或 NT 或 售價，允許後面有空格，抓取數字
    # 解決 "$ 5 6 0" 問題：抓取 (\d[\d\s]*\d) 表示「數字開頭、中間可有空格、數字結尾」
    price_match = re.search(r'(?:\$|NT\.?|售價)\s*[:.]?\s*(\d[\d\s,]*\d)', raw_text, re.IGNORECASE)
    if price_match:
        # 抓到後，把中間的空格或逗號拿掉
        clean_price = re.sub(r'[^\d]', '', price_match.group(1))
        data[1] = clean_price

    # --- B. 容量 (通用邏輯) ---
    # 找數字，且後面緊跟著 ml (忽略大小寫)
    vol_match = re.search(r'(\d+)\s*(?:ml|ML|Ml)', raw_text)
    if vol_match:
        data[2] = vol_match.group(1)

    # --- C. Batch no. (相對位置 + 排除法) ---
    # 1. 先把文字切成行，因為 Batch No 通常跟標籤在同一行
    lines = raw_text.split('\n')
    batch_found = None
    
    # 策略：逐行掃描，找到 "Batch" 關鍵字的那一行
    for line in lines:
        if "batch" in line.lower():
            # 找到關鍵字了！現在分析這一行
            # 移除 "Batch no.:" 這些字，剩下內容
            content = re.sub(r'Batch\s*no\.?[:\s]*', '', line, flags=re.IGNORECASE).strip()
            
            # 依空白切割，通常 Batch 是緊接在後面的第一個字串
            parts = content.split()
            for part in parts:
                # --- 過濾器 ---
                # 1. 忽略太長的純數字 (像是條碼 25019424...)，假設 Batch 不會超過 10 位純數字
                if part.isdigit() and len(part) > 8:
                    continue 
                # 2. 忽略像 "2090-10" 這種可能是 Article No 的 (如果它是特定的格式，這裡先寬鬆一點)
                # 3. 忽略日期格式 (如 2024-10)
                if re.match(r'^\d{4}-\d{2}$', part):
                    continue

                # 如果通過過濾，且長度合理 (至少3碼)，就當作是 Batch
                if len(part) > 2:
                    batch_found = part
                    break # 找到一個就跳出
        
        if batch_found:
            break

    # 如果逐行沒抓到，嘗試全域搜尋 regex (補救措施)
    if not batch_found:
        # 找 Batch no 後面，非空白的英數組合
        # 排除純長數字 (?! \d{8,})
        regex_match = re.search(r'Batch\s*no\.?[:\s]*((?!\d{9,})[A-Z0-9-]+)', raw_text, re.IGNORECASE)
        if regex_match:
            batch_found = regex_match.group(1)
            
    if batch_found:
        data[4] = batch_found

    # --- D. 保存期限 ---
    # 優先找 Sell by date
    date_match = re.search(r'Sell\s*by\s*(?:date)?.*(\d{2}[-.]\d{2})', raw_text, re.IGNORECASE)
    if not date_match:
         # 備案：找獨立的 MM-YY，但要小心不要抓到 Batch
         # 規則：前後不能有數字，格式為 數字2碼-數字2碼
         date_match = re.search(r'(?<!\d)(0[1-9]|1[0-2])[-.](\d{2})(?!\d)', raw_text)

    if date_match:
        if len(date_match.groups()) == 1:
            val = date_match.group(1).replace(".", "-")
            parts = val.split("-")
            data[3] = f"20{parts[1]}-{parts[0]}"
        else:
            data[3] = f"20{date_match.group(2)}-{date_match.group(1)}"

    return data

# --- 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
# 自動選 Pro
default_index = 0
for i, m in enumerate(available_models):
    if "pro" in m:
        default_index = i
        break
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=default_index)

uploaded_files = st.file_uploader("選取照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]
if 'raw_text_debug' not in st.session_state:
    st.session_state.raw_text_debug = ""

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在解讀標籤...'):
                # 提示詞重點：告訴 AI 忽略條碼
                prompt = """
                Please act as an OCR engine. 
                Task: Read all text from the images.
                
                Important Guidelines:
                1. Look carefully for "Batch no." and "Sell by date".
                2. IGNORE the large barcode numbers.
                3. The Batch no is usually small, alphanumeric (e.g., 14-XXXX or AB-XXXX).
                4. The Price usually starts with '$' or 'NT'.
                
                Output raw text line by line.
                """
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.raw_text_debug = response.text 
                    
                    # 1. 跑通用清洗
                    cleaned_data = parse_and_clean_data(response.text)
                    
                    # 2. 補抓品名 (中文)
                    name_match = re.search(r'品名[:\s]*([^\n]+)', response.text)
                    if name_match:
                        cleaned_data[0] = name_match.group(1).strip()

                    st.session_state.edit_data = cleaned_data
                    st.success("辨識完成")
        except Exception as e:
            st.warning(f"AI 錯誤：{e}")

# --- 除錯區塊 ---
if st.session_state.raw_text_debug:
    with st.expander("🕵️ 偵探模式 (原始資料)"):
        st.text(st.session_state.raw_text_debug)

# --- 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
current_date = st.session_state.edit_data[3]

is_known, suggestion = check_product_name(current_name)
if current_name and not is_known:
    if suggestion:
        col_warn, col_btn = st.columns([3, 1])
        with col_warn:
            st.warning(f"⚠️ 辨識為「{current_name}」，庫存無此名稱。")
        with col_btn:
            if st.button(f"💡 改為：{suggestion}"):
                st.session_state.edit_data[0] = suggestion
                st.rerun()

if current_date and len(current_date) == 7:
    try:
        now_ym = datetime.now().strftime("%Y-%m")
        if current_date < now_ym:
            st.error(f"🛑 商品已過期！效期 {current_date} < 當前 {now_ym}")
    except:
        pass

f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 確認入庫"):
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success(f"✅ {f1} 存入成功！")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.session_state.raw_text_debug = ""
        st.rerun()
