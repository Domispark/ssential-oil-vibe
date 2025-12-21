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

# --- 2. 介面設定 ---
st.info("💡 提示：拍攝兩張照片（正面與側面）能大幅提升辨識準確率。")
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

    if st.button("🚀 啟動高精準 AI 辨識"):
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = available_models[0] if available_models else "gemini-1.5-flash"
            model = genai.GenerativeModel(target_model)
            
            with st.spinner('正在分析標籤細節...'):
                # 強化版提示詞
                prompt = """你是一個專業的精油倉儲檢驗員。請根據圖片精確提取資訊：
                1. **產品名稱**：請提取標籤上最醒目的「繁體中文」名稱，不要包含多餘的特殊符號。
                2. **售價**：標籤上 '售價' 或 '$' 後方的數字。
                3. **容量**：標籤上顯示的 ML 數。
                4. **保存期限**：標籤若顯示 'Sell by date: 04-28'，請務必轉為 '2028-04'。
                5. **Batch no.**：請仔細尋找標籤上 'Batch no.:' 後方的字元，包含橫線（如 7-330705）。

                請嚴格依照此格式回傳：名稱,售價,容量,保存期限,Batch no.
                僅回傳一行文字，中間以半角逗號隔開，不要輸出其他說明。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    # 避免 AI 回傳多餘換行
                    clean_res = response.text.strip().replace("\n", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！請在下方校對資訊。")
        except Exception as e:
            st.error(f"辨識出錯：{e}")

# --- 3. 手動輸入/編輯區 ---
st.divider()
st.subheader("📝 確認入庫資訊")
name = st.text_input("產品名稱 (請檢查繁體中文)", value=st.session_state.edit_data[0])
price = st.text_input("售價", value=st.session_state.edit_data[1])
size = st.text_input("容量", value=st.session_state.edit_data[2])
expiry = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])

# 針對 Batch no. 進行額外處理確保索引安全
batch_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
batch = st.text_input("Batch no.", value=batch_val)

if st.button("✅ 確認無誤，正式入庫"):
    final_data = [name, price, size, expiry, batch]
    if save_to_sheet(final_data):
        st.balloons()
        st.success("✅ 成功！資料已寫入 Google Sheets。")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
