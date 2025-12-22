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
    "胡椒薄荷-一般",
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

# --- 步驟 2: 通用型資料清洗函式 (強化容錯版) ---
def parse_and_clean_data(raw_text):
    data = ["", "", "", "", ""] 

    # 1. 售價 (抓取 $ 符號後，或者 "售價" 字樣後的數字，允許中間有空格)
    price_match = re.search(r'(?:\$|售價|零售價)\s*[:：]?\s*(\d[\d\s,]*\d)', raw_text)
    if price_match:
        data[1] = re.sub(r'\D', '', price_match.group(1)) # 只保留數字

    # 2. 容量 (抓取數字後面跟著 ML/ml/毫升，或者 "容量" 後面的數字)
    vol_match = re.search(r'(?:容量|Size)?\s*[:：]?\s*(\d+)\s*(?:ML|ml|毫升)', raw_text, re.IGNORECASE)
    if not vol_match:
        vol_match = re.search(r'(\d+)\s*ML', raw_text, re.IGNORECASE)
    if vol_match:
        data[2] = vol_match.group(1)

    # 3. 保存期限 (處理 MM-YY 格式，如 04-28 -> 2028-04)
    date_match = re.search(r'(?:Sell\s*by\s*date|效期|保存期限)\s*[:：]?\s*(\d{2})[-/](\d{2})', raw_text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        data[3] = f"20{yy}-{mm}"

    # 4. Batch No. (找 Batch no. 後面，長度 3-12 碼的字串，避開超長條碼)
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

uploaded_files = st.file_uploader("選取照片 (正面+側面)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在精準讀取標籤資訊...'):
                # 提示詞強化：要求 AI 必須讀到關鍵前綴文字
                prompt = """
                Extract all label details from images. 
                Please look specifically for prefixes like "品名:", "$", "ML", "Sell by date:", and "Batch no.:".
                
                Format your output clearly like this:
                品名: [Name]
                售價: $[Number]
                容量: [Number]ML
                保存期限: [MM-YY]
                Batch no.: [String]
                """
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    raw_res = response.text
                    # 1. 跑強力清洗
                    cleaned_data = parse_and_clean_data(raw_res)
                    
                    # 2. 抓取品名 (特別針對中文)
                    name_match = re.search(r'(?:品名|Product Name)\s*[:：]?\s*([^\n]+)', raw_res)
                    if name_match:
                        # 移除 AI 可能加上的 ** 或 ( )
                        raw_name = name_match.group(1).strip()
                        cleaned_data[0] = re.sub(r'[\*#\(\)]', '', raw_name).strip()
                    else:
                        cleaned_data[0] = raw_res.split('\n')[0].replace('*', '').strip()

                    st.session_state.edit_data = cleaned_data
                    st.success("辨識完成！請確認欄位。")
        except Exception as e:
            st.warning(f"AI 暫時出錯，請手動填寫：{e}")

# --- 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
current_date = st.session_state.edit_data[3]

# 智慧建議
is_known, suggestion = check_product_name(current_name)
if current_name and not is_known:
    if suggestion:
        if st.button(f"💡 點此改為清單名稱：{suggestion}"):
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
