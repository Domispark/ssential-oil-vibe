import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (恢復穩定版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

# 核心：保留診斷功能，解決您截圖中的 429/404 問題
@st.cache_data(ttl=600)
def get_working_models():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        models.sort(key=lambda x: 'flash' not in x.lower())
        return models
    except Exception:
        return ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

def save_to_sheet(data_list):
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_list.append(now_str) # F欄: 自動更新時間
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
        sheet.append_row(data_list) # 寫入表格
        return True
    except Exception as e:
        st.error(f"寫入表格失敗：{e}")
        return False

# --- 2. 介面設定 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型路徑", available_models)

st.info(f"💡 目前連線路徑：`{selected_model}`。")
uploaded_files = st.file_uploader("選取照片 (建議正面+側面各一張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在分析標籤細節...'):
                # 針對您的反饋進行最終提示詞修正
                prompt = """你是一位極度細心的倉管員。請從圖中提取精確資訊：
                1. **名稱**：標籤第一行「品名:」後的繁體中文。
                   - 注意：是「胡椒」薄荷，不是甜椒。
                   - 注意：是「白雲杉」，不是白薰杉。
                2. **售價**：標籤上的金額數字（如 700）。
                3. **容量**：標籤上的 ML 數。
                4. **保存期限**：尋找 'Sell by date'，格式轉為 YYYY-MM（如 2028-04）。
                5. **Batch no.**：務必尋找 "Batch no.:" 之後的批號（如 7-330705）。
                   - **絕對忽略**：標籤最底部最大字的儲位代碼（如 1-A01-A1-XXXX）。

                僅回傳格式：名稱,售價,容量,保存期限,Batch no.
                請僅回傳一行文字，逗號隔開。若無資訊則填寫 N/A。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！")
        except Exception as e:
            st.warning(f"AI 暫時無法辨識：{e}。請直接手動填寫下方欄位。")

# --- 3. 確認與入庫區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1] if len(st.session_state.edit_data)>1 else "")
f3 = st.text_input("容量", value=st.session_state.edit_data[2] if len(st.session_state.edit_data)>2 else "")
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3] if len(st.session_state.edit_data)>3 else "")
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認正確，正式入庫"):
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success("✅ 存入成功！")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
