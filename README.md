# Comic Optimizer & Fast Packer (macOS)

專為 macOS（Apple Silicon 最佳化）設計的高效能漫畫與圖集自動化處理工具。結合 **PyQt6 現代深色介面**、**動態 RAM Disk 分級排程**與**多核心非阻塞流水線**，提供批次縮圖減肥、資料夾零壓縮封裝（`zip -0`），以及多格式壓縮檔智慧解壓功能。

---

## 核心特色

* **⚡ Multi-Source 批次最佳化 (Comic Optimizer)**：
  * **多來源匯集**：支援同時添加多個跨硬碟或 NAS 資料夾，一次作業完成轉檔並可統一輸出至指定目錄（留空則各自存回原來源目錄）。
  * **前置自動封裝**：掃描前自動偵測來源路徑下的第一級子資料夾，預先封裝為 `.zip` 並將原資料夾安全移至 `OriginalFiles-YYYY-MM-DD`。
  * **智慧分流與畫質最佳化**：靜態圖片自動依設定之解析度上限（預設 4K UHD `3840×2160`）進行等比縮圖與高品質 JPEG 轉換；動態圖（Animated GIF/WebP）與影音檔（MP4/MKV/MP3 等）則原樣抽離並獨立打包，完整保留原始影格時序與畫質。
* **🧠 記憶體與 CPU 資源動態調度**：
  * **自動 RAM Disk 分級快取**：依據本機實體記憶體自動掛載高速 RAM Disk（`/Volumes/ComicRamDisk`），大幅降低 SSD 寫入損耗並提升高併發讀寫速度；支援 Strict RAM 嚴格排隊模式。
  * **原子級 CPU Token 借用池**：微批次（Micro-batching）動態借用閒置或等待 I/O 的核心協助圖片縮放，防止 CPU 過度訂閱（Over-subscription）。
  * **Disk I/O 併發限流**：自訂硬碟讀寫串流上限，避免外接硬碟或 NAS 發生磁碟抖動（Thrashing）。
* **📦 Pack & Unpack Studio（雙向封裝與解壓工作站）**：
  * **Quick Folder Packer**：將一級子資料夾以零壓縮儲存模式（`ZIP_STORED` / `zip -0`）極速封裝為 `.zip` 或 `.cbz`，並依自然排序排列頁碼。
  * **Quick Archive Unpacker**：支援 `.zip`、`.cbz`、`.rar`、`.cbr`、`.7z` 批次解壓，具備 **Smart Flatten** 自動消除多餘套娃資料夾與 macOS 隱藏垃圾檔（`__MACOSX`、`.DS_Store`）。
  * **雙層解壓容錯引擎**：優先採用高速 `7zz`，遇到非標準標頭或日文/繁簡特殊編碼 RAR 檔時，自動無縫切換至 `unar` 進行救援解壓。
* **📊 All-Time 歷史數據與損毀檔案救援**：
  * 內建 SQLite 紀錄庫追蹤歷次節省空間百分比與耗時，支援 CSV 匯出。
  * 損毀壓縮檔自動隔離至 `FileErr-YYYY-MM-DD`，並自動生成清洗檔名後的 E-Hentai 搜尋導航網頁（`corrupted_search.html`）。

---

## 環境需求與依賴安裝

### 1. 系統工具（透過 Homebrew 安裝）

本專案依賴 `7zz` 與 `unar` 處理 `.rar`、`.cbr` 與 `.7z` 格式，請先透過 Homebrew 安裝：

```bash
brew install sevenzip unar
```

### 2. Python 環境與套件

建議使用 Python 3.11 或以上版本，並建立獨立虛擬環境：

```bash
# 建立並啟動虛擬環境
python3 -m venv .venv
source .venv/bin/activate

# 安裝核心依賴與打包工具
pip install --upgrade pip
pip install PyQt6 Pillow pyinstaller
```

---

## 開發模式啟動

在終端機中直接執行 GUI 主程式：

```bash
python3 comic_optimizer_gui.py
```

---

## 打包為獨立 macOS `.app` 應用程式

為了讓打包後的 `.app` 具備完整離線執行能力，需先將系統安裝的 `7zz` 與 `unar` 複製到專案根目錄再進行 PyInstaller 建構。

### 1. 準備二進位執行檔與圖示

```bash
# 複製 7zz 與 unar 至專案根目錄並賦予執行權限
cp $(which 7zz) ./7zz
cp $(which unar) ./unar
chmod +x ./7zz ./unar
```

*(選用)* 若專案目錄下備有自訂應用程式圖示（`app_icon.icns` 與 `app_icon.png`），建構腳本會自動將其嵌入 App Bundle。

### 2. 執行 PyInstaller 乾淨建構

```bash
# 清除舊快取並依據規格檔建構
rm -rf build dist
pyinstaller --clean ComicOptimizer.spec
```

### 3. 修復內部權限與移除 macOS 隔離標籤

```bash
# 確保封裝進 App 內的輔助工具保留執行權限
chmod +x dist/ComicOptimizer.app/Contents/MacOS/7zz 2>/dev/null || true
chmod +x dist/ComicOptimizer.app/Contents/MacOS/unar 2>/dev/null || true

# 移除本機 Gatekeeper 隔離屬性 (Quarantine Flag)
xattr -cr dist/ComicOptimizer.app
```

### 4. 部署至「應用程式」目錄

```bash
rm -rf /Applications/ComicOptimizer.app
cp -R dist/ComicOptimizer.app /Applications/
```

完成後即可透過 Spotlight（`Cmd + Space`）或 Launchpad 搜尋 **Comic Optimizer** 直接啟動。

---

## 專案目錄結構

```text
comic_optimizer/
├── comic_optimizer_gui.py   # PyQt6 GUI 主程式與多核心調度引擎
├── ComicOptimizer.spec      # PyInstaller macOS App Bundle 打包規格檔
├── AGENT.md                 # AI 開發代理架構規範檔
├── README.md                # 專案說明文件
├── .gitignore               # Git 忽略清單（排除二進位檔與建構產物）
└── app_icon.icns / .png     # 應用程式圖示資源（選用）
```