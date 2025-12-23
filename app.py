import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (效能優化版)")

# --- 1. 介面側邊欄：模型管理與額度提醒 ---
st.sidebar.subheader("⚙️ 系統診斷")

# [需求 1] 定義您絕對想要保留的模型列表，其他的都會被過濾掉
# 根據您的測試，這三個是最穩定的
ALLOWED_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3-flash-preview"
]

@st.cache_data(ttl=600)
def get_clean_models():
    try:
        all_models = [m.name for m in genai.list_models()]
        # 只保留在 ALLOWED_MODELS 裡面，且 API 確實存在的模型
        final_list = [m for m in all_models if m in ALLOWED_MODELS]
        return final_list if final_list else ALLOWED_MODELS
    except:
        return ALLOWED_MODELS

selected_model = st.sidebar.selectbox("當前使用模型", get_clean_models())

# [需求 2] 額度提醒區塊
st.sidebar.divider()
st.sidebar.warning("⚠️ **API 額度提醒**")
st.sidebar.write(f"您的 RPD 上限：**20 次 / 日**")
st.sidebar.info("💡 每按一次『啟動分段辨識』會消耗 **2 次** 額度（正面+側面）。建議每天辨識不超過 10 瓶精油。")

# --- 2. 初始化與功能函式 (承襲先前版本) ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_text(text):
    if not text: return ""
    return re.sub(r'[\*\"\}\{\[\]\:]', '', text).strip()

def parse_front_label(text):
    res = {"name": "", "price": "", "vol": ""}
    name_match = re.search(r'品名\s*[:：]?\s*([^\s\n\r]+)', text)
    res["name"] = clean_text(name_match.group(1)) if name_match else clean_text(text.split('\n')[0])
    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    if price_match: res["price"] = price_match.group(1)
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text)
    if vol_match: res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    res = {"expiry": "", "batch": ""}
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9-]{4,})', text, re.IGNORECASE)
    if batch_match: res["batch"] = batch_match.group(1).strip()
    return res

# --- 3. 主要作業區 ---
uploaded_files = st.file_uploader("上傳正面與側面照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請同時上傳兩張照片。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner(f'AI 辨識中...'):
                    r1 = model.generate_content(["OCR FRONT: Extract Name, Price, ML", imgs[0]])
                    f_data = parse_front_label(r1.text)
                    r2 = model.generate_content(["OCR SIDE: Extract Expiry, Batch", imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    st.session_state.edit_data = [
                        f_data["name"], f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                    st.success("辨識完成！ (已使用 2/20 當日配額)")
            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 額度已達上限！請更換模型或明天再試。")
                else:
                    st.error(f"辨識異常：{e}")

# --- 4. 確認與入庫 (略，與前版相同) ---
st.divider()
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

# 入庫按鈕邏輯... (略)
