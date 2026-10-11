# Comic Optimizer (4K 漫畫與圖集批次轉換壓縮工具)

專為 macOS (Apple Silicon M 系列最佳化) 與現代電子漫畫閱讀器（如 YACReader）打造的高效批次圖片轉檔與打包工具。
具備激進型動態 RAM Disk 運算、未壓縮尺寸預檢、空間預約記帳員、智慧重試排程、動態/靜態分流、雙軌異常隔離、qqq 即時中止與成果結算統計。

---

## 核心亮點

1. 激進型動態 RAM 配置 (Aggressive RAM Sizing)：
   - 啟動時透過 sysctl 與 vm_stat 實時分析系統可用記憶體（包含 Free、Inactive、Speculative 與 Purgeable）。
   - 大幅釋放 Apple Silicon 統一記憶體優勢，在 24GB 設備上直接配置 10GB~14GB RAM Disk，大幅降低 SSD 寫入磨損與迫降機率。

2. 鍵盤連續輸入 qqq 即時優雅中止 (Graceful Abort)：
   - 背景即時監聽鍵盤輸入，隨時連續鍵入 qqq 即可觸發中斷旗標。
   - 立即停止派工並終止運行核心，保存已處置檔案的成果統計，並安全卸載 RAM Disk。

3. 零 I/O 展開尺寸預檢 (Pre-flight Inspection)：
   - 解壓前讀取壓縮檔 Header（ZIP/CBZ 讀取 infolist，7z/RAR 調用 7z l），0.001 秒內預知解壓後的未壓縮總大小。
   - 徹底杜絕「解壓到一半空間不足才報錯」的無效運算浪費。

4. RAM 空間預約記帳員 (Admission Control)：
   - 跨行程共享配額記帳機制，Worker 執行前必須向記帳員「預約」足夠容量才能進入 RAM Disk。
   - 任務完成清理暫存後自動歸還配額，確保記憶體吃滿但不溢出。

5. 動態重試隊列 (Smart Re-queueing)：
   - 當大檔案暫時借不到 RAM 額度時，自動退回隊列等待，優先讓路給小檔案消化。
   - 累積重試超過上限（預設 3 次）或單檔尺寸物理性超過 RAM Disk 總容量時，才安全迫降至本機 SSD。

6. 雙軌異常隔離與自動產出壞檔清單：
   - FileErr-YYYY-MM-DD/：隔離損毀、CRC 校驗失敗、密碼保護或結構無效的檔案。任務完成後自動生成 corrupted_list.txt（純檔名，不含副檔名）。
   - Error-YYYY-MM-DD/：隔離非檔案因素之系統/執行期例外。
   - 成功項目全數移至 Processed-YYYY-MM-DD/，保證來源資料夾 100% 乾淨清空，天生具備中斷續傳能力。

7. 4K 最佳化與 YACReader 適配：
   - 靜態圖統一轉換為相容性最高、翻頁最流暢的 JPEG (Quality 85, Lanczos 縮放)，解析度上限限制為 4K (3840 x 2160)。
   - 依自然檔名排序（Natural Sort），並以 ZIP_STORED (零壓縮模式) 打包為 .cbz，閱讀器連翻與縮圖載入零延遲。

8. 成果結算報告 (Summary Report)：
   - 批次完成後自動統計：已歸檔原檔體積 (Processed) vs 最佳化成品體積 (Comic+其他)，精確呈現省下容量與縮減百分比。
   - 彙整總耗時、處理檔數與平均每本處理速度。

---

## 系統需求

- 作業系統：macOS (支援 Apple Silicon M 系列晶片)
- Python 版本：Python 3.9+ (系統內建版本即可)
- 系統工具：7z (處理 RAR / 7Z 解壓)

---

## 初始安裝

### 步驟 1：安裝 7-Zip 解壓工具 (Homebrew)
在 Terminal 執行：
brew install sevenzip

(安裝完成後可用 which 7z 驗證路徑)

### 步驟 2：安裝 Python 依賴套件
透過 requirements.txt 安裝：
pip3 install --user -r requirements.txt

或直接安裝套件：
pip3 install --user Pillow rich tqdm

---

## 使用方式

### 方式 1：指令傳入路徑
python3 comic_optimizer.py "/Users/your_name/Downloads/Comics"

### 方式 2：互動式輸入 (支援直接拖曳)
直接執行腳本：
python3 comic_optimizer.py

出現提示後，直接將 Finder 上的目標資料夾（包含本機資料夾、隨身碟或掛載的 SMB 網路硬碟 /Volumes/...）拖曳至 Terminal 視窗內並按 Enter 即可。

### 執行途中中止
在終端機運作期間，連續按鍵盤 qqq 即可隨時安全中斷作業並結算目前進度。

---

## 輸出目錄架構

執行完畢後，來源目錄會自動分類歸整：

來源目錄/
├── Comic-YYYY-MM-DD/        # 轉檔後的 4K .cbz 漫畫書庫
│   └── 航海王_105.cbz
├── Animated-YYYY-MM-DD/     # 分離出的動態 WebP / GIF (隨需生成)
│   └── 某作品-Animated.zip
├── Media-YYYY-MM-DD/        # 分離出的影片與音樂 (隨需生成)
│   └── 某作品-Media.zip
├── Processed-YYYY-MM-DD/    # 成功轉檔的原始壓縮檔歸檔區
│   └── 航海王_105.zip
├── FileErr-YYYY-MM-DD/      # 損毀檔案 / CRC 報錯 / 密碼保護 (隨需生成)
│   └── corrupted_list.txt  # 自動輸出的損毀書名清單 (無副檔名)
└── Error-YYYY-MM-DD/        # 系統 / 轉檔執行異常 (隨需生成)

---

## 排程與分流機制說明

掃描壓縮檔 ➔ 零 I/O 讀取未壓縮總大小
    │
    ├── 物理超標 (大於 RAM Disk 總額度) ─────────> 直接走 SSD
    │
    └── 尺寸合規 (小於 RAM Disk 總額度)
            │
            ├── 向記帳員申請預約成功 ─────────────> 進入 RAM Disk 執行 (零 SSD 磨損)
            │
            └── 目前額度已被其他 Worker 佔滿
                    │
                    ├── 重試次數 < 3 ────────────> 退回 Queue，先讓路給小檔案
                    └── 重試次數 >= 3 ───────────> 迫降 SSD 執行

---

## 常見問題 (FAQ)

- Q: 處理中斷（連續按 qqq 或關閉終端機）會怎麼樣？
  - 腳本會立即捕獲中止信號，保留當前已經成功處理完畢的檔案，並安全卸載釋放 RAM Disk。
  - 由於未完成的檔案不會被移入 Processed，下次重新執行同一個資料夾會自動從未完成的檔案接續處理。

- Q: 什麼時候檔案會被移到 FileErr 而不是 Error？
  - 壓縮檔損壞、CRC 錯誤、標頭損壞或設有解壓密碼時，會被隔離至 FileErr，並在該目錄下產生無副檔名的純書名清單 corrupted_list.txt。