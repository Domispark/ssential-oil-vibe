import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 1. 讀取 Secrets
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY，請檢查 Secrets 設定。")

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
    
    # --- 關鍵修正：改用最新的模型名稱 ---
    model = genai.GenerativeModel('gemini-2.0-flash-exp') # 改用 Gemini 2.0 Flash 或 3 系列通用版
    
    with st.spinner('AI 正在分析...'):
        try:
            # 傳送圖片給 AI 並明確要求格式
            response = model.generate_content([
                "你是專業倉庫員。辨識圖片標籤資訊。格式：名稱,售價,容量,保存期限(YYYY-MM),批號。僅回傳此格式文字，中間用逗號隔開。", 
                img
            ])
            
            result = response.text.strip().split(",")
            
            # 顯示預覽
            st.success("辨識成功！")
            st.write(f"**產品：** {result[0]}")
            st.write(f"**售價：** {result[1]}")
            st.write(f"**容量：** {result[2]}")
            st.write(f"**期限：** {result[3]}")

            if st.button("確認並存入 Google 表格"):
                save_to_sheet(result)
                st.balloons()
                st.success("✅ 已儲存至雲端表格！")
        except Exception as e:
            st.error(f"分析失敗：{e}")
            st.info("提示：如果還是出現 404，代表模型權限正在開通，請等待 1 分鐘後 Reboot App。")
