# 變更記錄

## [1.2.0] - 2026-06-13

### 新增
- 維基功能：AI 自動整理專案文件，產生維基百科風格知識頁面
- 維基支援暫停/繼續/停止控制 + 進度條
- 維基標注產生模型名稱 + 刪除重建
- 查詢功能接入 LLM（回答模式+研究模式都用 LLM 整理）
- 帳號管理重設計：使用者列表 + 編輯彈窗（修改角色/密碼/刪除）
- 查詢頁面改為 Perplexity 風格搜尋介面
- 專案多選改為膠囊按鈕（Chip）選取
- 上傳頁面統一拖曳區 + 檔案預覽
- 進度頁面卡片式佈局 + 狀態徽章
- LLM 多供應者支援（Ollama/OpenAI/Anthropic/Google/DeepSeek/NVIDIA NIM/自訂）
- LLM 連線測試自動列出可用模型
- URL 自動補全 http:// 前綴
- Windows .bat 腳本
- GitHub Actions CI

### 改進
- start.sh 端口檢查改用 grep 避免 awk 跳脫問題
- LLM 測試錯誤訊息不再顯示 undefined
- README 強調跨主機優勢、與 RAGFlow/Dify/LightRAG 比較

## [1.1.0] - 2026-06-12

### 新增
- Server 啟動時醒目顯示區域網路 IP 位址，方便 User 端連線
- User 首次設定精靈：瀏覽器內設定 Server IP，不需手動編輯 .env
- User 端修改密碼功能（帳號管理頁面）
- User 端登出功能
- Server API 認證中介層（token 驗證 + 24 小時過期）
- Server 日誌輪替（超過 50MB 自動輪替，最多保留 5 個）
- HTTPS 支援（自動產生自簽憑證）
- User start.sh 自動開啟瀏覽器
- User README Windows 使用指南（WSL）
- CHANGELOG.md

### 修復
- Server main.py 缺少 `import httpx`（導致 AI 自動整理功能崩潰）
- rebuild_index.sh 傳入不存在的參數（TypeError）

### 改進
- Server start.sh 輸出格式改為醒目區塊
- User 前端 token 持久化（localStorage），刷新頁面不用重新登入

## [1.0.0] - 2026-06-02

### 初始版本
- Server 端：FastAPI + SQLite + MinerU + RapidOCR + CLIP + BLIP
- User 端：FastAPI proxy + 繁體中文 Web UI
- 一鍵安裝/啟動/停止/更新/測試腳本
- 帳號系統（admin/user/readonly）
- Evidence Package 搜尋架構
- 多專案管理 + 專案模板
- 檔案上傳（PDF/TXT/JPG/JPEG/PNG/EPUB）
- 背景處理佇列
- 備份/還原/重建
- 搜尋紀錄 + 匯出（JSON/CSV/Markdown）
- 書籍校閱器（PDF 疊圖、OCR 文字、區塊檢查）
