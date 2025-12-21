import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime # 引入時間模組

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (相簿優化版)")

# 1. 讀取 Secrets
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

def save_to_sheet(data_list):
    try:
        # 在資料列表最後方加入目前時間
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_list.append(now)
        
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

# --- 介面優化：確保手機端能開啟相簿 ---
st.info("💡 點擊下方按鈕可選擇「拍照」或「從相簿選取」照片。")
# 增加 accept_multiple_files 讓手機觸發多選機制
uploaded_files = st.file_uploader(
    "選取或拍攝精油照片 (1~2張)", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True,
    help="點擊此處開啟系統選單"
)

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 開始整合辨識"):
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        with st.spinner('AI 正在讀取標籤與批號...'):
            try:
                # 終極提示詞：確保日期與批號精確度
                prompt = """你是一個精細的倉庫管理員。請從這幾張圖片中提取準確資訊：
                1. 名稱：產品主名稱。
                2. 售價：金額。
                3. 容量：ML 數。
                4. 保存期限：標籤 '04-28' 轉為 2028-04。
                5. 批號：Batch no. 後方完整字元（如 7-330705）。
                僅回傳格式：名稱,售價,容量,保存期限,批號 (半角逗號隔開)。"""
                
                response = model.generate_content([prompt] + imgs)
                
                if response.text:
                    result = response.text.strip().split(",")
                    st.session_state.current_result = result
                    
                    st.subheader("🔍 整合辨識結果")
                    st.write(f"**產品：** {result[0]} | **售價：** {result[1]}")
                    st.write(f"**容量：** {result[2]} | **期限：** {result[3]}")
                    st.write(f"**批號：** {result[4]}")
            except Exception as e:
                st.error(f"辨識發生錯誤：{e}")

# 確認按鈕
if 'current_result' in st.session_state:
    if st.button("✅ 確認正確，寫入表格並記錄時間"):
        if save_to_sheet(st.session_state.current_result):
            st.balloons()
            st.success("成功！更新時間已同步寫入表格。")
            del st.session_state.current_result
