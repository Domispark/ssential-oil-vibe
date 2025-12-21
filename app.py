import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])

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
    
    # 只使用這一個最穩定的名稱
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    with st.spinner('AI 分析中...'):
        try:
            response = model.generate_content([
                "辨識精油標籤，回傳格式：名稱,售價,容量,期限(YYYY-MM),批號。僅回傳文字並以逗號隔開。", 
                img
            ])
            
            if response.text:
                result = response.text.strip().split(",")
                st.subheader("🔍 辨識結果")
                st.write(f"**產品：** {result[0]}")
                st.write(f"**售價：** {result[1]}")
                st.write(f"**容量：** {result[2]}")
                st.write(f"**期限：** {result[3]}")

                if st.button("確認存入 Google Sheets"):
                    save_to_sheet(result)
                    st.balloons()
                    st.success("✅ 已儲存！")
        except Exception as e:
            st.error(f"分析失敗：{e}")
