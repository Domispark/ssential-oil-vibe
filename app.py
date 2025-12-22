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
st.title("🌿 精油入庫 (分工辨識版)")

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

# --- 步驟 2: 分工資料清洗函式 ---
def parse_front_label(text):
    """處理第一張圖：品名、售價、容量"""
    res = {"name": "", "price": "", "vol": ""}
    # 品名：找品名後面的字
    name_match = re.search(r'品名[:：]\s*([^\n\r]+)', text)
    if name_match:
        res["name"] = re.sub(r'[\*#\(\)]', '', name_match.group(1)).strip()
    
    # 售價：找 $ 後數字
    price_match = re.search(r'(?:\$|售價)\s*[:：]?\s*(\d+)', text)
    if price_match:
        res["price"] = price_match.group(1)
        
    # 容量：找 ML 前數字
    vol_match = re.search(r'(\d+)\s*ML', text, re.IGNORECASE)
    if vol_match:
        res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    """處理第二張圖：效期、批號"""
    res = {"expiry": "", "batch": ""}
    # 效期：MM-YY 轉 YYYY-MM
    date_match = re.search(r'Sell\s*by\s*date\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    
    # 批號：嚴格鎖定 Batch no 後的字串，排除長條碼
    batch_match = re.search(r'Batch\s*no\.?[:：\s]*([A-Z0-9-]+)', text, re.IGNORECASE)
    if batch_match:
        candidate = batch_match.group(1).strip()
        if not (candidate.isdigit() and len(candidate) > 9):
            res["batch"] = candidate
    return res

# --- 3. 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

# 強制要求兩張照片
st.info("📌 請上傳兩張照片：第一張為標籤正面(含品名)，第二張為標籤側面(含批號)")
uploaded_files = st.file_uploader("選取照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.error("⚠️ 請至少上傳兩張照片（正面與側面）以確保辨識準確。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner('正在分層分析標籤內容...'):
                    # 辨識第一張：正面
                    p1 = "OCR the FRONT label. Focus on '品名', '$' price, and 'ML' volume. Output all text."
                    r1 = model.generate_content([p1, imgs[0]])
                    front_data = parse_front_label(r1.text)
                    
                    # 辨識第二張：側面
                    p2 = "OCR the SIDE label. Focus on 'Sell by date' (MM-YY) and 'Batch no'. Ignore barcode. Output all text."
                    r2 = model.generate_content([p2, imgs[1]])
                    side_data = parse_side_label(r2.text)
                    
                    # 組合結果
                    st.session_state.edit_data = [
                        front_data["name"],
                        front_data["price"],
                        front_data["vol"],
                        side_data["expiry"],
                        side_data["batch"]
                    ]
                    st.success("分段辨識完成！")
            except Exception as e:
                st.warning(f"AI 辨識發生錯誤：{e}")

# --- 4. 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
is_known, suggestion = check_product_name(current_name)
if current_name and not is_known and suggestion:
    if st.button(f"💡 點此改為清單名稱：{suggestion}"):
        st.session_state.edit_data
