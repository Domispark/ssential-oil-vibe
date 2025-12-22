import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (自動適配穩定版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

# --- 核心：動態獲取模型，確保不出現 404 ---
@st.cache_data(ttl=600)
def get_best_model():
    """自動偵測目前帳號最穩定的模型路徑"""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 優先尋找 2.5-flash，若無則找 1.5-flash
        best_match = next((m for m in models if "2.5-flash" in m), None)
        if not best_match:
            best_match = next((m for m in models if "1.5-flash" in m), "models/gemini-1.5-flash")
        return best_match
    except Exception:
        return "models/gemini-1.5-flash"

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
current_model = get_best_model()
st.sidebar.success(f"✅ 已連接模型：{current_model}")

uploaded_files = st.file_uploader("選取精油照片 (正面標籤 + 側面日期)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動鷹眼 AI 辨識"):
        try:
            model = genai.GenerativeModel(current_model)
            with st.spinner(f'正在使用 {current_model} 進行深度辨識...'):
                # 強化指令：針對您的測試結果（雲杉/薰杉、甜椒/胡椒）進行修正
                prompt = """你是一位極度嚴謹的植物學倉管員。請逐字檢核標籤，嚴禁腦補形近字：
                1. **產品名稱**：請精準辨識標籤上的繁體中文。
                   - 注意：是「白雲杉」而非「白薰杉」。
                   - 注意：是「胡椒薄荷」而非「甜椒薄荷」。
                   - 必須確保品名第一個字百分之百正確。
                2. **售價**：標籤上的金額。
                3. **容量**：標籤上的 ML 數。
                4. **保存期限**：日期 '04-28' 轉換為 '2028-04'。
                5. **Batch no.**：務必尋找 "Batch no.:" 之後的批號（如 7-330705）。
                   - 【絕對忽略】標籤底部最大的儲位代碼（如 1-A01-A1-XXXX）。

                僅回傳格式：名稱,售價,容量,保存期限,Batch no. (逗號隔開)"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！")
        except Exception as e:
            st.error(f"連線失敗：{e}。建議再次 Reboot App。")

# --- 3. 手動確認區 ---
st.divider()
st.subheader("📝 入庫資訊檢查")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1] if len(st.session_state.edit_data)>1 else "")
f3 = st.text_input("容量", value=st.session_state.edit_data[2] if len(st.session_state.edit_data)>2 else "")
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3] if len(st.session_state.edit_data)>3 else "")
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認無誤，正式入庫"):
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success("✅ 存入成功！時間戳記已同步更新。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
