# Comic Optimizer (4K 漫畫與圖集批次轉換壓縮工具)

專為 macOS (Apple Silicon M 系列最佳化) 與現代電子漫畫閱讀器（如 YACReader）打造的高效批次圖片轉檔與打包工具。
具備互動式 RAM Disk 配置、純 RAM 優先排程、多核心並行尺寸預檢、7zz/7z 引擎動態偵測、動態/靜態分流、雙軌異常隔離、qqq 即時中止、成果結算統計，以及 E-Hentai 損毀檔案重搜導航表生成。

---

## 核心亮點

1. 互動式 RAM Disk 配置與純 RAM 排程模式：
   - 啟動時依據硬體規格提供推薦容量，並支援使用者自訂輸入（輸入 0 則走純 SSD 模式）。
   - 提供「純 RAM 模式」選項（預設啟用）：當記憶體額度用盡時，新任務持續在隊列中等待前一任務釋放空間，絕不輕易迫降寫入 SSD，極大化延長快閃記憶體壽命。

2. 多核心並行展開尺寸預檢 (並行 Pre-flight Inspection)：
   - 調用 ThreadPool 多執行緒同時掃描檔案 Header（ZIP 走原生記憶體讀取，RAR/7Z 調用精簡輸出）。
   - 搭配 Rich 即時進度條與檔案名稱滾動，數百本圖庫在數秒內即可精準估算展開體積。

3. 自動探測 7-Zip 引擎 (7zz / 7z)：
   - 自動判斷 Homebrew 安裝之獨立版 `7zz` 或系統 `7z`，並注入 `-p-` 旗標避免密碼提示卡死，徹底解決 RAR/CBR 誤判為損毀的問題。

4. 鍵盤連續輸入 qqq 即時優雅中止 (Graceful Abort)：
   - 背景即時監聽鍵盤輸入，隨時連續鍵入 qqq 即可觸發中止。
   - 立即停止派工並終止運行核心，完整保存已處置檔案的成果統計，並安全卸載 RAM Disk。

5. 雙軌異常隔離與 E-Hentai 重搜導航：
   - FileErr-YYYY-MM-DD/：隔離損毀、CRC 校驗失敗、密碼保護或結構無效的檔案。
   - 自動輸出 corrupted_list.txt（純檔名，不含副檔名）。
   - 自動生成 corrupted_search.html：清洗標題雜訊（移除頁數、AI 標記、括號等），產出支援深淺色切換與即時篩選的 E-Hentai 搜尋導航表，補檔只需一鍵點擊。
   - Error-YYYY-MM-DD/：隔離非檔案因素之系統/執行期例外。

6. 智慧過濾歷史資料夾：
   - 掃描時自動略過以往產生的輸出資料夾（如 Resized-*、FileErr-*、Processed-* 等），避免重複遞迴處理。

7. 4K 最佳化與 YACReader 適配：
   - 靜態圖統一轉換為相容性最高、翻頁最流暢的 JPEG (Quality 85, Lanczos 縮放)，解析度上限限制為 4K (3840 x 2160)。
   - 依自然檔名排序（Natural Sort），並以 ZIP_STORED (零壓縮模式) 打包為 .cbz，閱讀器連翻與縮圖載入零延遲。

8. 成果結算報告 (Summary Report)：
   - 批次完成後自動統計：已歸檔原檔體積 (Processed) vs 最佳化成品體積 (Resized+其他)，精確呈現省下容量與縮減百分比。
   - 彙整總耗時、處理檔數與平均每本處理速度。

---

## 系統需求

- 作業系統：macOS (支援 Apple Silicon M 系列晶片)
- Python 版本：Python 3.9+ (系統內建版本即可)
- 系統工具：7-Zip (處理 RAR / 7Z 解壓)

---

## 初始安裝

### 步驟 1：安裝 7-Zip 解壓工具 (Homebrew)
在 Terminal 執行：
brew install sevenzip

(安裝完成後可用 which 7zz 或 which 7z 驗證路徑)

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

1. 輸入或拖曳來源資料夾路徑。
2. 設定 RAM Disk 容量（直接 Enter 即採用建議值）。
3. 選擇是否啟用純 RAM 模式（直接 Enter 預設啟用 Y）。

### 執行途中中止
在終端機運作期間，連續按鍵盤 qqq 即可隨時安全中斷作業並結算目前進度。

---

## 輸出目錄架構

執行完畢後，來源目錄會自動分類歸整：

來源目錄/
├── Resized-YYYY-MM-DD/      # 轉檔後的 4K .cbz 漫畫書庫
│   └── 航海王_105.cbz
├── Animated-YYYY-MM-DD/     # 分離出的動態 WebP / GIF (隨需生成)
│   └── 某作品-Animated.zip
├── Media-YYYY-MM-DD/        # 分離出的影片與音樂 (隨需生成)
│   └── 某作品-Media.zip
├── Processed-YYYY-MM-DD/    # 成功轉檔的原始壓縮檔歸檔區
│   └── 航海王_105.zip
├── FileErr-YYYY-MM-DD/      # 損毀檔案 / CRC 報錯 / 密碼保護 (隨需生成)
│   ├── corrupted_list.txt   # 純文字書名清單 (無副檔名)
│   └── corrupted_search.html# E-Hentai 搜尋導航網頁 (一鍵點擊補檔)
└── Error-YYYY-MM-DD/        # 系統 / 轉檔執行異常 (隨需生成)

---

## 常見問題 (FAQ)

- Q: 處理中斷（連續按 qqq 或關閉終端機）會怎麼樣？
  - 腳本會立即捕獲中止信號，保留當前已經成功處理完畢的檔案，並安全卸載釋放 RAM Disk。
  - 由於未完成的檔案不會被移入 Processed，下次重新執行同一個資料夾會自動從未完成的檔案接續處理。

- Q: 什麼時候檔案會被移到 FileErr 而不是 Error？
  - 壓縮檔損壞、CRC 錯誤、標頭損壞或設有解壓密碼時，會被隔離至 FileErr，並在該目錄下產生 corrupted_list.txt 與 corrupted_search.html。