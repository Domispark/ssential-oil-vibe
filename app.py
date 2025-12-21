import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (極致穩定版)")

# 1. 讀取 Secrets
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
st.info("💡 您可以直接手動輸入資訊，或拍照嘗試讓 AI 協助填表。")
uploaded_files = st.file_uploader("上傳/拍攝精油照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# 初始化暫存資料
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"圖片 {i+1}")

    if st.button("🚀 嘗試 AI 自動辨識"):
        try:
            # 直接使用最穩定的模型名稱，不做循環測試
            model = genai.GenerativeModel('gemini-1.5-flash')
            with st.spinner('嘗試辨識中...'):
                prompt = "你是倉管員，請辨識照片並回傳格式：名稱,售價,容量,保存期限(YYYY-MM),Batch no.。僅回傳文字，逗號隔開。"
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.edit_data = response.text.strip().split(",")
                    st.success("AI 辨識成功！請校對下方欄位。")
        except Exception as e:
            st.warning("AI 目前連線不穩，請直接在下方手動輸入資訊進行入庫。")

# --- 3. 手動輸入區 (即便 AI 報錯，這裡依然可以工作) ---
st.divider()
st.subheader("📝 資訊確認與手動輸入")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認入庫 (同步至 Google 表格)"):
    final_row = [f1, f2, f3, f4, f5]
    if any(final_row):
        if save_to_sheet(final_row):
            st.balloons()
            st.success("✅ 入庫成功！時間戳記已自動產生。")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
    else:
        st.warning("請至少填寫一個欄位。")
