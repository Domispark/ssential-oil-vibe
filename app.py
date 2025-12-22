import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (深度校對版)")

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
    except Exception as e:
        return ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

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
st.sidebar.subheader("⚙️ 系統設定")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models)

uploaded_files = st.file_uploader("上傳/拍攝精油標籤 (建議正面+側面各一張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動高精準 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('AI 正在精確掃描標籤...'):
                # 最終強化版提示詞：加入排除邏輯
                prompt = """你是一位極度嚴謹的精油倉管員。請從圖中提取精確資訊：
                1. **產品名稱**：標籤上的繁體中文（如：白雲杉-特級）。
                2. **售價**：標籤上的數字（如：700）。
                3. **容量**：標籤上的 ML 數。
                4. **保存期限**：尋找 'Sell by date'，轉換為 YYYY-MM（如 2028-04）。
                5. **Batch no.**：這非常重要！請務必尋找文字 'Batch no.:' 之後的號碼（例如：7-330705）。
                   - **警告**：請【忽略】標籤底部最大字的儲位代碼（如 1-A01-A1-0254）。
                   - **目標**：批號通常在條碼旁邊或保存期限下方，格式通常包含橫線。

                僅回傳格式：名稱,售價,容量,保存期限,Batch no.
                請僅回傳一行文字，逗號隔開。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！請校對下方欄位。")
        except Exception as e:
            st.warning(f"AI 辨識異常：{e}")

# --- 3. 手動確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
f5 = st.text_input("Batch no.", value=f5_val)

if st.button("✅ 確認正確，正式入庫"):
    if any([f1, f2, f3, f4, f5]):
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success("✅ 入庫成功！更新時間已記錄至試算表。")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
