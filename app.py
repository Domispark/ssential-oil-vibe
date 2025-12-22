import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime
import difflib
import re

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (節能辨識版)")

# --- 步驟 0: 產品資料庫 ---
KNOWN_PRODUCTS = [
    "胡椒薄荷-特級", "胡椒薄荷-一般", "綠薄荷精油", "白雲杉-特級",
    "甜橙精油", "薰衣草精油-高地", "茶樹精油"
]

# 1. 初始化 AI
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("❌ 找不到 GEMINI_KEY")

@st.cache_data(ttl=600)
def get_working_models():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # 優先排在前面的模型順序
        priority = ["2.0-flash-exp", "2.5-flash", "1.5-flash"]
        sorted_models = []
        for p in priority:
            for m in models:
                if p in m.lower():
                    sorted_models.append(m)
        return sorted_models if sorted_models else models
    except Exception:
        return ["models/gemini-2.0-flash-exp", "models/gemini-2.5-flash"]

def save_to_sheet(data_list):
    try:
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

def check_product_name(ai_input_name):
    if ai_input_name in KNOWN_PRODUCTS:
        return True, None
    matches = difflib.get_close_matches(ai_input_name, KNOWN_PRODUCTS, n=1, cutoff=0.4)
    if matches:
        return False, matches[0]
    return False, None

def combine_images(img_list):
    """將上傳的多張圖片水平合併成一張，減少 API 請求次數"""
    widths, heights = zip(*(i.size for i in img_list))
    total_width = sum(widths)
    max_height = max(heights)
    new_im = Image.new('RGB', (total_width, max_height))
    x_offset = 0
    for im in img_list:
        new_im.paste(im, (x_offset, 0))
        x_offset += im.size[0]
    return new_im

# --- 3. 介面與辨識 ---
st.sidebar.subheader("⚙️ 系統診斷")
available_models = get_working_models()
selected_model = st.sidebar.selectbox("當前使用模型", available_models, index=0)

st.info("📌 請同時上傳「正面」與「側面」照片。系統將自動合併辨識以節省配額。")
uploaded_files = st.file_uploader("選取照片 (可多選)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = [Image.open(f) for f in uploaded_files]
    st.image(imgs, width=150)

    if st.button("🚀 啟動節能辨識"):
        if len(uploaded_files) < 2:
            st.warning("⚠️ 建議上傳兩張（正面+側面）以獲得完整資訊。")
        
        try:
            model = genai.GenerativeModel(selected_model)
            with st.spinner('AI 進行影像合併辨識中...'):
                combined_img = combine_images(imgs)
                
                prompt = """
                你是一個專業的倉庫管理員。請分析這張合併圖片（含標籤正面與側面）：
                1. 品名：精油名稱（不含品牌名稱）。
                2. 售價：標籤上帶有 $ 或 售價 字樣的數字。
                3. 容量：帶有 ML 或 ml 的數字。
                4. 效期：尋找 'Sell by date' 或 '效期'，格式 MM-YY 請轉換為 YYYY-MM（例如 04-28 轉為 2028-04）。
                5. 批號：尋找 'Batch no' 或 '批號'，排除 10 位數以上的純數字條碼。

                請僅回覆 JSON 格式，如下：
                {"name": "...", "price": "...", "vol": "...", "expiry": "...", "batch": "..."}
                """
                
                response = model.generate_content([prompt, combined_img])
                
                # 解析 JSON 輸出
                try:
                    # 去除 Markdown 代碼塊標籤
                    clean_text = re.sub(r'```json|```', '', response.text).strip()
                    res = json.loads(clean_text)
                    
                    st.session_state.edit_data = [
                        res.get("name", "辨識失敗"),
                        str(res.get("price", "")),
                        str(res.get("vol", "")),
                        str(res.get("expiry", "")),
                        str(res.get("batch", ""))
                    ]
                except Exception as json_err:
                    st.error(f"JSON 解析失敗，原始回應：{response.text}")
                    
                st.success("辨識完成！ (已節省一次配額使用)")
        except Exception as e:
            st.error(f"辨識異常：{e}")

# --- 4. 確認區 ---
st.divider()
st.subheader("📝 確認入庫資訊")

f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
# 名稱建議邏輯
is_known, suggestion = check_product_name(f1)
if f1 and not is_known and suggestion:
    if st.button(f"💡 名稱不符，要修正為「{suggestion}」嗎？"):
        st.session_state.edit_data[0] = suggestion
        st.rerun()

f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5 = st.text_input("Batch no.", value=st.session_state.edit_data[4])

if st.button("✅ 正式入庫"):
    if f1 and f1 != "辨識失敗":
        if save_to_sheet([f1, f2, f3, f4, f5]):
            st.balloons()
            st.success(f"✅ {f1} 已成功存入 Google Sheet！")
            st.session_state.edit_data = ["", "", "", "", ""]
            st.rerun()
