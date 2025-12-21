import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (最終修復版)")

# 1. 初始化 AI - 使用標準穩定路徑
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
st.info("💡 提示：若 AI 仍連線失敗，請參考照片直接手動修改下方欄位。")
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

    if st.button("🚀 執行深度視覺辨識"):
        try:
            # 關鍵修正：直接指定模型，避免呼叫 list_models() 觸發配額限制
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            with st.spinner('AI 正在讀取標籤細節...'):
                prompt = """你是一位精確的倉庫檢驗員。請嚴格辨識標籤上的繁體中文。
                1. 名稱：精確讀取品名，不可添加字詞（例如：「絲柏」不可辨識為「綠絲柏」）。
                2. 售價：標籤金額數字。
                3. 容量：標籤顯示的 ML 數。
                4. 保存期限：'04-28' 代表 2028-04。
                5. Batch no.：請精準找出 Batch no. 之後的字元，包含橫線（如 7-330705）。
                回傳格式：名稱,售價,容量,保存期限,Batch no.
                僅回傳一行文字，逗號隔開。不要任何解釋。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識預填完成！請校對。")
        except Exception as e:
            if "429" in str(e):
                st.warning("⚠️ 額度用盡，請 30 秒後再試。")
            else:
                st.error(f"AI 通訊失敗 ({e})。請手動填寫。")

# --- 3. 手動編輯與入庫區 ---
st.divider()
st.subheader("📝 入庫資訊檢查與修正")
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
        st.success("✅ 存入成功！時間戳記已更新。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
