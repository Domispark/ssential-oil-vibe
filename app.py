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
st.title("🌿 精油入庫 (強力通用版)")

# --- 步驟 0: 產品資料庫 ---
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級",
    "綠薄荷精油",
    "白雲杉-特級",
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
        return ["models/gemini-1.5-flash", "models/gemini-2.0-flash-exp"]

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

# --- 步驟 2: 強力資料清洗函式 ---
def parse_and_clean_data(raw_text):
    data = ["", "", "", "", ""] 

    # 1. 售價 (抓取 $ 符號後，或「售價」後方的純數字)
    # 解決截圖中掃描不到 $700 的問題
    price_match = re.search(r'(?:\$|售價|零售價)\s*[:：]?\s*(\d+)', raw_text)
    if price_match:
        data[1] = price_match.group(1)

    # 2. 容量 (抓取 ML 前方的數字)
    vol_match = re.search(r'(\d+)\s*ML', raw_text, re.IGNORECASE)
    if vol_match:
        data[2] = vol_match.group(1)

    # 3. 保存期限 (將 MM-YY 轉為 YYYY-MM，如 04-28 -> 2028-04)
    # 解決截圖中「保存期限」空白的問題
    date_match = re.search(r'(?:Sell\s*by\s*date|效期|保存期限)\s*[:：]?\s*(\d{2})[-/](\d{2})', raw_text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        data[3] = f"20{yy}-{mm}"

    # 4. Batch No. (優先尋找「Batch no.:」後面的英數組合)
    # 排除長條碼數字
    batch_match = re.search(r'Batch\s*no\.?\s*[:：]?\s*([A-Z0-9-]+)', raw_text, re.IGNORECASE)
    if batch_match:
        candidate = batch_match.group(1).strip()
        if not (candidate.isdigit() and len(candidate) > 9):
            data[4] = candidate
            
    return data

# --- 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

uploaded_files = st.file_uploader("選取照片 (建議正面與側面)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在分析標籤特徵...'):
                prompt = """
                Please act as an OCR specialist. Extract exactly these label details:
                1. 品名: The Chinese text following "品名:".
                2. 售價: The number following "$".
                3. 容量: The number before "ML".
                4. 保存期限: The MM-YY format after "Sell by date:".
                5. Batch no.: The code following "Batch no.:".
                
                Just list the results line by line, no extra text.
                """
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    raw_res = response.text
                    # 先過濾 AI 的說明文字 (Product Name: 等)
                    cleaned_data = parse_and_clean_data(raw_res)
                    
                    # 抓取品名 (特別針對中文品名行)
                    name_match = re.search(r'(?:品名|Name)\s*[:：]?\s*([^\n\r]+)', raw_res)
                    if name_match:
                        # 清理多餘的標點與 AI 加註
                        clean_name = name_match.group(1).strip().replace('*', '')
                        cleaned_data[0] = re.sub(r'\(.*?\)', '', clean_name).strip()
                    else:
                        cleaned_data[0] = raw_res.split('\n')[0].strip()

                    st.session_state.edit_data = cleaned_data
                    st.success("辨識完成")
        except Exception as e:
            st.warning(f"AI 異常，請手動輸入：{e}")

# --- 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
current_date = st.session_state.edit_data[3]

# 相似名稱提醒功能
is_known, suggestion = check_product_name(current_name)
if current_name and not is_known:
    if suggestion:
        if st.button(f"💡 點此改為清單建議名稱：{suggestion}"):
            st.session_state.edit_data[0] = suggestion
            st.rerun()

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
