import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
import time

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 1. 檢查 Secrets
if "GEMINI_KEY" not in st.secrets:
    st.error("❌ 找不到 GEMINI_KEY，請檢查 Secrets 設定。")
    st.stop()

genai.configure(api_key=st.secrets["GEMINI_KEY"])

def save_to_sheet(data_list):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
        sheet.append_row(data_list)
        return True
    except Exception as e:
        st.error(f"表格寫入失敗：{e}")
        return False

# 手機拍照元件
img_file = st.camera_input("拍照掃描精油標籤")

if img_file:
    img = Image.open(img_file)
    
    # 嘗試所有可能的模型路徑名稱
    model_options = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-1.5-flash-latest"]
    
    with st.spinner('AI 正在嘗試多種路徑辨識中...'):
        success = False
        last_error = ""
        
        for model_name in model_options:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([
                    "你是專業倉庫員。辨識圖片標籤資訊。格式：名稱,售價,容量,保存期限(YYYY-MM),批號。僅回傳此格式文字，中間用半角逗號隔開。", 
                    img
                ])
                
                if response and response.text:
                    result = response.text.strip().split(",")
                    st.success(f"辨識成功！(使用模型: {model_name})")
                    st.write(f"**產品：** {result[0]}")
                    st.write(f"**售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]}")
                    st.write(f"**期限：** {result[3]}")

                    if st.button("確認無誤，存入 Google 表格"):
                        if save_to_sheet(result):
                            st.balloons()
                            st.success("✅ 已同步至雲端表格！")
                    success = True
                    break
            except Exception as e:
                last_error = str(e)
                continue
        
        if not success:
            st.error(f"分析失敗：所有模型路徑均不可用。最後一個錯誤：{last_error}")
            st.info("💡 提示：這代表您的 API Key 權限還在開通中，請等待 1-5 分鐘後點擊右下角 Reboot App。")
