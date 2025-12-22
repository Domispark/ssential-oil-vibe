import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (自我診斷穩定版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

# --- 核心：模型自動偵測邏輯 ---
@st.cache_data(ttl=600)
def get_working_models():
    """探測目前 API Key 真正支援的模型清單"""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 優先排序 flash 模型
        models.sort(key=lambda x: 'flash' not in x.lower())
        return models
    except Exception as e:
        st.error(f"模型清單獲取失敗: {e}")
        return ["gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro"]

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
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型路徑", available_models)

st.info(f"💡 目前連線路徑：`{selected_model}`。若辨識失敗，請嘗試從左側選單切換模型。")

uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, use_container_width=True)

    if st.button("🚀 啟動高精準 AI 辨識"):
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('正在逐字校對標籤...'):
                # 強化辨識指令：針對「雲」vs「薰」、「絲柏」vs「綠絲柏」進行修正
                prompt = """你是一位極度嚴謹的植物學倉管員。請逐字辨識標籤文字，嚴禁「腦補」不存在的字：
                1. 名稱：精準讀取標籤上的繁體中文。
                   - 注意：是「雲杉」(Cloud Spruce) 還是「薰衣草/薰香」？請看清筆畫。
                   - 注意：若是「絲柏」就只寫「絲柏」，不可擅自加「綠」字。
                2. 售價：標籤金額數字。
                3. 容量：ML 數。
                4. 保存期限：'04-28' 轉換為 '2028-04'。
                5. Batch no.：完整批號（包含橫線）。
                回傳格式：名稱,售價,容量,保存期限,Batch no. (逗號隔開)"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    st.session_state.edit_data = response.text.strip().split(",")
                    st.success(f"辨識完成！使用模型：{selected_model}")
        except Exception as e:
            st.warning(f"AI 辨識路徑錯誤：{e}。請嘗試切換左側模型路徑，或手動填寫。")

# --- 3. 手動確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
f5 = st.text_input("Batch no.", value=f5_val)

if st.button("✅ 確認入庫"):
    if save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success("成功！資料已寫入表格。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
