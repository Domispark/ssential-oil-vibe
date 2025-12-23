import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")

# --- 1. 側邊欄配置 ---
st.sidebar.subheader("⚙️ 系統診斷")

# 鎖定測試表現最佳的模型
ALLOWED_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3-flash-preview"
]

@st.cache_data(ttl=600)
def get_clean_models():
    try:
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        final_list = [m for m in all_models if m in ALLOWED_MODELS]
        return final_list if final_list else ALLOWED_MODELS
    except:
        return ALLOWED_MODELS

selected_model = st.sidebar.selectbox("當前使用模型", get_clean_models())

st.sidebar.divider()
st.sidebar.warning("⚠️ **API 額度提醒**")
st.sidebar.write("您的 RPD 上限：**20 次 / 日**")
st.sidebar.info("💡 目前已使用次數可於 Google AI Studio 監測。")

st.title("🌿 精油入庫 (辨識補強版)")

# --- 2. 核心功能函式 ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_extracted_value(text):
    """強力清理所有非必要的標點符號與標籤"""
    if not text: return ""
    # 移除 Markdown、括號、冒號及常見雜訊
    s = re.sub(r'[\*\"\}\{\[\]\:\#]', '', text)
    s = s.replace('Name', '').replace('Product', '').strip()
    return s

def parse_front_label(text):
    """針對正面標籤的深度解析"""
    res = {"name": "", "price": "", "vol": ""}
    # 1. 尋找品名 (胡椒薄荷-特級)
    name_match = re.search(r'品名\s*[:：]?\s*([^\s\n\r]+)', text)
    if name_match:
        res["name"] = clean_extracted_value(name_match.group(1))
    else:
        # 如果沒抓到標籤，則嘗試找第一行內容
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 2]
        if lines: res["name"] = clean_extracted_value(lines[0])

    # 2. 尋找價格 (560)
    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    if price_match: res["price"] = price_match.group(1)

    # 3. 尋找容量 (10ML) - 修正之前抓到 10 的問題
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升|容量)', text, re.IGNORECASE)
    if vol_match: res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    """針對側面標籤的深度解析"""
    res = {"expiry": "", "batch": ""}
    # 1. 效期 MM-YY (04-24)
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"

    # 2. 批號 (14-268665) - 強化連字號抓取
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9A-Z-]+)', text, re.IGNORECASE)
    if batch_match:
        cand = batch_match.group(1).strip()
        if cand.lower() != "no": res["batch"] = cand
    return res

# --- 3. 作業區 ---
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

uploaded_files = st.file_uploader("請上傳正面與側面照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動強化辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請上傳兩張照片。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner('正在進行深度 OCR 掃描...'):
                    # 提示詞優化：要求 AI 回傳原始文字，不要嘗試格式化
                    p1 = "OCR FRONT label. Read the text carefully. Focus on '品名', '售價', and '容量'. Return the exact text found."
                    r1 = model.generate_content([p1, imgs[0]])
                    f_data = parse_front_label(r1.text)

                    p2 = "OCR SIDE label. Read 'Sell by date' and 'Batch no'. Focus on the numbers after these words. Return the exact text."
                    r2 = model.generate_content([p2, imgs[1]])
                    s_data = parse_side_label(r2.text)

                    st.session_state.edit_data = [
                        f_data["name"], f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                st.success("辨識完成，請確認下方資訊。")
                st.rerun()
            except Exception as e:
                st.error(f"辨識異常：{e}")

# --- 4. 確認與入庫 ---
st.divider()
st.subheader("📝 確認入庫資訊")

# 確保 UI 始終顯示最新數據
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量 (ML)", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 正式入庫"):
    # (入庫邏輯同前版本，省略)
    pass
