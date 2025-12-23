import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

# 頁面配置
st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")

# --- 1. 側邊欄：模型管理與額度提醒 ---
st.sidebar.subheader("⚙️ 系統診斷")

# 需求 1: 精簡模型選單
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

# 需求 2: 額度提醒看板
st.sidebar.divider()
st.sidebar.warning("⚠️ **API 額度提醒**")
st.sidebar.write("您的 RPD 上限：**20 次 / 日**")
st.sidebar.info("💡 每按一次『啟動分段辨識』會消耗 **2 次** 額度。建議每天辨識不超過 10 瓶精油。")

st.title("🌿 精油入庫 (2.5 Flash 穩定版)")

# --- 2. 初始化與解析功能 ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_text(text):
    """移除 Markdown、JSON 殘留及 AI 自動帶入的標籤"""
    if not text: return ""
    # 移除 **、"}、:、*、Name 等標籤
    s = re.sub(r'[\*\"\}\{\[\]\:]', '', text)
    s = s.replace('Name', '').replace('Product Name', '').strip()
    return s

def parse_front_label(text):
    """解析正面標籤"""
    res = {"name": "", "price": "", "vol": ""}
    # 找品名
    name_match = re.search(r'(?:品名|Name)\s*[:：]?\s*([^\s\n\r(]+)', text, re.IGNORECASE)
    res["name"] = clean_text(name_match.group(1)) if name_match else clean_text(text.split('\n')[0])
    # 找售價
    price_match = re.search(r'(?:售價|\$)\s*[:：]?\s*(\d+)', text)
    res["price"] = price_match.group(1) if price_match else ""
    # 找容量
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text)
    res["vol"] = vol_match.group(1) if vol_match else ""
    return res

def parse_side_label(text):
    """解析側面標籤"""
    res = {"expiry": "", "batch": ""}
    # 效期 MM-YY -> YYYY-MM
    date_match = re.search(r'(?:Sell by date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    # 批號：鎖定 14-268665 或類似格式
    batch_match = re.search(r'(?:Batch no|批號)\s*[:：]?\s*([0-9-]{4,})', text, re.IGNORECASE)
    res["batch"] = batch_match.group(1).strip() if batch_match else ""
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
# 初始化 session state
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

uploaded_files = st.file_uploader("請上傳標籤「正面」與「側面」照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請同時上傳正面與側面照片以確保資訊完整。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner(f'AI 辨識中 (使用 {selected_model})...'):
                    # 辨識正面
                    r1 = model.generate_content(["OCR FRONT label. Extract Name, Price, ML.", imgs[0]])
                    f_data = parse_front_label(r1.text)
                    # 辨識側面
                    r2 = model.generate_content(["OCR SIDE label. Extract Expiry (MM-YY), Batch No.", imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    # 更新至 Session State
                    st.session_state.edit_data = [
                        f_data["name"], f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                    st.success("辨識完成！ (已使用 2/20 當日額度)")
                    # 強制重新運行以更新 UI
                    st.rerun()
            except Exception as e:
                if "429" in str(e):
                    st.error("❌ API 額度已達今日上限 (20 RPD)！請明天再試。")
                else:
                    st.error(f"辨識異常：{e}")

# --- 4. 確認區 (獨立於辨識按鈕外，確保辨識後能持續顯示) ---
st.divider()
st.subheader("📝 確認入庫資訊")

# 使用存放在 session_state 的數據作為預設值
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
            # 清空狀態
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
    else:
        st.warning("⚠️ 請填寫產品名稱後再入庫。")
