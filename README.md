# Evidence-First Personal Knowledge Engine

> Evidence First. Everything Traceable. Everything Rebuildable.

多模態個人知識引擎，支援 PDF、EPUB、圖片的 OCR、版面分析、圖片向量化、Evidence-based RAG 查詢。

## 最低使用標準

執行以下步驟後，即可使用完整的知識引擎：

```
1. Server 端：./install.sh → ./start.sh
2. User 端：./install.sh → ./start.sh
3. 瀏覽器開啟 http://127.0.0.1:6161
4. 帳號 admin / 12345 登入
5. 建立專案 → 上傳 PDF → 等待處理完成 → 查詢
```

## 架構

```
┌──────────────┐     HTTP/HTTPS     ┌──────────────┐
│   User 端     │ ◄──────────────► │  Server 端    │
│  (Web UI)    │                    │  (API + 處理) │
│  Port 6161   │                    │  Port 8000   │
└──────────────┘                    └──────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │  ASUS GX10   │
                                    │  MinerU/OCR  │
                                    │  Qdrant/DB   │
                                    └─────────────┘
```

**Server 端**負責：原始檔保存、OCR、版面分析、圖片擷取、文字/圖片向量化、Hybrid Search、Reranker、Evidence Package。

**User 端**負責：Web UI、檔案上傳、查詢介面、工作進度、系統設定。

## 快速開始

### Server 端

```bash
cd release/Server
./launcher.sh    # 開啟選單（安裝/啟動/停止/狀態）
```

選單操作：

```
╔══════════════════════════════════════════╗
║     Evidence-First Server 控制面板       ║
╠══════════════════════════════════════════╣
║  狀態：未啟動                            ║
║                                          ║
  1  首次安裝（建立 venv、安裝依賴）
  2  啟動 Server
  3  停止 Server
  4  查看狀態
  0  離開
╚══════════════════════════════════════════╝
```

首次使用選擇 `1` 安裝，之後選擇 `2` 啟動。啟動後畫面會顯示區域網路 IP，把位址告訴 User 端的人。

### User 端

```bash
cd release/User
./launcher.sh    # 開啟選單（安裝/啟動/停止/狀態）
```

首次使用選擇 `1` 安裝，之後選擇 `2` 啟動（自動開啟瀏覽器）。

### Windows

直接雙擊 `launcher.bat` 即可，操作方式相同。

### 其他指令

| 指令 | 說明 |
|------|------|
| `./launcher.sh` | 選單式控制面板（推薦） |
| `./install.sh` | 直接安裝（不經過選單） |
| `./start.sh` | 直接啟動（不經過選單） |
| `./stop.sh` | 直接停止（不經過選單） |
| `./update.sh` | 更新依賴 |
| `./test.sh` | 執行測試 |
| `./backup.sh` | 建立備份（僅 Server） |
| `./restore.sh <檔名>` | 還原備份（僅 Server） |
| `./rebuild_index.sh` | 重建索引（僅 Server） |

## 支援格式

| 格式 | 說明 |
|------|------|
| PDF | 文字 PDF、掃描 PDF、圖文混排 |
| EPUB | 電子書 |
| TXT | 純文字 |
| JPG/JPEG/PNG | 圖片 |

## 查詢模式

### 回答模式

快速整理結論，仍會附上來源。適合一般問題。

### 研究模式

先列出 Evidence，再比較整理，最後給結論與不確定性。適合化工、程式、法律等專業查詢。

## 技術棧

- **Server**：Python / FastAPI / SQLite / MinerU / RapidOCR / CLIP / BLIP
- **User**：Python / FastAPI / 繁體中文 Web UI
- **搜尋**：Hybrid Search + Lexical Reranker + Source Rank
- **部署**：獨立 venv / 一鍵腳本 / 支援 HTTPS

## 目錄結構

```
release/
├── CHANGELOG.md
├── Server/
│   ├── launcher.sh / .bat   ← 雙擊這個就對了
│   ├── .env.example
│   ├── README.md
│   ├── requirements-server.txt
│   ├── app/main.py
│   └── scripts/
│       ├── install.sh / .bat
│       ├── start.sh / .bat
│       ├── stop.sh / .bat
│       └── ...
└── User/
    ├── launcher.sh / .bat   ← 雙擊這個就對了
    ├── .env.example
    ├── README.md
    ├── requirements-user.txt
    ├── app/main.py + static/
    └── scripts/
        ├── install.sh / .bat
        ├── start.sh / .bat
        ├── stop.sh / .bat
        └── ...
```

## Windows 使用

Windows 使用者有兩種方式：

### 方式一：直接執行 .bat 腳本

```
release/Server/install.bat → start.bat
release/User/install.bat → start.bat
```

### 方式二：透過 WSL

詳見 [release/User/README.md](release/User/README.md#windows-使用指南)。

## 規格文件

完整規格書位於 [docs/evidence_first_knowledge_engine_spec_v1.md](docs/evidence_first_knowledge_engine_spec_v1.md)。

## 授權

MIT License，詳見 [LICENSE](LICENSE)。
