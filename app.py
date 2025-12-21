import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (高精準辨識版)")

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

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
st.info("💡 建議：拍攝一張正面大圖與一張側面細節圖（包含 Batch no. 與日期）。")
uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 啟動深度視覺辨識"):
        try:
            # 獲取可用模型
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = available_models[0] if available_models else "gemini-1.5-flash"
            model = genai.GenerativeModel(target_model)
            
            with st.spinner('正在精準校對繁體中文與代碼...'):
                # 最終強化提示詞：強調字體筆畫與批號格式
                prompt = """你是一位極其細心的倉庫管理專家。請徹底掃描圖片中的所有文字資訊，並遵循以下規範：
                1. **產品名稱**：請精準辨識標籤上的「繁體中文」。特別區分筆畫相近字（例如：是「雲杉」而非「薰香」）。只保留主名稱，去掉無關符號。
                2. **售價**：標籤上的金額數字（例如：700）。
                3. **容量**：標籤上的容量（例如：5ML 或 6ML）。
                4. **保存期限**：若標籤有 'Sell by date: 04-28'，代表 2028-04。請輸出為 YYYY-MM 格式。
                5. **Batch no.**：請找出 'Batch no.:' 之後的完整字串，必須包含連字號（例如：7-330705）。

                請嚴格依此順序回傳：名稱,售價,容量,保存期限,Batch no.
                僅回傳一行結果，中間用半角逗號隔開。若資訊不明請填寫 N/A。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    # 清洗數據並寫入 session_state
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！請在下方檢查後存入。")
        except Exception as e:
            st.error(f"辨識出錯：{e}")

# --- 3. 手動編輯與入庫區 ---
st.divider()
st.subheader("📝 入庫資訊最終檢查")
name = st.text_input("產品名稱 (請檢查繁體中文是否正確)", value=st.session_state.edit_data[0])
price = st.text_input("售價", value=st.session_state.edit_data[1])
size = st.text_input("容量", value=st.session_state.edit_data[2])
expiry = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])

# 安全獲取 Batch no.
batch_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
batch = st.text_input("Batch no.", value=batch_val)

if st.button("✅ 確認正確，寫入雲端表格"):
    final_data = [name, price, size, expiry, batch]
    if save_to_sheet(final_data):
        st.balloons()
        st.success("✅ 資料與更新時間已同步寫入 Google Sheets！")
        # 清除暫存以便下一筆入庫
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
