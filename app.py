import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

# 設定頁面資訊
st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫自動化")

# 1. 檢查並設定 AI 金鑰
if "GEMINI_KEY" not in st.secrets:
    st.error("❌ 找不到 GEMINI_KEY，請檢查 Streamlit Secrets 設定。")
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
    
    # 使用目前最穩定的模型名稱
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    
    with st.spinner('AI 正在讀取標籤資訊...'):
        try:
            response = model.generate_content([
                "你是一個倉庫管理員。請辨識此精油標籤，並僅回傳以下格式文字（中間用半角逗號隔開，不要有其他廢話）：產品名稱, 售價, 容量, Sell by Date(YYYY-MM), 批號", 
                img
            ])
            
            if response.text:
                result = response.text.strip().split(",")
                # 預覽辨識結果
                st.subheader("🔍 辨識預覽")
                st.write(f"**產品：** {result[0]}")
                st.write(f"**售價：** {result[1]}")
                st.write(f"**容量：** {result[2]}")
                st.write(f"**期限：** {result[3]}")

                if st.button("確認無誤，傳送到 Google Sheets"):
                    if save_to_sheet(result):
                        st.balloons()
                        st.success("✅ 資料已同步至雲端表格！")
            else:
                st.warning("⚠️ AI 辨識不到文字，請換個角度再拍一次。")
                
        except Exception as e:
            st.error(f"⚠️ AI 辨識發生錯誤：{e}")
            st.info("提示：請檢查 Gemini API Key 是否正確填寫在 Secrets 中，且該 Key 是否已啟用。")
