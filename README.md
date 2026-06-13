# Evidence-First Personal Knowledge Engine (EFKE)

> **Evidence First. Everything Traceable. Everything Rebuildable.**

多模態個人知識引擎。不同於一般 RAG 系統，本專案以**證據為核心**——找不到足夠證據時，系統會明確回答「資料庫中未找到足夠證據」，而不是讓 LLM 猜測。

## 為什麼選擇 EFKE？

### 與其他 RAG 專案的差異

| 特色 | EFKE | RAGFlow | Dify | LightRAG |
|------|------|---------|------|----------|
| **跨主機部署** | ✅ Server + User 分離 | ❌ 單機 Docker | ❌ 單機 Docker | ❌ 單機 |
| **不需要 Docker** | ✅ 純腳本 + venv | ❌ 需要 2-9GB Docker | ❌ 需要 Docker | ❌ 需要 Docker |
| **Evidence-First** | ✅ 找不到就說找不到 | ⚠️ 嘗試回答 | ⚠️ 嘗試回答 | ⚠️ 嘗試回答 |
| **來源追溯** | ✅ 頁碼/區塊/座標 | ✅ | ⚠️ 有限 | ⚠️ 有限 |
| **維基功能** | ✅ AI 自動整理 | ❌ | ❌ | ❌ |
| **知識圖譜** | ✅ vis.js 視覺化 | ❌ | ❌ | ⚠️ |
| **繁體中文** | ✅ 原生支援 | ⚠️ 多語言 | ⚠️ 多語言 | ❌ 英文為主 |
| **一鍵安裝** | ✅ launcher 選單 | ⚠️ docker-compose | ⚠️ docker-compose | ⚠️ pip install |
| **Rust 加速** | ✅ SHA256/Chunk/Scan | ❌ | ❌ | ❌ |

### 跨主機架構

```
┌─────────────────────┐         ┌─────────────────────┐
│     User 端          │         │     Server 端        │
│  （你的筆電/桌機）    │◄──────►│  （高效能主機）       │
│                     │  網路   │                     │
│  • 瀏覽器操作        │         │  • OCR / MinerU      │
│  • 檔案上傳          │         │  • 圖片向量化         │
│  • 查詢介面          │         │  • Hybrid Search     │
│  • 維基/圖譜         │         │  • Reranker          │
│  Port 6161          │         │  Port 8000           │
└─────────────────────┘         └─────────────────────┘
```

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

## 功能總覽

| 功能 | 說明 |
|------|------|
| **查詢** | LLM 整理回答 + Evidence 引用 + 對話記憶 |
| **維基** | AI 自動整理專案文件，144+ 條知識條目 |
| **知識圖譜** | vis.js 視覺化，點擊節點顯示維基 |
| **上傳** | 拖曳/批次/單檔 + 即時進度 |
| **校閱** | PDF 疊圖/OCR 標示/EPUB 圖片 |
| **歷史** | 查詢紀錄，可重新執行 |
| **設定** | LLM 多供應者/連線測試/Server URL 可改 |
| **帳號** | admin/user/readonly 三種角色 |
| **多語言** | 繁中/英文切換 |
| **手機版** | 響應式設計 + 漢堡選單 |

## 目錄結構

```
EFKE/
├── README.md
├── LICENSE (MIT)
├── docs/
│   ├── evidence_first_knowledge_engine_spec_v1.md
│   └── WIKI_SCHEMA.md
├── .github/workflows/test.yml
└── release/
    ├── CHANGELOG.md
    ├── Server/
    │   ├── launcher.sh / .bat   ← 雙擊這個就對了
    │   ├── .env.example
    │   ├── README.md
    │   ├── requirements-server.txt
    │   ├── app/main.py
    │   └── scripts/
    └── User/
        ├── launcher.sh / .bat   ← 雙擊這個就對了
        ├── .env.example
        ├── README.md
        ├── requirements-user.txt
        ├── app/main.py + static/
        └── scripts/
```

## 技術棧

- **Server**：Python FastAPI + SQLite + MinerU + RapidOCR + CLIP + BLIP
- **User**：Python FastAPI + 繁體中文 Web UI
- **加速**：Rust CLI（SHA256/Chunk/Scan/Meta）
- **搜尋**：Hybrid Search + Lexical Reranker + Source Rank
- **視覺化**：vis.js 知識圖譜 + D3.js

## 授權

MIT License，詳見 [LICENSE](LICENSE)。
