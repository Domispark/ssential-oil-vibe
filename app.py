import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (高精準辨識版)")

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

# 介面設定
st.info("💡 拍照時請保持環境明亮，AI 會優先分析圖片中的繁體中文標籤。")
uploaded_files = st.file_uploader("選取精油照片 (可選取1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 執行高精準 AI 辨識"):
        try:
            # 鎖定最強的 Vision 模型
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            with st.spinner('正在進行深度視覺分析...'):
                # 強化版提示詞：加入字體特徵描述與邏輯檢查
                prompt = """你是一個具備多年經驗的精油倉庫管理員，專長是辨識精密產品標籤。
                請仔細分析提供的圖片，並遵循以下規則：
                1. **中文名稱**：標籤上通常有最大的繁體中文。請確保每個筆畫都辨識正確（例如：區分「雪」與「雲」）。
                2. **日期邏輯**：標籤上的 '04-28' 必須轉換為 '2028-04'。
                3. **Batch no.**：請找出標籤上 Batch no. 字樣後的代碼，包含橫線（如 7-330705）。
                4. **售價與容量**：僅提取數字，不需貨幣符號。
                
                輸出格式：名稱,售價,容量,保存期限,Batch no.
                請僅回傳這一行文字，中間用半角逗號隔開。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.edit_data = response.text.strip().split(",")
        except Exception as e:
            st.error(f"辨識出錯：{e}")

# --- 3. 手動修正區 (欄位已更名) ---
st.divider()
st.subheader("📝 入庫資訊檢查")
name = st.text_input("產品名稱 (請檢查繁體中文)", value=st.session_state.edit_data[0])
price = st.text_input("售價", value=st.session_state.edit_data[1])
size = st.text_input("容量", value=st.session_state.edit_data[2])
expiry = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
batch = st.text_input("Batch no.", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認正確並送入 Google Sheets"):
    final_data = [name, price, size, expiry, batch]
    if save_to_sheet(final_data):
        st.balloons()
        st.success("成功！資料已完整入庫。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
