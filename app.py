import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

# 1. 從 Streamlit Secrets 讀取金鑰 (稍後在 Streamlit Cloud 設定)
genai.configure(api_key=st.secrets["GEMINI_KEY"])

def save_to_sheet(data_list):
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    # 讀取 Secrets 裡的 JSON 憑證
    creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    # 讀取 Secrets 裡的表格 ID
    sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
    sheet.append_row(data_list)

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 手機拍照元件
img_file = st.camera_input("拍照掃描精油標籤")

if img_file:
    img = Image.open(img_file)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    with st.spinner('AI 正在讀取標籤資訊...'):
        # AI 辨識指令
        response = model.generate_content([
            "你是一個倉庫管理員。請辨識此精油標籤，並僅回傳以下格式文字（中間用半角逗號隔開，不要有其他廢話）：產品名稱, 售價, 容量, Sell by Date(YYYY-MM), 批號", 
            img
        ])
        
        result = response.text.strip().split(",")
        
    # 預覽辨識結果
    st.subheader("🔍 辨識預覽")
    col1, col2 = st.columns(2)
    with col1:
        st.image(img, width=200)
    with col2:
        st.write(f"**產品：** {result[0]}")
        st.write(f"**售價：** {result[1]}")
        st.write(f"**容量：** {result[2]}")
        st.write(f"**期限：** {result[3]}")

    if st.button("確認無誤，傳送到 Google Sheets"):
        try:
            save_to_sheet(result)
            st.balloons()
            st.success("✅ 資料已同步至雲端表格！")
        except Exception as e:
            st.error(f"儲存失敗：{e}")
