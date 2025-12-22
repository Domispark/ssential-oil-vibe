import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import time

# --- 頁面與基礎設定 ---
st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (鷹眼精準版)")

# 1. 初始化 AI - 【關鍵改進】直接鎖定最穩定的 1.5 flash 模型
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
    # 不再使用 list_models，直接指定，減少錯誤與額度消耗
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.error("❌ 找不到 GEMINI_KEY，請檢查 Secrets 設定。")

def save_to_sheet(data_list):
    """將資料寫入 Google Sheets 並壓上時間戳記"""
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_list.append(now_str) # F欄: 更新時間
        
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

# --- 2. 介面與圖像處理 ---
st.info("💡 提示：請拍攝清晰的正面標籤與側面批號/日期。AI 會自動排除底部干擾碼。")
uploaded_files = st.file_uploader("選取照片 (建議 2 張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# 初始化暫存資料
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        img = Image.open(file)
        imgs.append(img)
        cols[i].image(img, use_container_width=True, caption=f"照片 {i+1}")

    if st.button("🚀 啟動鷹眼 AI 辨識"):
        with st.spinner('正在進行逐字顯微比對...'):
            try:
                # 【關鍵改進】全新編寫的「防呆+排除」提示詞
                prompt = """你是一位擁有顯微鏡視覺的嚴謹倉管員。請逐字檢核圖片標籤，嚴禁腦補或混淆形近字。

                執行任務：
                1. **產品名稱 (繁體中文)**：
                   - 嚴格區分筆畫：是「雲」杉 (Cloud) 還是「薰」衣草 (Lavender)？是「胡」椒 (Black Pepper) 還是「甜」椒 (Sweet Pepper)？
                   - 僅提取主品名，精準輸出標籤上的漢字。
                2. **售價**：提取標籤上的金額數字（如 560、700）。
                3. **容量**：提取標籤上的 ML 數（如 5ML、10ML）。
                4. **保存期限**：尋找日期資訊，統一轉換為 YYYY-MM 格式（如 2028-04）。
                5. **Batch no. (批號)**：
                   - **最高指令**：請尋找緊跟在文字 "Batch no.:" 或 "批號:" 之後的字串。
                   - **排除干擾**：絕對【忽略】標籤最底部、字體最大的儲位代碼（類似 1-A01-A1-XXXX 格式）。
                   - 真正的批號通常較短，且常位於條碼旁或日期下方（如 7-330705 或 01D-2090-10）。

                輸出格式規範：
                - 僅回傳一行文字，使用半角逗號 (,) 區隔這五項資訊。
                - 順序必須是：名稱,售價,容量,保存期限,Batch no.
                - 若某項資訊完全無法辨識，請填寫 N/A。"""
                
                # 呼叫 AI
                response = model.generate_content([prompt] + imgs)
                
                if response.text:
                    # 資料清洗：移除可能的換行與多餘空白
                    clean_text = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_text.split(",")
                    st.success("✅ 精準辨識完成！請校對下方結果。")
                
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                     st.warning("⚠️ 系統繁忙 (429)。請等待約 30 秒後再試。")
                elif "404" in error_msg:
                     st.error("❌ API 路徑錯誤 (404)。請確保您已重新部署 App。")
                else:
                     st.error(f"AI 通訊失敗：{e}。請直接手動填寫。")

# --- 3. 手動確認與入庫區 ---
st.divider()
st.subheader("📝 入庫資訊最終校對")
# 使用 columns 讓介面更緊湊
c1, c2 = st.columns(2)
f1 = c1.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = c2.text_input("售價", value=st.session_state.edit_data[1] if len(st.session_state.edit_data)>1 else "")

c3, c4 = st.columns(2)
f3 = c3.text_input("容量", value=st.session_state.edit_data[2] if len(st.session_state.edit_data)>2 else "")
f4 = c4.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3] if len(st.session_state.edit_data)>3 else "")

f5 = st.text_input("Batch no. (請確認非底部代碼)", value=st.session_state.edit_data[4] if len(st.session_state.edit_data)>4 else "")

if st.button("✅ 確認無誤，寫入資料庫"):
    # 確保至少有名稱才存入
    if f1 and save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success("🎉 成功！資料與時間戳記已同步至 Google Sheets。")
        # 清空暫存，準備下一筆
        st.session_state.edit_data = ["", "", "", "", ""]
        time.sleep(1) # 稍等一下讓使用者看到成功訊息
        st.rerun()
