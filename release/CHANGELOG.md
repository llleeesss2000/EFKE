# 變更記錄

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
