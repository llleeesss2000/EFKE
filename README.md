# Evidence-First Personal Knowledge Engine (EFKE)

> **🚧 正在施工中 — 部份功能暫時未開放**
>
> 本專案目前為 v1.0 版本，核心功能已可使用。以下功能尚在開發中：
> - Knowledge Graph（V2 規劃）
> - 外部 Reranker 模型接入
> - 向量搜尋（目前為 Lexical Search）
> - PDF 匯出搜尋結果
>
> 歡迎 Issues 回饋建議！

---

> **Evidence First. Everything Traceable. Everything Rebuildable.**

多模態個人知識引擎。不同於一般 RAG 系統，本專案以**證據為核心**——找不到足夠證據時，系統會明確回答「資料庫中未找到足夠證據」，而不是讓 LLM 猜測。

## 為什麼選擇 EFKE？

### 與其他 RAG 專案的差異

| 特色 | EFKE | RAGFlow | Dify | LightRAG |
|------|------|---------|------|----------|
| **跨主機部署** | ✅ Server + User 分離 | ❌ 單機 Docker | ❌ 單機 Docker | ❌ 單機 |
| **不需要 Docker** | ✅ 純腳本 + venv | ❌ 需要 2-9GB Docker | ❌ 需要 Docker | ❌ 需要 Docker |
| **Evidence-First 哲學** | ✅ 找不到證據就說找不到 | ⚠️ 嘗試回答 | ⚠️ 嘗試回答 | ⚠️ 嘗試回答 |
| **來源追溯到頁碼/區塊** | ✅ 每個回答附座標 | ✅ | ⚠️ 有限 | ⚠️ 有限 |
| **掃描 PDF OCR** | ✅ MinerU + RapidOCR | ✅ | ⚠️ 需外掛 | ❌ |
| **圖片向量化搜尋** | ✅ CLIP + Caption | ✅ | ⚠️ | ❌ |
| **繁體中文原生支援** | ✅ 從介面到錯誤訊息 | ⚠️ 多語言 | ⚠️ 多語言 | ❌ 英文為主 |
| **一鍵安裝** | ✅ launcher 選單 | ⚠️ docker-compose | ⚠️ docker-compose | ⚠️ pip install |
| **非技術友善** | ✅ 雙擊就完成 | ⚠️ 需懂 Docker | ⚠️ 需懂 Docker | ❌ 需懂 Python |
| **災難復原** | ✅ 原始檔可重建一切 | ⚠️ | ⚠️ | ❌ |

### 🌐 跨主機架構（核心優勢）

**這是目前 GitHub 上少數支援「Server 與 User 分機部署」的 RAG 系統。**

```
┌─────────────────────┐         ┌─────────────────────┐
│     User 端          │         │     Server 端        │
│  （你的筆電/桌機）    │◄──────►│  （高效能主機）       │
│                     │  網路   │                     │
│  • 瀏覽器操作        │         │  • OCR / MinerU      │
│  • 檔案上傳          │         │  • 圖片向量化         │
│  • 查詢介面          │         │  • Hybrid Search     │
│  • 工作進度          │         │  • Reranker          │
│                     │         │  • 原始檔保存         │
│  Port 6161          │         │  Port 8000           │
└─────────────────────┘         └─────────────────────┘
```

**為什麼這很重要？**

- **OCR 和圖片處理需要大量運算** → 放在高效能主機（如 ASUS GX10）上跑
- **使用者在自己的電腦上操作** → 不需要懂伺服器、不需要遠端桌面
- **多個 User 可以同時連線同一個 Server** → 知識庫共享
- **Server 可以 24 小時運行** → 隨時上傳、隨時查詢
- **搬移方便** → User 端整個資料夾搬到新電腦即可使用

其他 RAG 系統（RAGFlow、Dify）都在同一台機器上跑，OCR 和 UI 搶資源。EFKE 把重型處理和使用者操作分開，各自獨立。

### 🔒 Evidence-First 哲學

> **有證據才回答。找不到足夠證據，就說找不到。**

大多數 RAG 系統會盡量「生成」回答，即使檢索到的內容不夠充分。這在一般聊天沒問題，但在**化工、法律、醫療、投資**等專業領域，錯誤的猜測可能造成嚴重後果。

EFKE 的做法：

1. 搜尋 Evidence Package（文字 + 圖片 + 表格 + 公式）
2. 有足夠證據 → 引用來源回答
3. 證據不足 → 明確回答「資料庫中未找到足夠證據」
4. **絕對不讓 LLM 自由猜測專業資料**

### 📍 完整來源追溯

每個回答都可以追溯到：

```
回答 → Evidence Package → 區塊/Chunk/圖片/表格 → 頁碼 → 原始檔案
```

搜尋結果包含：
- 原始檔案名稱
- 頁碼
- 區塊 ID 與座標（bbox）
- Rerank 分數
- Source Rank（A級教科書 > B級論文 > C級文章 > D級論壇）

### 🖥️ 非技術友善

不需要懂 Docker、不需要懂命令列。打開資料夾，雙擊 `launcher.bat`：

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

首次設定在瀏覽器內完成——輸入 Server IP 就好，不用編輯任何設定檔。

### 🛡️ 災難復原

只要保留原始檔，就能重建整個系統：

```bash
./backup.sh      # 備份 metadata
./restore.sh     # 還原
./rebuild_index.sh  # 重建索引
```

OCR 結果、Chunk、向量、AI 整理都是「可重建衍生資料」。原始檔是唯一的黃金來源。

## 快速開始

### Server 端（放在高效能主機上）

```bash
cd release/Server
./launcher.sh
# 選 1 安裝 → 選 2 啟動
# 畫面會顯示 IP 位址，告訴 User 端的人
```

### User 端（放在你自己的電腦上）

```bash
cd release/User
./launcher.sh
# 選 1 安裝 → 選 2 啟動（自動開瀏覽器）
# 輸入 Server 顯示的 IP 位址
```

### Windows

直接雙擊 `launcher.bat` 即可。

## 支援格式

| 格式 | 說明 |
|------|------|
| PDF | 文字 PDF、掃描 PDF、圖文混排、表格、公式 |
| EPUB | 電子書 |
| TXT | 純文字 |
| JPG/JPEG/PNG | 圖片（OCR + 向量化） |

## 查詢模式

### 回答模式

快速整理結論，仍會附上來源。適合一般問題。

### 研究模式

先列出 Evidence，再比較整理，最後給結論與不確定性。適合化工、程式、法律等專業查詢。

## 技術棧

- **Server**：Python / FastAPI / SQLite / MinerU / RapidOCR / CLIP / BLIP
- **User**：Python / FastAPI / 繁體中文 Web UI
- **搜尋**：Hybrid Search + Lexical Reranker + Source Rank
- **部署**：獨立 venv / 一鍵腳本 / 支援 HTTPS / 跨主機

## 目錄結構

```
EFKE/
├── README.md
├── LICENSE (MIT)
├── docs/
│   └── evidence_first_knowledge_engine_spec_v1.md
├── .github/workflows/test.yml
└── release/
    ├── CHANGELOG.md
    ├── Server/
    │   ├── launcher.sh / .bat   ← 雙擊這個就對了
    │   └── scripts/
    └── User/
        ├── launcher.sh / .bat   ← 雙擊這個就對了
        └── scripts/
```

## 規格文件

完整規格書位於 [docs/evidence_first_knowledge_engine_spec_v1.md](docs/evidence_first_knowledge_engine_spec_v1.md)。

## 授權

MIT License，詳見 [LICENSE](LICENSE)。

---

**如果這個專案對你有幫助，歡迎 Star 支持！**
