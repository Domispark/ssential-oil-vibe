import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (環境修復版)")

# 1. 初始化 AI (使用最穩定配置)
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def save_to_sheet(data_list):
    try:
        # 自動加入更新時間 (最後一欄)
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
st.info("💡 提示：若 AI 仍顯示 404，請參考照片直接在下方手動填寫並正式入庫。")
uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 執行視覺辨識"):
        try:
            # 強制指定模型，避免路徑誤跳
            model = genai.GenerativeModel('gemini-1.5-flash')
            with st.spinner('正在與 AI 通訊...'):
                prompt = """你是倉管員，請讀取標籤：
                1. 名稱：品名（區分雲杉/絲柏/薰香）。
                2. 售價：金額。
                3. 容量：ML數。
                4. 保存期限：'04-28' 轉為 2028-04。
                5. Batch no.：含橫線的完整批號。
                格式：名稱,售價,容量,保存期限,Batch no. (逗號隔開)"""
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.edit_data = response.text.strip().split(",")
        except Exception as e:
            st.warning(f"AI 目前無法通訊 ({e})，請手動填寫下方資訊。")

# --- 3. 手動輸入區 (即使 AI 斷線也能運作) ---
st.divider()
st.subheader("📝 入庫資訊檢查")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
f5 = st.text_input("Batch no.", value=f5_val)

if st.button("✅ 確認無誤，正式入庫"):
    final_data = [f1, f2, f3, f4, f5]
    if any(final_data) and save_to_sheet(final_data):
        st.balloons()
        st.success("✅ 存入成功！時間戳記已同步更新。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
