import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (多圖整合版)")

# 1. 讀取 Secrets
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

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
        st.error(f"寫入表格失敗：{e}")
        return False

# --- 介面設定 ---
st.info("💡 請選取 2 張照片：一張正面標籤，一張側面/底部日期。")
uploaded_files = st.file_uploader("選取或拍攝精油照片", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 開始全方位辨識"):
        # 自動搜尋可用模型以避開 404
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = available_models[0] if available_models else "gemini-1.5-flash"
        except:
            target_model = "gemini-1.5-flash"

        model = genai.GenerativeModel(target_model)
        
        with st.spinner(f'正在使用 {target_model} 整合分析中...'):
            try:
                # 提示詞引導 AI 從多張圖提取資訊
                prompt = "你是一個精油倉管員。請從這幾張圖片中找出：1.產品名稱 2.售價 3.容量 4.保存期限(YYYY-MM) 5.批號。僅回傳這五項資訊，中間用半角逗號隔開，不要有任何標題或廢話。"
                response = model.generate_content([prompt] + imgs)
                
                if response.text:
                    result = response.text.strip().split(",")
                    st.session_state.current_result = result # 暫存結果
                    
                    st.subheader("🔍 整合辨識結果")
                    st.write(f"**產品：** {result[0]}")
                    st.write(f"**售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]}")
                    st.write(f"**期限：** {result[3]}")
                    if len(result) > 4:
                        st.write(f"**批號：** {result[4]}")
                else:
                    st.error("AI 未回傳有效文字。")
            except Exception as e:
                st.error(f"辨識發生錯誤：{e}")

# 確認存入按鈕
if 'current_result' in st.session_state:
    if st.button("✅ 確認正確，寫入 Google Sheets"):
        if save_to_sheet(st.session_state.current_result):
            st.balloons()
            st.success("成功存入雲端表格！")
            del st.session_state.current_result
