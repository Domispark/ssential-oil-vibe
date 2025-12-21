import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 1. 確保 API KEY 正確讀取
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

img_file = st.camera_input("拍照掃描精油標籤")

if img_file:
    img = Image.open(img_file)
    
    # 嘗試不同的模型名稱，直到成功為止
    model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest']
    
    with st.spinner('AI 正在讀取標籤資訊...'):
        success = False
        for name in model_names:
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content([
                    "辨識此精油標籤，僅回傳格式：產品名稱, 售價, 容量, Sell by Date(YYYY-MM), 批號", 
                    img
                ])
                if response.text:
                    result = response.text.strip().split(",")
                    st.subheader("🔍 辨識預覽")
                    st.write(f"**產品：** {result[0]}")
                    st.write(f"**售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]}")
                    st.write(f"**期限：** {result[3]}")
                    
                    if st.button("確認無誤，傳送到 Google Sheets"):
                        save_to_sheet(result)
                        st.balloons()
                        st.success("✅ 已同步至雲端表格！")
                    success = True
                    break
            except Exception as e:
                continue # 嘗試下一個模型名稱
        
        if not success:
            st.error("❌ AI 辨識失敗。請確認 Secrets 中的 GEMINI_KEY 是否為最新複製的金鑰。")
