# Comic Optimizer & Fast Packer (macOS)

專為 **macOS (Apple Silicon M1/M2/M3/M4/M5)** 打造的高效能漫畫／圖集壓縮檔最佳化與快速封裝工具。結合 **RAM Disk 零膨脹記憶體磁碟管線**、**動態 CPU 核心借調 (Dynamic Core Borrowing)** 與 **外接硬碟／RAID I/O 優先順序閘門 (Write-Priority Disk I/O Gatekeeper)**，在保護系統 SSD 壽命與避免外接磁碟陣列讀寫卡死的同時，發揮極致的多核心轉檔效能。

---

## ✨ 核心特色

- **⚡ 智慧 RAM Disk 零膨脹管線 (Rolling Unlink Pipeline)**：
  - 自動掛載 macOS 記憶體磁碟 (`/Volumes/ComicRamDisk`)，在記憶體內高速完成解壓縮、縮圖與 `.cbz` 封裝。
  - 採用**「邊轉邊刪、邊包邊刪」**機制，單一任務在 RAM Disk 內的空間佔用峰值不超過原始解壓大小的 100%，徹底消除暫存空間翻倍問題。
  - 支援 **Strict RAM（強制於 RAM Disk 執行）** 雙重空間檢核（帳面預留 + 實體剩餘空間），確保檔案不會因瞬時空間吃緊而偷跑至系統 SSD。
- **💿 外接陣列／硬碟友善的 I/O 優先閘門 (Write-Priority Disk I/O Gatekeeper)**：
  - 可自訂 **Disk I/O Limit（同時讀寫串流數，預設 `3 Streams`）**，防止傳統機械硬碟 (HDD)、NAS 或外接 RAID 陣列（如 QNAP TR-002）因 14 核心同時隨機讀寫而尋道卡死 (Disk Thrashing)。
  - **組裝完即刻搬移 (Priority Flush)**：在 RAM Disk 組裝完成的成品享有最高寫出優先權，第一時間循序寫回目的資料夾並釋放 RAM Disk。
- **🧠 動態 CPU 核心借調 (Atomic CPU Token Pool)**：
  - 保留 1 顆實體核心予 macOS 系統與 GUI 主執行緒 (`os.cpu_count() - 1`)，確保系統流暢不卡頓。
  - 當部分 Worker 處於 `Idle` 或等待硬碟讀取 (`Queued I/O`) 時，正在進行圖片縮放 (`Resizing`) 的任務會自動借調所有閒置核心進行多執行緒併發加速（例如 `Resizing(12T)`）。
- **📂 智慧分流與跨磁碟多來源處理**：
  - 支援拖曳多個來源資料夾批次處理（`.zip`、`.cbz`、`.rar`、`.cbr`、`.7z`），並自動在處理前將未打包的子資料夾預先封裝為 `.zip`。
  - 自動識別並分流：
    - **靜態圖片**（`.jpg`, `.png`, `.webp`, `.bmp`, `.gif` 靜態圖）➔ 最佳化縮放為高畫質 JPEG 並封裝為 `.cbz` (`Resized-YYYY-MM-DD/`)
    - **動態圖片**（多影格動畫 `.gif`, `.webp`）➔ 原檔無損保留並封裝為 `-Animated.zip` (`Animated-YYYY-MM-DD/`)
    - **影音媒體**（`.mp4`, `.mkv`, `.mov`, `.mp3`, `.flac` 等）➔ 原檔無損保留並封裝為 `-Media.zip` (`Media-YYYY-MM-DD/`)
    - **原始壓縮檔** ➔ 自動歸檔至各自來源目錄下的 `OriginalFiles-YYYY-MM-DD/`
    - **損毀壓縮檔** ➔ 自動隔離至 `FileErr-YYYY-MM-DD/` 並產出 `corrupted_search.html` 一鍵搜尋救援清單
- **📊 全時期歷史統計資料庫與參數自動記憶**：
  - 內建 SQLite 資料庫 (`history.db`) 永久記錄每次轉檔的頁數、原始大小、最佳化後大小、節省空間比例與耗時，支援關鍵字篩選、雙擊在 Finder 開啟與匯出 CSV 報表。
  - 所有介面設定（來源清單、輸出路徑、解析度預設、JPEG 品質、RAM Disk 容量、I/O 限制）皆自動儲存於 `config.json`。

---

## 🚀 初次使用必讀：macOS 環境建置指南 (First-Time Setup)

初次在新的 Mac 上使用本程式時，請依序完成以下 **4 個步驟**：

### 步驟 1：安裝 Homebrew（若尚未安裝）

開啟 macOS「終端機 (Terminal)」，執行以下指令安裝 [Homebrew](https://brew.sh/)：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

> 💡 **Apple Silicon (M1~M5) 注意事項**：安裝完成後，請確認 `/opt/homebrew/bin` 已加入您的 `PATH`（通常安裝腳本會提示執行以下兩行）：
> ```bash
> echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
> eval "$(/opt/homebrew/bin/brew shellenv)"
> ```

---

### 步驟 2：安裝系統依賴套件（Python 3.11+ 與 7-Zip `7zz`）

本程式需要 **Python 3.11 以上版本**，以及官方命令列解壓縮核心 **`sevenzip` (`7zz`)** 以支援 `.rar` / `.cbr` / `.7z` 格式的高速串流解壓縮：

```bash
brew update
brew install python sevenzip
```

接著進入專案目錄，將 Homebrew 安裝好的 `7zz` 執行檔複製一份至專案根目錄（確保未來打包 `.app` 或離線執行時皆能直接呼叫）：

```bash
cd /path/to/comic_optimizer
cp "$(which 7zz)" ./7zz
chmod +x ./7zz
```

---

### 步驟 3：建立 Python 虛擬環境 (`.venv`) 並安裝套件

為避免與 macOS 系統環境衝突，建議在專案根目錄下建立獨立的 `.venv` 虛擬環境並安裝 `requirements.txt` 中的套件（包含 `PyQt6`、`Pillow`、`rich`、`tqdm`、`pyinstaller`）：

```bash
# 1. 建立虛擬環境
python3 -m venv .venv

# 2. 升級 pip 並安裝所有依賴套件
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

---

### 步驟 4：啟動程式

環境建置完成後，即可直接透過虛擬環境啟動 GUI 介面：

```bash
./.venv/bin/python comic_optimizer_gui.py
```

啟動後，macOS Dock 將顯示專屬的 Apple 風應用程式圖示（[`app_icon.png`](file:///Users/edwardyao/GithubProjects/comic_optimizer/app_icon.png)）。

---

## 📦 進階：封裝為獨立 macOS `.app` 應用程式（選用）

若希望不透過終端機、直接從「應用程式 (Applications)」或 Dock 點擊啟動，可使用專案內已安裝的 `PyInstaller` 將程式、`7zz` 執行檔與 [`app_icon.icns`](file:///Users/edwardyao/GithubProjects/comic_optimizer/app_icon.icns) 打包為原生 `.app`：

```bash
./.venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name "Comic Optimizer" \
  --icon "app_icon.icns" \
  --add-binary "7zz:." \
  --add-data "app_icon.png:." \
  --add-data "app_icon.icns:." \
  comic_optimizer_gui.py
```

打包完成後，應用程式將位於 `dist/Comic Optimizer.app`，可直接拖曳至 `/Applications` 資料夾使用。

---

## ⚙️ 參數設定建議

| 參數項目 | 建議設定值 | 說明 |
| :--- | :--- | :--- |
| **Max Resolution** | `4K UHD (3840×2160)` | 長邊不超過 3840px、短邊不超過 2160px（等比例縮放，小圖不放大）；亦可選擇 `2K`、`1080p` 或 `Original Resolution`。 |
| **JPEG Quality** | `85 %` | 在 4K 解析度下兼顧肉眼無損畫質與最佳檔案體積壓縮比（通常可節省 50%~75% 空間）。 |
| **RAM Disk** | 系統自動建議值（如 24GB 記憶體建議 `14 GB`） | 設為 `0 GB` 時將停用 RAM Disk 並改用系統暫存區。 |
| **Strict RAM** | **建議勾選 (`Checked`)** | 強制所有小於 RAM Disk 總容量的壓縮檔 100% 在記憶體磁碟中完成處理，絕不寫入系統 SSD。 |
| **Disk I/O Limit** | 外接 HDD/RAID 建議 `2 ~ 3 Streams`<br>內建 NVMe SSD 可調至 `6 ~ 8 Streams` | 限制同時從硬碟讀取／寫出的串流數，避免外接陣列尋道滿載而拖慢 CPU 轉檔效率。 |

---

## 📁 資料儲存位置

- **設定檔 (`config.json`)**：`~/Library/Application Support/ComicOptimizer/config.json`
- **歷史統計資料庫 (`history.db`)**：`~/Library/Application Support/ComicOptimizer/history.db`

