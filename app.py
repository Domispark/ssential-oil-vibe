import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (最終完美版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY，請檢查 Secrets 設定。")

def save_to_sheet(data_list):
    try:
        # 自動加入更新時間 (最後一欄)
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
st.info("💡 點擊下方可「現場拍照」或「從相簿選取」1~2張照片。")
uploaded_files = st.file_uploader(
    "選取精油照片 (正面標籤 + 側面日期)", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True
)

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 開始整合辨識"):
        try:
            # 自動搜尋可用模型以避開 404
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = available_models[0] if available_models else "gemini-1.5-flash"
            model = genai.GenerativeModel(target_model)
            
            with st.spinner('AI 整合辨識中...'):
                prompt = """你是一個精細的倉庫管理員。請從圖片中提取資訊：
                1. 名稱：產品主名稱。
                2. 售價：標籤上的金額數字。
                3. 容量：ML 數。
                4. 保存期限：標籤顯示 '04-28' 代表 2028-04。
                5. 批號：Batch no. 後方的完整字元（如 7-330705）。
                格式：名稱,售價,容量,保存期限,批號。僅回傳文字，並以半角逗號隔開。"""
                
                response = model.generate_content([prompt] + imgs)
                
                if response.text:
                    result = response.text.strip().split(",")
                    st.session_state.current_result = result
                    
                    st.subheader("🔍 整合辨識預覽")
                    st.write(f"**產品：** {result[0]} | **售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]} | **期限：** {result[3]}")
                    st.write(f"**批號：** {result[4]}")
        except Exception as e:
            st.error(f"辨識發生錯誤：{e}")

# 3. 確認寫入按鈕
if 'current_result' in st.session_state:
    if st.button("✅ 確認正確，寫入表格"):
        if save_to_sheet(st.session_state.current_result):
            st.balloons()
            st.success("成功！資料與時間已存入 Google Sheets。")
            del st.session_state.current_result
