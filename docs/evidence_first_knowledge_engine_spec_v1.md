# Evidence-First Personal Knowledge Engine 新專案規格書 v1.0

> 交給 Codex / AI Coding Agent 使用。  
> 請依照本規格重新建立新專案，不要沿用舊專案爛尾架構。  
> 本專案不是一般 RAG，也不是單純 PDF 問答系統，而是長期可用、可驗證、可重建、可擴充的個人知識引擎。

---

## 0. 專案核心定位

本專案目標：

```text
Evidence-First Personal Knowledge Engine
```

最高原則：

```text
Evidence First.
Everything Traceable.
Everything Rebuildable.
```

意思是：

1. 有證據才回答。
2. 找不到足夠證據時，必須回答：「資料庫中未找到足夠證據」。
3. 不能讓 LLM 自由猜測專業資料。
4. 每個回答都必須能追溯到原始檔案、頁碼、區塊、圖片、表格、公式或段落。
5. 原始資料不可被 AI 修改或覆蓋。
6. 所有衍生資料都必須可以重建。
7. AI 可以自動整理知識，但必須寫入獨立 AI Knowledge Layer，並有完整 audit log 與 rollback。
8. 系統必須支援目前約 3000 本 PDF，未來擴充到幾萬本書、百萬級圖片。

---

## 1. 使用情境與資料類型

主要用途：

```text
化工
程式設計
法律
房地產
投資
其他專業知識
```

這些領域高正確性需求很高，因此系統必須以證據為核心，而不是以生成回答為核心。

支援資料類型：

```text
PDF
TXT
JPG
JPEG
PNG
```

文件可能包含：

```text
純文字 PDF
掃描 PDF
書本掃描
圖文混排
表格
公式
工程圖
流程圖
程式碼
圖片
```

---

## 2. 系統分端

整體架構必須分成兩端：

```text
Server 端
User 端
```

---

### 2.1 Server 端用途

Server 端負責重型與核心資料處理：

```text
資料儲存
原始檔管理
Metadata DB
Job Queue
OCR / MinerU / Layout Analysis
圖片擷取
圖片 Caption
文字 Embedding
圖片 Embedding
Qdrant / Vector DB
Hybrid Search
Reranker
Evidence Package
API
背景任務
備份與重建
```

Server 端可部署在：

```text
HX370
或未來任一主機
```

---

### 2.2 User 端用途

User 端負責使用者操作：

```text
前端網頁
檔案上傳
查詢介面
工作進度查看
回答模式 / 研究模式
系統設定
LLM / API / Key 設定
資料存放位置設定
帳號管理
```

User 端可部署在：

```text
使用者筆電
桌機
另一台電腦
同一台 Server
```

User 端前端網頁 Port 固定預設：

```text
6161
```

---

## 3. 必須產生的部署包

必須建立：

```text
release/
├── Server/
└── User/
```

---

## 4. Server 端部署包要求

Server 端目錄：

```text
release/Server/
├── install.sh
├── start.sh
├── stop.sh
├── update.sh
├── test.sh
├── backup.sh
├── restore.sh
├── rebuild_index.sh
├── .env.example
├── README.md
├── requirements-server.txt
└── app/
```

要求：

1. Server 程序必須安裝在獨立 venv。
2. venv 位置：

```text
release/Server/.venv
```

3. 一鍵安裝：

```bash
./install.sh
```

4. 一鍵啟動：

```bash
./start.sh
```

5. 一鍵停止：

```bash
./stop.sh
```

6. 一鍵更新：

```bash
./update.sh
```

7. 一鍵測試：

```bash
./test.sh
```

8. 不允許污染系統 Python。
9. 不允許要求使用者手動 pip install 一堆東西。
10. install.sh 必須檢查：
   - Python 版本
   - 磁碟空間
   - Port 是否被占用
   - 必要依賴
   - 資料目錄是否可寫
11. start.sh 必須顯示：
   - Server URL
   - API URL
   - 資料存放位置
   - Log 路徑
   - Job Queue 狀態
12. Server README 必須用繁體中文寫給使用者看，不要只寫給工程師看。

---

## 5. User 端部署包要求

User 端目錄：

```text
release/User/
├── install.sh
├── start.sh
├── stop.sh
├── update.sh
├── test.sh
├── .env.example
├── README.md
├── requirements-user.txt
└── app/
```

要求：

1. User 程序必須安裝在獨立 venv。
2. venv 位置：

```text
release/User/.venv
```

3. User 端前端網頁 Port 固定：

```text
6161
```

4. 一鍵安裝：

```bash
./install.sh
```

5. 一鍵啟動：

```bash
./start.sh
```

6. 一鍵停止：

```bash
./stop.sh
```

7. 一鍵測試：

```bash
./test.sh
```

8. 啟動後顯示：

```text
User Web UI: http://127.0.0.1:6161
```

9. User README 必須清楚說明：
   - 如何設定 Server 地址
   - 如何設定 LLM 地址
   - 如何設定 API Key
   - 如何選擇量化資料存在 Server 或 User
   - 如何搬移到其他電腦

---

## 6. User 端 .env.example

User 端必須提供 `.env.example`：

```env
# User Web UI
USER_WEB_HOST=0.0.0.0
USER_WEB_PORT=6161

# Server API
SERVER_API_URL=http://127.0.0.1:8000

# LLM Provider
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3-coder-next:q8_0

# Embedding Provider
EMBEDDING_PROVIDER=server
EMBEDDING_MODEL=

# Quantized Data Location
# 可選：server / user
QUANTIZED_DATA_LOCATION=server

# 若選 user，量化資料存在 User 端此目錄
USER_DATA_DIR=./user_data

# Auth
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=12345

# Language
UI_LANGUAGE=zh-TW
```

---

## 7. Server 端 .env.example

Server 端必須提供 `.env.example`：

```env
# Server API
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Storage
SERVER_DATA_DIR=./server_data
ORIGINAL_FILES_DIR=./server_data/originals
DERIVED_DATA_DIR=./server_data/derived
BACKUP_DIR=./server_data/backups

# Database
DATABASE_URL=sqlite:///./server_data/metadata.db

# Queue
REDIS_URL=redis://127.0.0.1:6379/0

# Vector DB
VECTOR_DB=qdrant
QDRANT_URL=http://127.0.0.1:6333

# Reranker
RERANKER_ENABLED=true
RERANKER_MODEL=
RERANKER_TOP_N=100
RERANKER_TOP_K=10
RERANKER_DEVICE=auto

# OCR / MinerU
OCR_ENGINE=auto
MINERU_ENABLED=true
OCR_DEVICE=auto

# Image Embedding
IMAGE_EMBEDDING_ENABLED=true
IMAGE_EMBEDDING_MODEL=
IMAGE_EMBEDDING_DEVICE=auto

# LLM
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=

# Auth
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=12345

# Language
UI_LANGUAGE=zh-TW
```

---

## 8. 量化資料存放位置

做好後的量化資料 / 衍生資料可選擇存在：

```text
Server 端
User 端
```

### 8.1 Server 端存放

適用：

```text
固定主機
長期知識庫
多裝置存取
大量資料
```

資料存在：

```text
release/Server/server_data/
```

### 8.2 User 端存放

適用：

```text
可攜式資料
使用者想移動到其他電腦
離線使用
```

資料存在：

```text
release/User/user_data/
```

User 端若選擇本地存放，必須支援：

1. 保存 metadata cache。
2. 保存本地向量索引或可攜式量化資料。
3. 可移動到其他電腦。
4. 保留 source trace 對應原始檔。
5. 支援匯入 / 匯出。
6. User 端 README 必須清楚說明如何搬移資料。

---

## 9. 語言與介面要求

整個專案能使用中文就使用中文。

要求：

```text
前端介面：繁體中文
錯誤訊息：繁體中文
README：繁體中文
安裝提示：繁體中文
按鈕：繁體中文
狀態文字：繁體中文
```

英文可保留於程式碼、變數、API，但使用者看到的內容以繁體中文為主。

---

## 10. 帳號與權限

必須實作帳號管理。

預設帳號：

```text
帳號：admin
密碼：12345
```

首次登入必須提醒修改密碼。

角色：

```text
admin
user
readonly
```

權限：

```text
admin：所有功能
user：上傳、查詢、建立專案
readonly：只能查詢
```

---

## 11. User 端前端功能

User 端 Web UI 必須包含：

```text
登入頁
專案管理
檔案上傳
工作進度
查詢頁
回答模式 / 研究模式切換
搜尋結果
來源檢視
圖片檢視
表格檢視
公式檢視
系統設定
LLM 設定
資料存放位置設定
帳號管理
備份 / 還原入口
```

---

## 12. 查詢模式

查詢頁必須提供：

```text
[回答模式] [研究模式]
```

### 12.1 回答模式

說明文字：

```text
快速整理結論，仍會附上來源。適合一般問題。
```

特性：

1. 結論優先。
2. 較快。
3. 仍必須引用來源。
4. 找不到證據不得猜測。

### 12.2 研究模式

說明文字：

```text
先列出證據，再比較整理，最後給結論與不確定性。適合化工、程式、法律等專業查詢。
```

特性：

1. 先列 Evidence。
2. 再整理比較。
3. 最後給結論。
4. 顯示不確定性。
5. 適合專業資料。

---

## 13. 上傳與背景處理

支援上傳：

```text
PDF
TXT
JPG
JPEG
PNG
```

流程：

```text
使用者上傳
↓
建立 Job
↓
前端可關閉
↓
Server Worker 繼續處理
↓
重新打開前端可看到進度
```

不得依賴瀏覽器保持開啟。

---

## 14. 工作進度追蹤

不要只顯示百分比。

必須顯示階段：

```text
upload
metadata
layout_analysis
ocr
image_extract
image_caption
image_embedding
table_extract
formula_extract
chunk
text_embedding
rerank_ready
index
ai_suggestion
done
failed
not_implemented
```

每個階段包含：

```text
狀態
開始時間
結束時間
錯誤訊息
處理數量
目前檔案
Log
```

嚴禁 placeholder handler 標記 completed。未實作必須標記 `not_implemented`。

---

## 15. 資料保留策略

### 15.1 永久保留

原始檔為黃金來源，建議永久保留：

```text
PDF
TXT
JPG
JPEG
PNG
metadata
hash
upload record
```

### 15.2 可重建資料

以下視為可重建：

```text
OCR 結果
Layout 結果
Chunk
Text Embedding
Image Caption
Image Embedding
Table Extraction
Formula Extraction
Knowledge Graph
Reranker cache
```

### 15.3 必須支援重新處理

```text
重新 OCR
重新 Layout Analysis
重新 Chunk
重新 Text Embedding
重新 Image Embedding
重新 Index
重新 AI Suggestion
```

不得要求重新上傳原始檔。

---

## 16. 掃描 PDF 與圖文混排

系統必須支援：

```text
Layout Analysis
Block Detection
OCR
Image Extraction
Table Extraction
Formula Extraction
```

每頁必須切成 Block：

```text
Text Block
Image Block
Table Block
Formula Block
Title Block
Header/Footer Block
```

每個 Block 必須保存：

```text
document_id
page_number
block_id
block_type
bbox
reading_order
source_path
confidence
```

---

## 17. 圖片擷取與圖片量化

掃描頁中的圖片區塊必須裁切存檔：

```text
page_001_image_001.png
page_001_image_002.png
page_002_image_001.png
```

圖片命名必須可追溯到：

```text
原始檔
頁碼
區塊
座標
```

所有圖片預設都要量化，不做重要圖片篩選。

原因：

1. Image Embedding 佔用空間遠小於原圖。
2. 未來無法預測哪些圖片重要。
3. 重跑百萬張圖片成本高。
4. Evidence-First 系統需要完整圖片檢索能力。

每張圖片必須建立：

```text
原圖
OCR
Caption
Image Embedding
Metadata
Source Trace
```

圖片搜尋必須支援：

```text
文字查圖片
圖片找相似圖片
圖片 OCR 搜尋
圖片 Caption 搜尋
圖片 Evidence 引用
```

---

## 18. 多模態 Evidence Package

搜尋命中文字、圖片、表格或公式時，不能只送單一 Chunk 給 LLM。

必須建立 Context Expansion Engine。

命中 Block 後，自動擴展：

```text
同頁 Block
前後頁 Block
同章節 Block
關聯圖片
關聯表格
關聯公式
```

組成：

```text
Evidence Package
```

Evidence Package 包含：

```text
文字
圖片
表格
公式
來源
頁碼
區塊座標
信心度
```

---

## 19. 搜尋架構

系統必須支援全部內容搜尋，不是只搜尋書名或摘要。

搜尋流程：

```text
Query
↓
Project / Domain Filter
↓
Metadata Filter
↓
Hybrid Search
  - Full-text Search / BM25
  - Vector Search
  - Image Search
  - Caption Search
  - OCR Search
↓
Merge Candidates Top-N
↓
Context Expansion
↓
Reranker
↓
Top-K Evidence Package
↓
Answer
```

---

## 20. Reranker 必須內建

Reranker 是核心功能，不是未來選配。

用途：

```text
全文搜尋與向量搜尋先取 Top-N
Reranker 再判斷哪些 evidence 真正回答問題
```

預設開啟。

設定：

```env
RERANKER_ENABLED=true
RERANKER_MODEL=
RERANKER_TOP_N=100
RERANKER_TOP_K=10
RERANKER_DEVICE=auto
```

Search API 必須回傳：

```text
original_rank
rerank_score
source_file
page_number
block_id
chunk_id
project
evidence_text
evidence_assets
```

---

## 21. Evidence-First 回答規則

1. 只能根據 Top-K Evidence 回答。
2. 必須引用來源。
3. 必須標示頁碼 / 區塊 / 圖片。
4. 找不到足夠證據時回答：

```text
資料庫中未找到足夠證據。
```

5. 不得自由補充未檢索到的內容。
6. 專業問題必須優先使用研究模式。
7. 化工、法律、程式設計類問題不得猜測。

---

## 22. Source Trace / Provenance

每個資料單位都必須可追溯。

追溯鏈：

```text
Answer
↓
Evidence Package
↓
Block / Chunk / Image / Table / Formula
↓
Page
↓
Original File
```

每個 Chunk / Block 必須保存：

```text
file_id
document_id
project_id
page_number
block_id
paragraph_id
char_start
char_end
bbox
chunk_id
chunk_version
ocr_version
embedding_version
source_hash
```

---

## 23. 專案 / 專業領域隔離

必須支援多專案：

```text
化工
程式設計
法律
房地產
投資
自訂
```

每個專案應有：

```text
獨立 metadata
獨立 collection / namespace
獨立索引
獨立權限
獨立設定
```

也必須支援跨專案搜尋：

```text
☑ 化工
☑ 程式設計
□ 法律
```

---

## 24. 專案模板

建立專案時提供模板：

```text
化工
程式設計
法律
房地產
投資
自訂
```

不同模板可有不同：

```text
Chunk 設定
Metadata 欄位
OCR 策略
Reranker 策略
Source Ranking
```

---

## 25. Source Ranking / 資料可信度

必須支援來源可信度分級：

```text
A 級：教科書、原廠文件、技術手冊
B 級：論文、標準文件
C 級：技術文章、部落格
D 級：論壇、AI 生成內容
```

搜尋與回答時優先引用高可信度來源。

---

## 26. AI 自動整理層

AI 可以自動發現：

```text
標籤
摘要
關聯
實體
概念
```

但不能修改原始資料。

必須寫入獨立 AI Knowledge Layer。

資料表 / 檔案可包含：

```text
ai_tags
ai_summaries
ai_relations
ai_entities
ai_suggestions
```

每筆必須包含：

```text
id
project_id
source_file_id
source_chunk_id
source_block_id
content
relation_type
confidence
model_name
prompt_version
created_at
batch_id
status
```

status：

```text
active
disabled
deleted
```

---

## 27. AI 寫入 Audit Log 與 Rollback

每次 AI 寫入都必須記錄：

```text
時間
模型
prompt version
根據哪些來源
寫入什麼
confidence
batch_id
```

必須支援：

```text
依 batch 刪除
依模型刪除
依時間刪除
依 project 刪除
停用 AI 產生的關聯
```

如果發現 AI 污染，必須可回滾。

---

## 28. Knowledge Graph

Knowledge Graph 可以延後至 V2，但 V1 必須預留 schema。

V1 預留：

```text
Entity
Relation
Confidence
Source
Evidence
Batch
Status
```

V1 不得因為 Graph 尚未完成而阻塞核心 Evidence Search。

V1 優先順序：

```text
Upload
OCR
Layout
Chunk
Embedding
Image Embedding
Hybrid Search
Reranker
Citation
Evidence Package
```

---

## 29. Duplicate Detection

必須使用 SHA256 或等效 hash 偵測重複檔案。

重複檔案策略：

```text
提示已存在
允許建立新版本
允許跳過
允許覆蓋 metadata 但不覆蓋原始檔
```

---

## 30. 多版本管理

支援：

```text
同一本書不同版本
同一文件不同修訂
同一 PDF 重新上傳
```

不能互相覆蓋。

需保存：

```text
version_id
source_hash
upload_time
metadata
processing_version
```

---

## 31. 版本化處理流程

必須保存：

```text
OCR version
Layout model version
Chunk version
Embedding model version
Image embedding model version
Reranker version
Prompt version
Processing date
```

原因：未來模型升級後搜尋結果可能不同，必須可追蹤。

---

## 32. 刪除 / 封存策略

支援：

```text
Archive
Delete
```

Archive：

```text
不參與搜尋
保留原始檔與 metadata
可恢復
```

Delete：

```text
刪除原始檔
刪除 metadata
刪除向量
刪除 AI 關聯
需要 admin 權限
需要二次確認
```

---

## 33. 災難復原

必須做到：

即使以下資料壞掉：

```text
Qdrant
Postgres / SQLite
Knowledge Graph
Embedding
OCR
Chunk
```

只要保留：

```text
原始檔
metadata backup
processing config
```

就能重建整個索引。

必須提供：

```text
backup.sh
restore.sh
rebuild_index.sh
```

---

## 34. 匯出功能

搜尋結果可匯出：

```text
Markdown
JSON
PDF
CSV
```

匯出內容包含：

```text
問題
答案
Evidence
來源
頁碼
圖片
表格
rerank score
查詢時間
使用模式
```

---

## 35. Search History

保存搜尋紀錄：

```text
query
project
mode
filters
results
answer
timestamp
user
```

可重新執行。

---

## 36. API 需求

Server 端至少提供 API：

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
/evidence
/settings
/admin/rebuild
/admin/backup
/admin/restore
```

---

## 37. 技術建議

可使用：

```text
FastAPI
SQLite / PostgreSQL
Redis / RQ / Celery
Qdrant
LightRAG 作為 Retrieval Layer 參考或底盤
MinerU / OCR pipeline
PyMuPDF
PaddleOCR / Surya OCR
Reranker model
Ollama / Qwen
```

但不要為了使用某套工具犧牲 Evidence-First。

---

## 38. Rust / C++ 高效能模組策略

整體系統不建議全部用 C++ 重寫。

主架構建議：

```text
Python / FastAPI：API、Web、Job Queue、OCR / MinerU 調度、LLM 整合
Qdrant：向量搜尋
SQLite / PostgreSQL：metadata
Rust：高效能工具層
```

Rust 可用於：

```text
SHA256 / 重複檔案偵測
大量檔案掃描
Chunk 前處理
Block / metadata 批次處理
大量 JSONL / Parquet 轉換
圖片與檔案索引輔助工具
```

Rust 模組應以：

```text
CLI
或 Python binding
```

提供。

不要讓整個系統綁死在 Rust 或 C++。

---

## 39. 第一版必須完成的真正流程

第一版必須完成真正可用流程：

```text
登入
建立專案
上傳 PDF/TXT/圖片
背景處理
版面分析
OCR
圖片擷取
文字 embedding
圖片 caption
圖片 embedding
Hybrid Search
Reranker
Evidence Answer
Citation
進度追蹤
匯出結果
```

不要只做：

```text
Queue framework
Placeholder handler
空 API
```

---

## 40. Codex 實作要求

Codex 必須遵守：

1. 不要建立空 placeholder 後宣稱完成。
2. 每個模組完成後必須有 test.sh 或單元測試。
3. 每個 API 必須可實際呼叫。
4. 每個處理流程必須能跑一個 sample 檔案。
5. README 必須寫給使用者看，不是寫給工程師看。
6. 所有使用者看到的文字盡量繁體中文。
7. 每次完成後必須列出：
   - 已完成
   - 未完成
   - 如何測試
   - 實際輸出位置

---

## 41. 最小可接受完成標準

第一版完成後，使用者應能：

1. 執行 Server/install.sh。
2. 執行 Server/start.sh。
3. 執行 User/install.sh。
4. 執行 User/start.sh。
5. 打開：

```text
http://127.0.0.1:6161
```

6. 使用：

```text
admin / 12345
```

登入。

7. 建立「化工」專案。
8. 上傳 PDF。
9. 關閉前端。
10. 重新打開前端看到進度。
11. 完成後查詢 PDF 內容。
12. 回答附來源、頁碼、區塊。
13. 若找不到證據，回答「資料庫中未找到足夠證據」。
14. 圖片可被擷取、caption、embedding、搜尋。
15. 搜尋結果可匯出。
16. 可選擇量化資料存在 Server 或 User。
17. Server/User 都能在各自 venv 中獨立安裝與啟動。

---

## 42. 專案標語

```text
Evidence First.
Everything Traceable.
Everything Rebuildable.
```

請把這三句視為整個系統最高優先級。
