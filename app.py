import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (純淨強化版)")

# --- 1. 側邊欄配置 (僅保留模型選單) ---
st.sidebar.subheader("⚙️ 系統診斷")

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

# --- 2. 核心功能函式 (強化字串清洗) ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_extracted_value(text):
    """強力移除 AI 輸出的雜訊，如 **、"}、Name 等"""
    if not text: return ""
    # 移除 Markdown、括號、冒號及常見雜訊
    s = re.sub(r'[\*\"\}\{\[\]\:\#]', '', text)
    # 移除 AI 有時會自動補上的標籤詞
    s = re.sub(r'(Product Name|Name|品名|售價|容量)', '', s, flags=re.IGNORECASE)
    return s.strip()

def parse_front_label(text):
    """解析正面：品名、售價、容量"""
    res = {"name": "", "price": "", "vol": ""}
    # 1. 品名：找標籤後第一個字串，或直接抓第一行
    name_match = re.search(r'品名\s*[:：]?\s*([^\s\n\r]+)', text)
    res["name"] = clean_extracted_value(name_match.group(1)) if name_match else clean_extracted_value(text.split('\n')[0])

    # 2. 售價
    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    if price_match: res["price"] = price_match.group(1)

    # 3. 容量 (數字 + ML/ml)
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text, re.IGNORECASE)
    if vol_match: res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    """解析側面：效期、批號"""
    res = {"expiry": "", "batch": ""}
    # 1. 效期 MM-YY
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"

    # 2. 批號 (鎖定數字連字號格式 14-268665)
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9-]{4,})', text, re.IGNORECASE)
    if batch_match: res["batch"] = batch_match.group(1).strip()
    return res

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

# --- 3. 作業區 ---
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

uploaded_files = st.file_uploader("上傳「正面」與「側面」照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動強化辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請上傳兩張照片。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner('AI 正在讀取標籤細節...'):
                    # 提示詞調整：要求 AI 回傳原始辨識結果，增加解析成功率
                    r1 = model.generate_content(["Read all text on this essential oil FRONT label. Find name, price, and ml.", imgs[0]])
                    f_data = parse_front_label(r1.text)
                    
                    r2 = model.generate_content(["Read all text on this SIDE label. Find the Sell by date and Batch no.", imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    st.session_state.edit_data = [
                        f_data["name"], f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                st.success("辨識完成！")
                st.rerun()
            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 每日 API 配額已達上限。")
                else:
                    st.error(f"辨識異常：{e}")

# --- 4. 確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量 (ML)", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 正式入庫"):
    if f1 and f1 != "辨識失敗":
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success(f"✅ {f1} 已成功入庫！")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
