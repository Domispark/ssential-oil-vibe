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
        models.sort(key=lambda x: 'flash' not in x.lower())
        return models
    except Exception:
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

# --- 步驟 2: 通用型資料清洗函式 ---
def parse_and_clean_data(raw_text):
    data = ["", "", "", "", ""] # 名稱, 售價, 容量, 效期, Batch

    # 1. 售價
    price_match = re.search(r'(?:\$|零售價)\s*:?\s*(\d+)', raw_text)
    if price_match:
        data[1] = price_match.group(1)

    # 2. 容量
    vol_match = re.search(r'(\d+)\s*ML', raw_text, re.IGNORECASE)
    if vol_match:
        data[2] = vol_match.group(1)

    # 3. 保存期限 (MM-YY 轉 YYYY-MM)
    date_match = re.search(r'Sell\s*by\s*date\s*[:\s]*(\d{2})[-/](\d{2})', raw_text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        data[3] = f"20{yy}-{mm}"

    # 4. Batch No.
    batch_patterns = [
        r'Batch\s*no\.?[:\s]*(\d+-\d+)', 
        r'Batch\s*no\.?[:\s]*([A-Z0-9-]+)'
    ]
    for pattern in batch_patterns:
        batch_match = re.search(pattern, raw_text, re.IGNORECASE)
        if batch_match:
            candidate = batch_match.group(1).strip()
            if not (candidate.isdigit() and len(candidate) > 8):
                data[4] = candidate
                break
    return data

# --- 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
# 修正處：確保名稱正確呼叫為 get_working_models()
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

uploaded_files = st.file_uploader("選取照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在解讀標籤...'):
                prompt = """
                Please act as an OCR engine. 
                Task: Read all text from the images.
                
                Important Guidelines:
                1. Identify "品名" (Product Name) usually on the first line.
                2. Find "零售價" or "$" for Price.
                3. Find "容量" or "ML" for Volume.
                4. Find "Sell by date" in MM-YY format (e.g., 04-28).
                5. Find "Batch no." (e.g., 7-330705). IGNORE large barcode numbers.
                """
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    cleaned_data = parse_and_clean_data(response.text)
                    name_match = re.search(r'品名[:\s]*([^\n]+)', response.text)
                    if name_match:
                        cleaned_data[0] = name_match.group(1).strip()
                    st.session_state.edit_data = cleaned_data
                    st.success("辨識完成")
        except Exception as e:
            st.warning(f"AI 錯誤：{e}")

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
            st.warning(f"⚠️ 辨識為「{current_name}」，庫存清單中找不到。")
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
        st.rerun()
