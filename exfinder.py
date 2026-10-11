#!/usr/bin/env python3
import sys
import os
import re
import html
import urllib.parse
import argparse

def clean_to_query(line: str) -> str:
    """清理標題字串，保留核心作者與標題/角色關鍵字"""
    # 移除來源、AI標記、贊助平台、無修、副本等雜訊
    tags_to_remove = [
        r'\[\s*(AI Generated|REQUEST)\s*\]',
        r'\(\s*(AI Generated|REQUEST)\s*\)',
        r'\[\s*(Patreon|Unifans)\s*\]',
        r'\(\s*(Patreon|Unifans)\s*\)',
        r'\[\s*UNCENSORED\s*\]',
        r'\(\s*UNCENSORED\s*\)',
        r'\b(AI Generated|Uncensored|copy|拷貝)\b',
        r'\(?\b\d+\s*(P|PICS|IMAGES|PAGES)\b\)?',  # 頁數，如 127P, 70 IMAGES, 200 PICS
    ]
    cleaned = line
    for pattern in tags_to_remove:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)

    # 移除上下篇標記、特殊括號、分隔線等字符
    cleaned = re.sub(r'\[[上下]篇\]', ' ', cleaned)
    cleaned = re.sub(r'[\[\]\(\)（）︱|\\/\-–—~～]', ' ', cleaned)

    # 將連續空白壓平成單一空格
    cleaned = ' '.join(cleaned.split())
    return cleaned

def generate_html(records: list, output_filepath: str):
    """產出預設深色模式、支援切換與搜尋的表格 HTML 檔"""
    rows_html = []
    for idx, (original, query, eh_url) in enumerate(records, 1):
        safe_orig = html.escape(original)
        safe_query = html.escape(query)
        rows_html.append(f"""
        <tr>
            <td class="text-center">{idx}</td>
            <td class="orig-text">{safe_orig}</td>
            <td class="query-text"><code>{safe_query}</code></td>
            <td class="text-center">
                <a href="{eh_url}" target="_blank" rel="noopener noreferrer" class="search-btn">
                    在 E-Hentai 搜尋
                </a>
            </td>
        </tr>
        """)

    table_rows = "\n".join(rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-Hentai 漫畫檢索導航表</title>
    <style>
        /* 亮色模式變數 */
        :root {{
            --bg-color: #f7f9fb;
            --card-bg: #ffffff;
            --primary: #4f46e5;
            --primary-hover: #4338ca;
            --text-color: #1f2937;
            --subtext-color: #6b7280;
            --border-color: #e5e7eb;
            --table-header-bg: #f9fafb;
            --table-row-hover: #f8fafc;
            --code-bg: #f3f4f6;
            --code-text: #1f2937;
            --visited-btn: #9ca3af;
        }}

        /* 深色模式變數 (預設啟用) */
        [data-theme="dark"] {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --primary: #6366f1;
            --primary-hover: #818cf8;
            --text-color: #f1f5f9;
            --subtext-color: #94a3b8;
            --border-color: #334155;
            --table-header-bg: #0f172a;
            --table-row-hover: #273549;
            --code-bg: #0f172a;
            --code-text: #38bdf8;
            --visited-btn: #64748b;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 24px;
            transition: background-color 0.2s ease, color 0.2s ease;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: var(--card-bg);
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
            border: 1px solid var(--border-color);
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
        }}
        h1 {{
            margin: 0;
            font-size: 1.5rem;
            color: var(--text-color);
        }}
        .header-controls {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .search-box {{
            width: 260px;
        }}
        .search-box input {{
            width: 100%;
            padding: 8px 12px;
            background: var(--bg-color);
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 0.95rem;
            outline: none;
            box-sizing: border-box;
            transition: border-color 0.2s ease;
        }}
        .search-box input:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
        }}
        .theme-btn {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }}
        .theme-btn:hover {{
            border-color: var(--primary);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
        }}
        th, td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background-color: var(--table-header-bg);
            font-weight: 600;
            color: var(--text-color);
            position: sticky;
            top: 0;
        }}
        tr:hover td {{
            background-color: var(--table-row-hover);
        }}
        .text-center {{
            text-align: center;
        }}
        .orig-text {{
            word-break: break-all;
            color: var(--text-color);
        }}
        .query-text code {{
            background-color: var(--code-bg);
            color: var(--code-text);
            padding: 3px 6px;
            border-radius: 4px;
            font-size: 0.9rem;
            border: 1px solid var(--border-color);
        }}
        .search-btn {{
            display: inline-block;
            background-color: var(--primary);
            color: #ffffff;
            text-decoration: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-weight: 500;
            font-size: 0.88rem;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}
        .search-btn:hover {{
            background-color: var(--primary-hover);
        }}
        .search-btn:visited {{
            background-color: var(--visited-btn);
            color: #e2e8f0;
        }}
        .badge {{
            font-size: 0.85rem;
            color: var(--subtext-color);
            margin-left: 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>E-Hentai 搜尋導航清單 <span class="badge">共 {len(records)} 筆</span></h1>
            </div>
            <div class="header-controls">
                <div class="search-box">
                    <input type="text" id="filterInput" placeholder="即時篩選關鍵字..." onkeyup="filterTable()">
                </div>
                <button class="theme-btn" onclick="toggleTheme()" id="themeBtn">☀️ 切換淺色</button>
            </div>
        </header>

        <table id="linksTable">
            <thead>
                <tr>
                    <th style="width: 50px;" class="text-center">#</th>
                    <th style="width: 45%;">原始文字</th>
                    <th style="width: 35%;">清洗後關鍵字</th>
                    <th style="width: 15%;" class="text-center">動作</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>

    <script>
        // 預設為 dark 模式，可切換
        function setTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            const btn = document.getElementById('themeBtn');
            if (theme === 'dark') {{
                btn.innerHTML = '☀️ 切換淺色';
            }} else {{
                btn.innerHTML = '🌙 切換深色';
            }}
        }}

        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme');
            const target = current === 'dark' ? 'light' : 'dark';
            setTheme(target);
        }}

        function filterTable() {{
            const input = document.getElementById("filterInput").value.toLowerCase();
            const rows = document.querySelectorAll("#linksTable tbody tr");
            rows.forEach(row => {{
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(input) ? "" : "none";
            }});
        }}

        // 初始化
        setTheme('dark');
    </script>
</body>
</html>
"""
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    parser = argparse.ArgumentParser(description="將漫畫清單 txt 轉為 E-Hentai 搜尋導航 HTML 表格 (預設 Dark Mode)")
    parser.add_argument("input_file", nargs="?", help="輸入的文字檔路徑 (例如: corrupted_list.txt)")
    parser.add_argument("-o", "--output", help="自訂輸出的 HTML 檔案路徑")
    args = parser.parse_args()

    input_path = args.input_file
    if not input_path:
        input_path = input("請輸入 txt 檔案名稱或路徑: ").strip()

    if not os.path.exists(input_path):
        print(f"錯誤：找不到檔案 '{input_path}'")
        sys.exit(1)

    # 決定輸出檔名
    output_path = args.output
    if not output_path:
        base_name, _ = os.path.splitext(input_path)
        output_path = f"{base_name}.html"

    # 讀取並處理清單
    records = []
    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue

            query = clean_to_query(raw_line)
            if not query:
                continue

            encoded_query = urllib.parse.quote_plus(query)
            eh_url = f"https://e-hentai.org/?f_search={encoded_query}&f_cats=0"
            records.append((raw_line, query, eh_url))

    if not records:
        print("未在檔案中解析到有效條目。")
        sys.exit(0)

    # 產生網頁
    generate_html(records, output_path)
    print(f"\n處理完成！")
    print(f"成功處理條目：{len(records)} 筆")
    print(f"生成的網頁已儲存至：{os.path.abspath(output_path)}")
    print(f"預設深色模式已啟用，您可以直接點擊瀏覽。")

if __name__ == "__main__":
    main()