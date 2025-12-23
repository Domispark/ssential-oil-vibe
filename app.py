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
st.title("🌿 精油入庫 (2.5 Flash 穩定版)")

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
    """根據測試結果動態排列最佳模型"""
    try:
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 排除不支援圖片的模型
        available = [n for n in available if not any(x in n.lower() for x in ["tts", "live", "embed"])]
        
        # 優先級：2.5-flash > 2.5-flash-lite > 3-flash
        priority = ["2.5-flash", "2.5-flash-lite", "3-flash"]
        sorted_list = []
        for p in priority:
            for name in available:
                if p in name.lower() and name not in sorted_list:
                    sorted_list.append(name)
        return sorted_list if sorted_list else available
    except:
        return ["models/gemini-2.5-flash", "models/gemini-2.5-flash-lite"]

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

# --- 步驟 1: 清理與解析功能 ---
def clean_text(text):
    """移除 Markdown 符號與 JSON 殘留"""
    if not text: return ""
    # 移除 **、"}、:、* 等符號
    s = re.sub(r'[\*\"\}\{\[\]\:]', '', text)
    return s.strip()

def parse_front_label(text):
    res = {"name": "", "price": "", "vol": ""}
    # 針對品名強化抓取
    name_match = re.search(r'品名\s*[:：]?\s*([^\s\n\r]+)', text)
    if name_match:
        res["name"] = clean_text(name_match.group(1))
    else:
        # 備案：抓取第一行
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines: res["name"] = clean_text(lines[0])

    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    if price_match: res["price"] = price_match.group(1)
    
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text)
    if vol_match: res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    res = {"expiry": "", "batch": ""}
    # 效期 MM-YY -> YYYY-MM
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    
    # 批號：鎖定數字與連字號，避開單純的 "no"
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9-]{4,})', text, re.IGNORECASE)
    if batch_match:
        res["batch"] = batch_match.group(1).strip()
    return res

# --- 3. 介面與辨識 ---
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

uploaded_files = st.file_uploader("上傳正面與側面照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

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
                with st.spinner(f'AI ({selected_model}) 分析中...'):
                    r1 = model.generate_content(["OCR FRONT: Extract Name, Price, ML", imgs[0]])
                    f_data = parse_front_label(r1.text)
                    
                    r2 = model.generate_content(["OCR SIDE: Extract Expiry, Batch", imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    st.session_state.edit_data = [
                        f_data["name"] if f_data["name"] else "辨識失敗",
                        f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                    st.success("辨識完成")
            except Exception as e:
                st.error(f"辨識異常：{e}")

# --- 4. 確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
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
