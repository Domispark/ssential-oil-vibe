import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (繁中強化版)")

# --- 1. 側邊欄配置 ---
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

# --- 2. 核心功能函式 ---
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def clean_extracted_value(text):
    """強力移除雜訊，保留純淨的繁體中文與數據"""
    if not text: return ""
    # 移除 Markdown、括號、冒號及 AI 常見的前言 (如 Based on...)
    s = re.sub(r'[\*\"\}\{\[\]\:\#]', '', text)
    s = re.sub(r'(Based on|text|found|Product|Name|品名|售價|容量|毫升)', '', s, flags=re.IGNORECASE)
    return s.strip()

def parse_front_label(text):
    """解析正面：鎖定繁中品名、售價、容量"""
    res = {"name": "", "price": "", "vol": ""}
    
    # 1. 品名：鎖定繁體中文關鍵字
    name_match = re.search(r'品名\s*[:：]?\s*([\u4e00-\u9fa5-]+)', text)
    if name_match:
        res["name"] = clean_extracted_value(name_match.group(1))
    else:
        # 備案：抓取第一行非英文的繁中內容
        lines = [l.strip() for l in text.split('\n') if any('\u4e00' <= char <= '\u9fa5' for char in l)]
        if lines: res["name"] = clean_extracted_value(lines[0])

    # 2. 售價 (抓取三位數以上的純數字)
    price_match = re.search(r'(?:售價|零售價|\$)\s*[:：]?\s*(\d{3,})', text)
    if price_match: res["price"] = price_match.group(1)

    # 3. 容量
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text, re.IGNORECASE)
    if vol_match: res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    """解析側面：鎖定效期、長數字批號"""
    res = {"expiry": "", "batch": ""}
    # 1. 效期 MM-YY
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"

    # 2. 批號 (強力鎖定包含橫線的長數字，避開 no 字眼)
    batch_match = re.search(r'(?:Batch|批號)\s*(?:no\.?)?\s*[:：]?\s*([0-9-]{6,})', text, re.IGNORECASE)
    if batch_match: 
        res["batch"] = batch_match.group(1).strip()
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

# --- 3. 主要作業區 ---
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

uploaded_files = st.file_uploader("上傳照片 (左：正面，右：側面)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動繁中精準辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請同時上傳正面與側面照片。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner('AI 正在讀取繁體中文標籤...'):
                    # 提示詞優化：強調繁體中文與純文字輸出
                    p1 = "請讀取精油標籤正面。請找出「品名」、「零售價」與「容量」。請只回傳找到的文字，不要任何解釋。"
                    r1 = model.generate_content([p1, imgs[0]])
                    f_data = parse_front_label(r1.text)
                    
                    p2 = "請讀取精油標籤側面。請找出「Sell by date」與「Batch no」。請回傳原始數字與日期，不要解釋。"
                    r2 = model.generate_content([p2, imgs[1]])
                    s_data = parse_side_label(r2.text)
                    
                    st.session_state.edit_data = [
                        f_data["name"], f_data["price"], f_data["vol"],
                        s_data["expiry"], s_data["batch"]
                    ]
                st.success("辨識完成！")
                st.rerun()
            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 今日免費額度已用罄，請明天再試或切換模型。")
                else:
                    st.error(f"辨識異常：{e}")

# --- 4. 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量 (ML)", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 確認無誤，正式入庫"):
    if f1 and f1 != "辨識失敗":
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success(f"✅ {f1} 已入庫！")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
