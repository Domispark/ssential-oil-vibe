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

# 動態偵測模型以避免 404
@st.cache_data(ttl=600)
def get_best_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
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
st.sidebar.success(f"✅ 已連接：{current_model}")

uploaded_files = st.file_uploader("選取精油照片 (正面標籤 + 側面日期)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動邏輯校對辨識"):
        try:
            model = genai.GenerativeModel(current_model)
            with st.spinner('正在根據您的規則校對資訊...'):
                # 強化版 Prompt：加入使用者提供的兩大核心邏輯
                prompt = """你是一位專業倉管員。請根據以下兩張照片的內容提取資訊：
                
                【重要規則】
                1. **品名邏輯**：標籤的第一行文字即為正確的產品名稱（繁體中文）。
                   - 例如：第一行是「胡椒薄荷」，就不可辨識為「甜椒薄荷」。
                   - 例如：第一行是「白雲杉」，就不可辨識為「白薰杉」。
                2. **關聯邏輯**：保存期限 (Sell by date) 與 批號 (Batch no.) 必定出現在同一張照片的相鄰位置。
                   - 請尋找 "Sell by date" 旁邊的 "Batch no." 欄位。
                3. **排除邏輯**：標籤最底部最大字的「儲位代碼」（如 1-A01...）絕對不是 Batch no.，請略過它。
                
                【提取內容】
                - 名稱：提取標籤第一行。
                - 售價：標籤上的金額數字。
                - 容量：標籤顯示的 ML 數。
                - 保存期限：格式轉為 YYYY-MM（如 04-28 轉為 2028-04）。
                - Batch no.：Sell by date 附近的批號字串。

                格式：名稱,售價,容量,保存期限,Batch no. (逗號隔開)"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("校對辨識完成！")
        except Exception as e:
            st.error(f"連線失敗：{e}")

# --- 3. 手動確認區 ---
st.divider()
st.subheader("📝 入庫資訊檢查")
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
