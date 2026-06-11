# Evidence-First Knowledge Engine Server

這是 Server 端部署包，負責原始檔保存、metadata、背景處理、Evidence Search、RAG 查詢、備份、還原與重建。

最高原則：

```text
Evidence First.
Everything Traceable.
Everything Rebuildable.
```

## 快速開始

```bash
cd release/Server
./install.sh
./start.sh
```

部署包可以搬到其他資料夾或其他主機。`start.sh` 會檢查 `.venv` 是否仍指向目前資料夾；如果發現 venv 是從別處搬來的，會自動移到 `.venv.broken.YYYYMMDD_HHMMSS` 並重建，不會修改 `server_data/` 原始資料。

如果你是用檔案管理器雙擊，請改用這三個腳本，視窗不會閃退：

```bash
./install_keep_open.sh
./start_keep_open.sh
./status_keep_open.sh
```

啟動後會顯示：

```text
Server URL: http://127.0.0.1:8000
API URL: http://127.0.0.1:8000/docs
```

停止：

```bash
./stop.sh
```

測試：

```bash
./test.sh
```

## 預設帳號

```text
帳號：admin
密碼：12345
```

首次登入會提醒修改密碼。角色保留 admin、user、readonly。

## 資料位置

預設資料存在：

```text
release/Server/server_data/
```

重要子目錄：

```text
originals/  原始檔，黃金來源，不應被 AI 修改
derived/    OCR、圖片、chunk、索引等可重建資料
backups/    備份檔
metadata.db SQLite metadata
```

## 支援檔案

```text
PDF
TXT
JPG
JPEG
PNG
EPUB
```

PDF/TXT/EPUB 會建立文字 Evidence。PDF/EPUB 圖片會嘗試擷取並保存來源 trace。若 EPUB 是掃描圖片型電子書，圖片會先保存成 Evidence asset；OCR、圖片 embedding、表格/公式模型尚未接入時，對應工作階段會標為 `not_implemented`，不會假裝完成。

## API

主要 API：

```text
/auth/login
/auth/logout
/users
/projects
/upload
/jobs
/search
/rag/query
/files
/evidence/{chunk_id}
/settings
/admin/rebuild
/admin/backup
/admin/restore
```

刪除相關 API：

```text
DELETE /projects/{project_id}  刪除專案，移除相關工作、metadata、索引與專案原始檔目錄
DELETE /jobs/{job_id}          移除工作進度紀錄，不刪原始檔與索引
```

查詢找不到足夠 Evidence 時，回答固定為：

```text
資料庫中未找到足夠證據。
```

## 備份、還原、重建

建立備份：

```bash
./backup.sh
```

還原：

```bash
./restore.sh ./server_data/backups/evidence_backup_YYYYMMDD_HHMMSS.tar.gz
```

重建索引：

```bash
./rebuild_index.sh
```

只要保留原始檔、metadata backup 與處理設定，就能重建衍生資料。

## 設定

複製自 `.env.example` 的 `.env` 可調整：

```text
SERVER_PORT
SERVER_DATA_DIR
QDRANT_URL
RERANKER_ENABLED
LLM_BASE_URL
LLM_MODEL
```

第一版內建 SQLite lexical search + reranker，可直接使用。外部 Qdrant、OCR、embedding、reranker、LLM 模型可之後接入，衍生資料可重建。
