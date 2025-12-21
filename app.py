import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化系統")

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

# --- 2. 介面設定：新增輸入模式切換 ---
mode = st.radio("選擇輸入方式：", ["相簿/檔案上傳", "開啟視訊鏡頭"], horizontal=True)

imgs = []
if mode == "相簿/檔案上傳":
    uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    if uploaded_files:
        cols = st.columns(len(uploaded_files))
        for i, file in enumerate(uploaded_files):
            img = Image.open(file)
            imgs.append(img)
            cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")
else:
    camera_file = st.camera_input("請對準精油標籤拍照")
    if camera_file:
        img = Image.open(camera_file)
        imgs.append(img)

# 初始化暫存資料
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if imgs:
    if st.button("🚀 啟動高精準 AI 辨識"):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            with st.spinner('正在分析標籤...'):
                prompt = """你是一個精細的倉庫管理員。請從圖片中提取資訊：
                1. 名稱：請精準辨識繁體中文名稱（區分雲杉與薰香）。
                2. 售價：標籤上的金額數字。
                3. 容量：ML 數。
                4. 保存期限：標籤 '04-28' 代表 2028-04。
                5. Batch no.：請完整找出 Batch no. 字樣後的字元，必須包含橫線（如 7-330705）。
                回傳格式：名稱,售價,容量,保存期限,Batch no.
                僅回傳一行文字，逗號隔開。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！請在下方檢查後存入。")
        except Exception as e:
            st.error(f"辨識出錯：{e}")

# --- 3. 手動編輯與入庫區 ---
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
    if save_to_sheet(final_data):
        st.balloons()
        st.success("✅ 成功！資料與時間已同步寫入 Google Sheets。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
