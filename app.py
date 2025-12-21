if st.button("🚀 啟動深度視覺辨識"):
        try:
            # 關鍵修正 1：直接指定模型名稱，不要用 list_models() 消耗額度
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            with st.spinner('正在精準校對繁體中文與代碼...'):
                prompt = """你是一位極其細心的倉庫管理專家。請徹底掃描圖片中的所有文字資訊，並遵循以下規範：
                1. **產品名稱**：請精準辨識標籤上的「繁體中文」。特別區分筆畫相近字（例如：是「雲杉」而非「薰香」）。只保留主名稱，去掉無關符號。
                2. **售價**：標籤上的金額數字。
                3. **容量**：標籤上的容量。
                4. **保存期限**：若標籤有 'Sell by date: 04-28'，代表 2028-04。請輸出為 YYYY-MM 格式。
                5. **Batch no.**：請找出 'Batch no.:' 之後的完整字串，必須包含連字號（例如：7-330705）。

                請嚴格依此順序回傳：名稱,售價,容量,保存期限,Batch no.
                僅回傳一行結果，中間用半角逗號隔開。"""
                
                response = model.generate_content([prompt] + imgs)
                if response.text:
                    clean_res = response.text.strip().replace("\n", "").replace(" ", "")
                    st.session_state.edit_data = clean_res.split(",")
                    st.success("辨識完成！")
        except Exception as e:
            if "429" in str(e):
                st.error("⚠️ API 額度已達上限或請求太頻繁，請等待約 1 分鐘後再試。")
            else:
                st.error(f"辨識出錯：{e}")
