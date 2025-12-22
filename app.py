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
st.title("🌿 精油入庫 (分工辨識版 V2)")

# --- 步驟 0: 產品資料庫 ---
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級",
    "胡椒薄荷-一般",
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

# --- 步驟 2: 精準資料解析函式 ---
def parse_front_label(text):
    """處理第一張圖：品名、售價、容量"""
    res = {"name": "", "price": "", "vol": ""}
    
    # 品名：尋找「品名」關鍵字後的繁體中文，過濾 * 號
    name_match = re.search(r'品名\s*[:：]?\s*([^\n\r*]+)', text)
    if name_match:
        res["name"] = name_match.group(1).strip()
    
    # 售價：尋找 $ 符號後的數字，允許中間有空格
    price_match = re.search(r'(?:\$|售價|零售價)\s*[:：]?\s*(\d[\d\s]*\d)', text)
    if price_match:
        res["price"] = re.sub(r'\D', '', price_match.group(1))
        
    # 容量：尋找數字後跟 ML 或毫升
    vol_match = re.search(r'(\d+)\s*(?:ML|ml|毫升)', text, re.IGNORECASE)
    if vol_match:
        res["vol"] = vol_match.group(1)
    return res

def parse_side_label(text):
    """處理第二張圖：效期、批號"""
    res = {"expiry": "", "batch": ""}
    
    # 效期：捕捉 MM-YY 格式並轉為 20YY-MM
    date_match = re.search(r'(?:Sell\s*by\s*date|效期)\s*[:：]?\s*(\d{2})[-/](\d{2})', text, re.IGNORECASE)
    if date_match:
        mm, yy = date_match.groups()
        res["expiry"] = f"20{yy}-{mm}"
    
    # 批號：尋找 Batch no 後面的編號，排除長條碼 (10碼以上純數字)
    batch_match = re.search(r'Batch\s*no\.?\s*[:：\s]*([A-Z0-9-]+)', text, re.IGNORECASE)
    if batch_match:
        candidate = batch_match.group(1).strip()
        if not (candidate.isdigit() and len(candidate) > 9):
            res["batch"] = candidate
    return res

# --- 3. 介面與辨識邏輯 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

st.info("📌 操作指南：請上傳兩張照片。\n第一張：標籤正面 (含品名、售價)\n第二張：標籤側面 (含批號、效期)")
uploaded_files = st.file_uploader("選取照片 (請依序上傳正面與側面)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    # 顯示預覽並確保順序
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=200, caption=["第一張 (正面)", "第二張 (側面)"] if len(imgs) == 2 else None)

    if st.button("🚀 啟動分段辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 請上傳兩張照片以獲得完整資訊。")
        else:
            try:
                model = genai.GenerativeModel(selected_model)
                with st.spinner('AI 正在分層掃描標籤...'):
                    # 辨識正面
                    r1 = model.generate_content(["Please perform OCR on this label front. Extract product name, price with $, and volume ML.", imgs[0]])
                    front_data = parse_front_label(r1.text)
                    
                    # 辨識側面
                    r2 = model.generate_content(["Please perform OCR on this label side. Extract 'Sell by date' MM-YY and 'Batch no'.", imgs[1]])
                    side_data = parse_side_label(r2.text)
                    
                    # 更新至 Session State
                    st.session_state.edit_data = [
                        front_data["name"] if front_data["name"] else "辨識失敗",
                        front_data["price"],
                        front_data["vol"],
                        side_data["expiry"],
                        side_data["batch"]
                    ]
                    st.success("辨識完成！請確認下方資訊。")
            except Exception as e:
                st.error(f"辨識異常：{e}")

# --- 4. 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

current_name = st.session_state.edit_data[0]
is_known, suggestion = check_product_name(current_name)
if current_name and not is_known and suggestion:
    if st.button(f"💡 建議更正為：{suggestion}"):
        st.session_state.edit_data[0] = suggestion
        st.rerun()

# 顯示輸入欄位
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 確認正確，正式入庫"):
    if f1 and f1 != "辨識失敗":
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success(f"✅ {f1} 已成功入庫！")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
    else:
        st.error("請填寫正確的產品名稱後再入庫。")
