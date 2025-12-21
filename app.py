import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (雙圖辨識版)")

# 1. 初始化 AI (使用你剛才測試成功的金鑰)
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def save_to_sheet(data_list):
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
    sheet.append_row(data_list)

# --- 改為多檔案上傳介面 ---
st.info("💡 請拍攝或上傳 2 張照片：一張正面標籤，一張日期細節。")
uploaded_files = st.file_uploader("選取精油照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    # 預覽上傳的照片
    cols = st.columns(len(uploaded_files))
    imgs = []
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 開始全方位辨識"):
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        with st.spinner('AI 正在整合兩張照片的資訊...'):
            try:
                # 同時發送多張圖片給 AI
                prompt = "你是一個精油倉管。請綜合這兩張圖片的資訊，回傳格式：名稱,售價,容量,保存期限(YYYY-MM),批號。僅回傳文字並以半角逗號隔開。"
                response = model.generate_content([prompt] + imgs)
                
                if response.text:
                    result = response.text.strip().split(",")
                    st.subheader("🔍 整合辨識結果")
                    st.write(f"**產品：** {result[0]} | **售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]} | **期限：** {result[3]}")
                    st.write(f"**批號：** {result[4]}")

                    if st.button("確認存入 Google Sheets"):
                        save_to_sheet(result)
                        st.balloons()
                        st.success("✅ 已儲存至雲端表格！")
            except Exception as e:
                st.error(f"辨識失敗：{e}")
