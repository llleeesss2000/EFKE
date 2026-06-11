# Evidence-First Knowledge Engine User

這是 User 端部署包，提供固定 Port `6161` 的繁體中文 Web UI。

## 快速開始

請先啟動 Server：

```bash
cd release/Server
./install.sh
./start.sh
```

再啟動 User：

```bash
cd release/User
./install.sh
./start.sh
```

部署包可以搬到其他資料夾。`start.sh` 會檢查 `.venv` 是否仍指向目前資料夾；如果發現 venv 是從別處搬來的，會自動移到 `.venv.broken.YYYYMMDD_HHMMSS` 並重建。

如果你是用檔案管理器雙擊，請改用這兩個腳本，視窗不會閃退：

```bash
./install_keep_open.sh
./start_keep_open.sh
```

打開：

```text
http://127.0.0.1:6161
```

登入：

```text
帳號：admin
密碼：12345
```

## 設定 Server 地址

編輯 `release/User/.env`：

```env
SERVER_API_URL=http://127.0.0.1:8000
```

如果 Server 在另一台電腦，改成該主機 IP：

```env
SERVER_API_URL=http://192.168.1.10:8000
```

目前雙機部署範例，Server 與 LLM 都在 `192.168.31.36`：

```env
SERVER_API_URL=http://192.168.31.36:8000
LLM_BASE_URL=http://192.168.31.36:11434/v1
```

可執行連線檢查：

```bash
./check_remote_keep_open.sh
```

## 設定 LLM 與 API Key

編輯 `release/User/.env`：

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3-coder-next:q8_0
```

這些設定會在 User UI 的系統設定中顯示。真正回答仍由 Server 的 Evidence Package 控制，避免 LLM 自由猜測。

## 量化資料存在 Server 或 User

預設：

```env
QUANTIZED_DATA_LOCATION=server
```

適合固定主機、大量 PDF、長期知識庫。

若要可攜式資料：

```env
QUANTIZED_DATA_LOCATION=user
USER_DATA_DIR=./user_data
```

User 端會建立 `release/User/user_data/`。搬移到其他電腦時，請一起搬移整個 `release/User/` 目錄，並確認 `.env` 的 Server 地址正確。

## UI 功能

目前已包含：

```text
登入頁
專案管理
檔案上傳
工作進度
查詢頁
回答模式 / 研究模式
搜尋結果
來源 Evidence 檢視
系統設定
LLM 設定顯示
資料存放位置設定顯示
帳號管理
備份 / 重建入口
專案刪除
工作進度移除
```

圖片、表格、公式的專用檢視入口已由 Evidence/asset schema 保留。第一版若未接外部模型，相關處理階段會明確顯示 `not_implemented`。

支援上傳格式：

```text
PDF
TXT
JPG
JPEG
PNG
EPUB
```

上傳頁支援：

```text
單檔上傳
拖曳單一檔案到批次上傳區
拖曳資料夾到批次上傳區
選擇資料夾
選擇多個檔案
```

批次上傳會顯示目前檔案、目前檔案百分比、整體進度、成功/失敗數量。

## 測試

```bash
./test.sh
```

測試會確認首頁與設定 API 可用。

## Windows 使用指南

Windows 使用者可以透過 WSL（Windows Subsystem for Linux）執行。

### 安裝 WSL

1. 開啟 PowerShell（系統管理員）
2. 執行：`wsl --install`
3. 重開電腦
4. 首次開啟 WSL 會要求設定帳號密碼

### 在 WSL 中執行

```bash
# 將部署包放到 WSL 可存取的位置（例如 /mnt/c/ 下）
cp -r /mnt/c/Users/你的帳號/Downloads/release ~/
cd ~/release/User
chmod +x *.sh
./install.sh
./start.sh
```

### 雙擊啟動（Windows 捷徑）

如果不想每次開終端機，可以在 Windows 桌面建立捷徑：

1. 桌面按右鍵 → 新增 → 捷徑
2. 輸入：`wsl.exe -d Ubuntu -- bash -c "cd ~/release/User && ./start.sh"`
3. 命名為「Evidence-First User」
4. 雙擊即可啟動

### 注意事項

- WSL 內的網路與 Windows 共用，可以直接存取區域網路的 Server
- 如果 Server 也在 WSL 中，使用 `localhost` 或 `127.0.0.1` 即可
- 搬移資料時，整個 `release/User/` 資料夾一起搬移即可
