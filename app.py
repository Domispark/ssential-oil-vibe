import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (2.5 Flash 穩定版)")

# --- 1. 模型清單與額度看板 ---
st.sidebar.subheader("⚙️ 系統診斷")

# [需求 1] 只保留最穩定的三個模型，刪除其餘不需要的選項
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

# [需求 2] 呈現使用額度提醒
st.sidebar.divider()
st.sidebar.warning("⚠️ **API 額度提醒**")
st.sidebar.write("您的 RPD 上限：**20 次 / 日**")
st.sidebar.info("💡 每按一次『啟動分段辨識』會消耗 **2 次** 額度。建議每天辨識不超過 10 瓶精油。")

# --- 2. 初始化與解析功能 ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_text(text):
    """移除 Markdown、JSON 殘留及多餘的 'Name' 標籤"""
    if not text: return ""
    # 移除 **、"}、:、*、Name 等字眼
    s = re.sub(r'[\*\"\}\{\[\]\:]', '', text)
    s = s.replace('Name', '').strip()
    return s

def parse_front_label(text):
    res = {"name": "", "price": "", "vol": ""}
    name_match = re.search(r'品名\s*[:：]?\s*([^\s\n\r]+)', text)
    res["name"] = clean_text(name_match.group(1)) if name_match else clean_text(text.split('\n')[0])
    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    res["price"] = price_match.group(1) if price_match else ""
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text)
    res["vol"] = vol_match.group(1) if vol_match else ""
    return res

def parse_side_label(text):
    res = {"expiry": "", "batch": ""}
    # 效期 MM-YY -> YYYY-MM
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    # 批號：鎖定 14-268665 格式
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9-]{4,})', text, re.IGNORECASE)
    res["batch"] = batch_match.group(1).strip() if batch_match else ""
    return res

# --- 3. 作業區與入庫邏輯 (其餘部分同前版) ---
# ... (略去重複的上傳與確認區代碼)
