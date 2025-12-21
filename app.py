import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (AI 辨識 + 手動修正版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

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

# --- 2. 介面設定 ---
st.info("💡 拍照/選取後，AI 會自動填入下方欄位，您也可以手動修改。")
uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# 準備編輯欄位（預設為空）
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 啟動 AI 辨識"):
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = available_models[0] if available_models else "gemini-1.5-flash"
            model = genai.GenerativeModel(target_model)
            
            with st.spinner('AI 正在分析並填表...'):
                prompt = """你是一個專業倉管。請精準辨識圖片中的繁體中文名稱與數字。
                格式：名稱,售價,容量,保存期限(YYYY-MM),批號。
                標籤 '04-28' 請轉為 2028-04。僅回傳文字，並以半角逗號隔開。"""
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.edit_data = response.text.strip().split(",")
        except Exception as e:
            st.error(f"辨識出錯：{e}")

# --- 3. 手動輸入/編輯區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
name = st.text_input("產品名稱", value=st.session_state.edit_data[0])
price = st.text_input("售價", value=st.session_state.edit_data[1])
size = st.text_input("容量", value=st.session_state.edit_data[2])
expiry = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
batch = st.text_input("批號", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認無誤，正式入庫"):
    final_data = [name, price, size, expiry, batch]
    if save_to_sheet(final_data):
        st.balloons()
        st.success("成功！資料已寫入 Google Sheets。")
        # 清除暫存
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
