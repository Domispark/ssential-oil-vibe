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
st.title("🌿 精油入庫 (Next-Gen 辨識版)")

# --- 步驟 0: 產品資料庫 ---
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級", "胡椒薄荷-一般", "綠薄荷精油", "白雲杉-特級",
    "甜橙精油", "薰衣草精油-高地", "茶樹精油"
]

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

@st.cache_data(ttl=600)
def get_working_models():
    """根據截圖提供的最新名單進行排序"""
    # 這裡根據您的 Rate limits 截圖，手動指定最新的模型路徑
    # 優先順序：Gemini 3 > Gemini 2.5 (新一代模型通常有較好的免費配額)
    latest_models = [
        "models/gemini-3-flash",
        "models/gemini-2.5-flash",
        "models/gemini-2.5-flash-lite",
        "models/gemini-2.0-flash-exp" # 保留備案
    ]
    return latest_models

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

# --- 步驟 2: 資料解析函式 ---
def parse_front_label(text):
    res = {"name": "", "price": "", "vol": ""}
    name_match = re.search(r'品名\s*[:：]?\s*([^\n\r*]+)', text)
    if name_match:
        res["name"] = name_match.group(1).strip()
    else:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) > 0:
            res["name"] = lines[0].replace('品名', '').replace(':', '').strip()
    price_match = re.search(r'(?:\$|售價|零售價)\s*[:：]?\s*(\d[\d\s]*\d)', text)
    if price_match:
        res["price"] = re.sub(r'\D', '', price_match.group(1))
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升|容量)', text, re.IGNORECASE)
    if not vol_match:
        vol_match = re.search(r'容量\s*[:：]?\s*(\d+)', text)
    if vol_match:
        res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    res = {"expiry": "", "batch": ""}
    date_match = re.search(r'(?:Sell\s*by\s*date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([A-Z0-9-]+)', text, re.IGNORECASE)
    if batch_match:
        candidate = batch_match.group(1).strip()
        if not (candidate.isdigit() and len(candidate) > 9):
            res["batch"] = candidate
    return res

# --- 3. 介面與辨識 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("選取最新模型", available_models, index=0)

st.info("📌 已更新至最新模型名單 (Gemini 3 / 2.5)。")
uploaded_files = st.file_uploader("選取照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請上傳兩張照片。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner(f'正在使用 {selected_model} 辨識...'):
                    # 辨識正面
                    p1 = "OCR FRONT label. Find '品名', '$', and 'ML'. Output ALL text."
                    r1 = model.generate_content([p1, imgs[0]])
                    f_data = parse_front_label(r1.text)
                    
                    # 辨識側面
                    p2 = "OCR SIDE label. Find 'Sell by date' and 'Batch no'. Output ALL text."
                    r2 = model.generate_content([p2, imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    st.session_state.edit_data = [
                        f_data["name"] if f_data["name"] else "辨識失敗",
                        f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                    st.success("辨識成功")
            except Exception as e:
                st.error(f"辨識異常：{e}")

# --- 4. 確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
is_known, suggestion = check_product_name(f1)
if f1 and not is_known and suggestion:
    if st.button(f"💡 建議更正為：{suggestion}"):
        st.session_state.edit_data[0] = suggestion
        st.rerun()

f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 正式入庫"):
    if f1 and f1 != "辨識失敗":
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success(f"✅ {f1} 已入庫！")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
