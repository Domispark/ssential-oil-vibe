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
st.title("🌿 精油入庫 (2.5 Flash 終極相容版)")

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
    """自動過濾不支援圖片的模型並排序"""
    try:
        available_names = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name
                # 排除不支援影像的模型 (TTS, Live, Audio-only)
                if any(x in name.lower() for x in ["tts", "live", "audio", "embed"]):
                    continue
                available_names.append(name)
        
        # 優先級：2.5-flash > 3-flash > 1.5-flash
        priority = ["2.5-flash", "3-flash", "1.5-flash"]
        sorted_models = []
        for p in priority:
            for name in available_names:
                if p in name.lower() and name not in sorted_models:
                    sorted_models.append(name)
        
        return sorted_models if sorted_models else available_names
    except Exception:
        return ["models/gemini-2.5-flash", "models/gemini-1.5-flash"]

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

# --- 步驟 1: 輔助函式 ---
def clean_ai_text(text):
    """強力移除 JSON 殘留符號"""
    if not text: return ""
    bad_chars = ['"', '{', '}', '[', ']', ':', ',', 'json', '`', ';']
    temp = text
    for char in bad_chars:
        temp = temp.replace(char, ' ')
    return temp.strip()

def check_product_name(ai_input_name):
    if ai_input_name in KNOWN_PRODUCTS:
        return True, None
    matches = difflib.get_close_matches(ai_input_name, KNOWN_PRODUCTS, n=1, cutoff=0.4)
    if matches:
        return False, matches[0]
    return False, None

# --- 步驟 2: 資料解析函式 ---
def parse_front_label(text):
    """處理正面：品名、售價、容量"""
    res = {"name": "", "price": "", "vol": ""}
    clean_t = clean_ai_text(text)
    
    # 1. 品名
    name_match = re.search(r'品名\s*([^\s\n]+)', clean_t)
    if name_match:
        res["name"] = name_match.group(1).strip()
    else:
        lines = [l.strip() for l in clean_t.split('\n') if l.strip()]
        if lines: res["name"] = lines[0]

    # 2. 售價
    price_match = re.search(r'(?:售價|\$)\s*(\d+)', clean_t)
    if price_match:
        res["price"] = price_match.group(1)
        
    # 3. 容量
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', clean_t)
    if vol_match:
        res["vol"] = vol_match.group(1)
        
    return res

def parse_side_label(text):
    """處理側面：效期、批號"""
    res = {"expiry": "", "batch": ""}
    # 側面需保留冒號與斜線以便解析日期與批號
    raw_t = text.replace('"', '').replace('`', '').strip()
    
    # 1. 效期 (YYYY-MM)
    date_match = re.search(r'(?:date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', raw_t, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    
    # 2. 批號 (強化提取數字，避開 "no")
    # 專門抓取 "Batch no.:" 或 "批號:" 後方的非空白字串
    batch_match = re.search(r'(?:Batch\s*no\.?|批號)\s*[:：]?\s*([A-Z0-9-]+)', raw_t, re.IGNORECASE)
    if batch_match:
        res["batch"] = batch_match.group(1).strip()
            
    return res

# --- 3. 介面與辨識 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

st.info("📌 第一張：標籤正面 (含品名、售價)\n📌 第二張：標籤側面 (含批號、效期)")
uploaded_files = st.file_uploader("選取照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請同時上傳兩張照片（正面與側面）。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner(f'AI 使用 {selected_model} 分析中...'):
                    # 辨識正面
                    p1 = "OCR FRONT label. Extract: 品名, 售價, 容量. Output ALL text."
                    r1 = model.generate_content([p1, imgs[0]])
                    f_data = parse_front_label(r1.text)
                    
                    # 辨識側面
                    p2 = "OCR SIDE label. Extract: Sell by date, Batch no. Output ALL text."
                    r2 = model.generate_content([p2, imgs[1]])
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
