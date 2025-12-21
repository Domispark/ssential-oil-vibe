import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

# 設定頁面
st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 1. 設定 AI 金鑰
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("請在 Secrets 中設定 GEMINI_KEY")

def save_to_sheet(data_list):
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
    sheet.append_row(data_list)

# 手機拍照元件
img_file = st.camera_input("拍照掃描精油標籤")

if img_file:
    img = Image.open(img_file)
    
    # 這是最穩定的呼叫方式，不加 models/ 前綴
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    with st.spinner('AI 正在讀取標籤資訊...'):
        try:
            # 傳送圖片給 AI
            response = model.generate_content([
                "你是一個倉庫管理員。請辨識此精油標籤，並僅回傳以下格式文字（中間用半角逗號隔開，不要有其他廢話）：產品名稱, 售價, 容量, Sell by Date(YYYY-MM), 批號", 
                img
            ])
            
            # 解析結果
            result = response.text.strip().split(",")
            
            # 顯示辨識結果預覽
            st.subheader("🔍 辨識預覽")
            st.write(f"**產品：** {result[0]}")
            st.write(f"**售價：** {result[1]}")
            st.write(f"**容量：** {result[2]}")
            st.write(f"**期限：** {result[3]}")

            if st.button("確認無誤，傳送到 Google Sheets"):
                save_to_sheet(result)
                st.balloons()
                st.success("✅ 資料已同步至雲端表格！")
                
        except Exception as e:
            st.error(f"錯誤：{e}")
            st.info("提示：如果出現 404，請確認 Secrets 中的 GEMINI_KEY 是最新從 AI Studio 複製的那串。")
