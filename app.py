import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests # 改用 requests 直接通訊
import json
from PIL import Image
import base64
import io
from datetime import datetime

st.set_page_config(page_title="精油倉儲 Vibe", page_icon="🌿")
st.title("🌿 精油入庫 (API 直連穩定版)")

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

# 圖片轉 Base64 函數
def encode_image(image):
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# --- 介面設定 ---
uploaded_files = st.file_uploader("選取精油照片 (1~2張)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = ["", "", "", "", ""]

if uploaded_files:
    imgs = []
    for file in uploaded_files:
        img = Image.open(file)
        imgs.append(img)
        st.image(img, use_container_width=True)

    if st.button("🚀 啟動 AI 辨識 (直連模式)"):
        try:
            # 這是直連 Google API 的穩定網址，避開套件的 v1beta 錯誤
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={st.secrets['GEMINI_KEY']}"
            
            # 準備多圖資料
            contents = []
            for img in imgs:
                contents.append({"inline_data": {"mime_type": "image/jpeg", "data": encode_image(img)}})
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "你是一個專業倉管員。請辨識圖片資訊。格式：名稱,售價,容量,保存期限(YYYY-MM),Batch no.。僅回傳文字，逗號隔開。標籤04-28代表2028-04。"},
                        *contents
                    ]
                }]
            }
            
            response = requests.post(api_url, json=payload)
            res_json = response.json()
            
            if response.status_code == 200:
                ai_text = res_json['candidates'][0]['content']['parts'][0]['text']
                st.session_state.edit_data = ai_text.strip().split(",")
                st.success("辨識預填完成！")
            else:
                st.error(f"API 回傳錯誤: {res_json.get('error', {}).get('message', '未知錯誤')}")
        except Exception as e:
            st.error(f"連線失敗: {e}")

# --- 手動編輯與入庫 ---
st.divider()
f1 = st.text_input("產品名稱", value=st.session_state.edit_data[0])
f2 = st.text_input("售價", value=st.session_state.edit_data[1])
f3 = st.text_input("容量", value=st.session_state.edit_data[2])
f4 = st.text_input("保存期限 (YYYY-MM)", value=st.session_state.edit_data[3])
f5_val = st.session_state.edit_data[4] if len(st.session_state.edit_data) > 4 else ""
f5 = st.text_input("Batch no.", value=f5_val)

if st.button("✅ 確認入庫"):
    if save_to_sheet([f1, f2, f3, f4, f5]):
        st.balloons()
        st.success("✅ 存入成功！")
        st.session_state.edit_data = ["", "", "", "", ""]
        st.rerun()
