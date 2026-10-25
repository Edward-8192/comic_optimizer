import os
import sys
import re
import html
import shutil
import zipfile
import subprocess
import tempfile
import multiprocessing
import time
import select
import termios
import tty
import threading
import urllib.parse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)

# ==================== 基本設定 ====================
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
JPEG_QUALITY = 85

MAX_RAM_RETRIES = 5            # 彈性模式下，放不進 RAM 的最大重試次數
RAM_DISK_MOUNT = Path("/Volumes/ComicRamDisk")

ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.cbz', '.cbr'}
STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'}
MEDIA_EXTS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg'
}

# 系統產出目錄前綴（包含歷史任何日期的目錄皆會被略過，保留 Processed- 以相容舊目錄）
SYSTEM_DIR_PREFIXES = (
    "Resized-",
    "Comic-",
    "Animated-",
    "Media-",
    "OriginalFiles-",
    "Processed-",
    "FileErr-",
    "Error-",
)

ARCHIVE_MAIN_EXT = '.cbz'
ARCHIVE_OTHER_EXT = '.zip'

SPINNER_CHARS = ["-", "\\", "|", "/"]
# =================================================


def sanitize_log_text(text: str) -> str:
    """過濾會造成終端機字元寬度計算失真 (1 cell vs 2 cells) 的 Emoji 與特殊符號"""
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251" 
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text)


def find_7z_binary() -> str:
    """自動探測 7zz (Homebrew sevenzip 預設) 或 7z"""
    for binary in ["7zz", "7z"]:
        if shutil.which(binary):
            return binary
    return "7z"

SEVEN_ZIP_BIN = find_7z_binary()


# ==================== E-Hentai 導航檢索生成模組 ====================
def clean_to_query(line: str) -> str:
    """清理標題字串，保留核心作者與標題/角色關鍵字"""
    cleaned = sanitize_log_text(line)
    tags_to_remove = [
        r'\[\s*(AI Generated|REQUEST)\s*\]',
        r'\(\s*(AI Generated|REQUEST)\s*\)',
        r'\[\s*(Patreon|Unifans)\s*\]',
        r'\(\s*(Patreon|Unifans)\s*\)',
        r'\[\s*UNCENSORED\s*\]',
        r'\(\s*UNCENSORED\s*\)',
        r'\b(AI Generated|Uncensored|copy|拷貝)\b',
        r'\(?\b\d+\s*(P|PICS|IMAGES|PAGES)\b\)?',
    ]
    for pattern in tags_to_remove:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r'\[[上下]篇\]', ' ', cleaned)
    cleaned = re.sub(r'[\[\]\(\)（）︱|\\/\-–—~～★☆◆◇▲△▼▽]', ' ', cleaned)
    return ' '.join(cleaned.split())


def generate_eh_search_html(records: list, output_filepath: Path):
    """產出支援即時篩選、深淺色切換的 E-Hentai 搜尋導航 HTML"""
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
    <title>E-Hentai 損毀檔案重搜導航表</title>
    <style>
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
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
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
        .search-box input {{
            width: 260px;
            padding: 8px 12px;
            background: var(--bg-color);
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 0.95rem;
            outline: none;
            box-sizing: border-box;
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
            white-space: nowrap;
            transition: all 0.2s ease;
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
                <h1>E-Hentai 損毀檔案檢索清單 <span class="badge">共 {len(records)} 筆</span></h1>
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
                    <th style="width: 45%;">原始檔案名稱</th>
                    <th style="width: 35%;">清洗後檢索關鍵字</th>
                    <th style="width: 15%;" class="text-center">動作</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>

    <script>
        function setTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            const btn = document.getElementById('themeBtn');
            btn.innerHTML = (theme === 'dark') ? '☀️ 切換淺色' : '🌙 切換深色';
        }}
        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme');
            setTheme(current === 'dark' ? 'light' : 'dark');
        }}
        function filterTable() {{
            const input = document.getElementById("filterInput").value.toLowerCase();
            const rows = document.querySelectorAll("#linksTable tbody tr");
            rows.forEach(row => {{
                row.style.display = row.innerText.toLowerCase().includes(input) ? "" : "none";
            }});
        }}
        setTheme('dark');
    </script>
</body>
</html>
"""
    output_filepath.write_text(html_content, encoding="utf-8")
# ====================================================================


class KeyAbortListener:
    """背景監聽鍵盤輸入，連續輸入 qqq 即觸發中止"""
    def __init__(self):
        self.stop_event = threading.Event()
        self.aborted = False
        self.thread = None
        self.orig_term_settings = None

    def start(self):
        if not sys.stdin.isatty():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        q_count = 0
        fd = sys.stdin.fileno()
        try:
            self.orig_term_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            while not self.stop_event.is_set():
                r, _, _ = select.select([sys.stdin], [], [], 0.2)
                if r:
                    char = sys.stdin.read(1)
                    if char.lower() == 'q':
                        q_count += 1
                        if q_count >= 3:
                            self.aborted = True
                            break
                    else:
                        q_count = 0
        except Exception:
            pass
        finally:
            self.restore_terminal()

    def restore_terminal(self):
        if self.orig_term_settings and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.orig_term_settings)
            except Exception:
                pass

    def stop(self):
        self.stop_event.set()
        self.restore_terminal()


def get_recommended_ram_disk_gb() -> int:
    """評估系統實體記憶體並給出建議 RAM Disk 容量 (GB)"""
    try:
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        total_ram_gb = mem_bytes / (1024 ** 3)
        if total_ram_gb >= 64.0:
            return 36
        elif total_ram_gb >= 36.0:
            return 20
        elif total_ram_gb >= 24.0:
            return 14
        elif total_ram_gb >= 16.0:
            return 9
        else:
            return 4
    except Exception:
        return 12


def setup_ram_disk(size_gb: int) -> Path:
    """自動掛載 RAM Disk"""
    if size_gb <= 0:
        return None
    if RAM_DISK_MOUNT.exists():
        return RAM_DISK_MOUNT
    sectors = size_gb * 1024 * 1024 * 1024 // 512
    try:
        dev = subprocess.check_output(
            ["hdiutil", "attach", "-nomount", f"ram://{sectors}"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        subprocess.check_call(
            ["diskutil", "erasevolume", "HFS+", RAM_DISK_MOUNT.name, dev],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return RAM_DISK_MOUNT
    except Exception:
        return None


def cleanup_ram_disk():
    """安全卸載 RAM Disk"""
    if RAM_DISK_MOUNT.exists():
        subprocess.run(
            ["diskutil", "eject", str(RAM_DISK_MOUNT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )


def get_ram_disk_usage():
    if not RAM_DISK_MOUNT.exists():
        return "未啟用", 0.0
    try:
        stat = shutil.disk_usage(RAM_DISK_MOUNT)
        used_mb = (stat.total - stat.free) / (1024 * 1024)
        total_mb = stat.total / (1024 * 1024)
        pct = (used_mb / total_mb) * 100
        return f"{used_mb:.0f}MB/{total_mb/1024:.1f}GB ({pct:.1f}%)", pct
    except Exception:
        return "未知", 0.0


def get_uncompressed_size_mb_fast(archive_path: Path) -> float:
    """
    極速零 I/O 預檢引擎：
    1. ZIP / CBZ 讀取檔尾集中目錄表（原生記憶體操作，毫秒級完成）。
    2. RAR / 7Z 採漫畫專用精準係數（實體大小 × 1.2 倍），徹底杜絕外部磁碟與 NAS 的尋軌延遲。
    """
    ext = archive_path.suffix.lower()
    try:
        if ext in ('.zip', '.cbz'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                total_bytes = sum(zinfo.file_size for zinfo in zf.infolist())
                return total_bytes / (1024 * 1024)
        else:
            return (archive_path.stat().st_size * 1.2) / (1024 * 1024)
    except Exception:
        return (archive_path.stat().st_size * 1.2) / (1024 * 1024)


def inspect_archive_worker(arch: Path):
    """供 ThreadPool 平行預檢調用的工作單元"""
    return {
        "path": arch,
        "uncompressed_mb": get_uncompressed_size_mb_fast(arch),
        "retries": 0
    }


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def is_image_animated(image_path: Path) -> bool:
    try:
        with Image.open(image_path) as img:
            if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
                return True
    except Exception:
        pass
    return False


def resize_and_convert_image(src_path: Path, dst_path: Path):
    with Image.open(src_path) as img:
        img = ImageOps.exif_transpose(img)

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha_img = img.convert("RGBA")
            background.paste(alpha_img, mask=alpha_img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        ratio = min(MAX_WIDTH / orig_w, MAX_HEIGHT / orig_h)
        if ratio < 1.0:
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        img.save(dst_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)


def extract_archive_stream(archive_path: Path, extract_dir: Path, progress_callback=None):
    ext = archive_path.suffix.lower()
    start_time = time.time()

    try:
        if ext in ('.zip', '.cbz'):
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    members = zf.infolist()
                    total = len(members)
                    for idx, member in enumerate(members):
                        zf.extract(member, extract_dir)
                        if progress_callback and (idx % 12 == 0 or idx == total - 1):
                            elapsed = time.time() - start_time
                            progress_callback((idx + 1) / max(1, total), elapsed)
                return True, "SUCCESS"
            except OSError as e:
                if e.errno == 28 or "No space left on device" in str(e):
                    return False, "NO_SPACE"
                return False, "CORRUPTED"
            except (zipfile.BadZipFile, zipfile.LargeZipFile):
                return False, "CORRUPTED"
            except Exception:
                return False, "CORRUPTED"

        elif ext in ('.rar', '.cbr', '.7z'):
            cmd = [SEVEN_ZIP_BIN, "x", str(archive_path), f"-o{extract_dir}", "-y", "-p-", "-bsp1"]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
            except FileNotFoundError:
                return False, "CORRUPTED"

            pct_pattern = re.compile(r'(\d+)%')
            current_pct = 0.0
            captured_output = []

            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break

                if line:
                    captured_output.append(line)
                    matches = pct_pattern.findall(line)
                    if matches:
                        current_pct = int(matches[-1]) / 100.0

                elapsed = time.time() - start_time
                if progress_callback:
                    progress_callback(current_pct, elapsed)

            _, stderr_out = proc.communicate()
            if proc.returncode == 0:
                return True, "SUCCESS"

            all_err_text = "".join(captured_output) + (" " + stderr_out if stderr_out else "")
            no_space_keywords = ["no space left", "not enough space", "disk full", "write error"]
            if any(k in all_err_text.lower() for k in no_space_keywords):
                return False, "NO_SPACE"

            return False, "CORRUPTED"

    except Exception as e:
        if "No space left on device" in str(e):
            return False, "NO_SPACE"
        return False, "CORRUPTED"


def create_zip_store(target_archive: Path, file_pairs: list, root_folder_name: str = None):
    """
    建立 ZIP_STORED 壓縮檔。
    具備智慧路徑防呆：若指定 root_folder_name，僅在檔案散落於根目錄時補上一層資料夾，
    避免解壓縮時出現『檔名/檔名/...』重複巢狀資料夾的問題。
    """
    if not file_pairs:
        return
    target_archive.parent.mkdir(parents=True, exist_ok=True)
    file_pairs.sort(key=lambda x: natural_sort_key(x[1]))

    # 1. 檢查這批檔案是否已經具備共同的單一頂層資料夾
    needs_wrapper = False
    if root_folder_name:
        # 取得所有檔案在相對路徑下的第一層目錄名稱
        top_dirs = set()
        has_root_files = False
        for _, arc_name in file_pairs:
            parts = Path(arc_name).parts
            if len(parts) > 1:
                top_dirs.add(parts[0])
            else:
                has_root_files = True

        # 若根目錄有散落檔案，或者頂層目錄不只一個，代表缺乏單一資料夾包裹
        if has_root_files or len(top_dirs) > 1:
            needs_wrapper = True
        else:
            # 如果內部已經有唯一頂層目錄，但名稱與我們要的不同，也可以視需求決定是否套用
            needs_wrapper = False

    # 2. 寫入 ZIP
    with zipfile.ZipFile(target_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
        for disk_path, arc_name in file_pairs:
            if needs_wrapper:
                final_arc_name = f"{root_folder_name}/{arc_name}"
            else:
                final_arc_name = arc_name
            zf.write(disk_path, arcname=final_arc_name)


def safe_move_file(src_path: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / src_path.name
    counter = 1
    while dst_path.exists():
        dst_path = dst_dir / f"{src_path.stem}_{counter}{src_path.suffix}"
        counter += 1
    shutil.move(str(src_path), str(dst_path))


def get_dir_size_bytes(directory: Path) -> int:
    if not directory.exists():
        return 0
    total = 0
    for p in directory.rglob("*"):
        if p.is_file() and not p.is_symlink():
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return total


def format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def _process_single_page_task(args):
    """供內部 ThreadPool 並行調用的單圖縮放工作單元"""
    idx, img_path, rel_path, out_img_path = args
    try:
        resize_and_convert_image(img_path, out_img_path)
        new_rel_path = str(Path(rel_path).with_suffix('.jpg'))
        return (out_img_path, new_rel_path)
    except Exception:
        return (img_path, rel_path)


def execute_pipeline(archive_path, resized_dir, anim_dir, media_dir, original_files_dir, temp_target_dir, tier_tag, worker_id, status_dict):
    stem_name = archive_path.stem

    def update_extract_progress(ratio: float, elapsed: float):
        spin = SPINNER_CHARS[int(elapsed * 4) % len(SPINNER_CHARS)]
        mapped_pct = ratio * 0.25
        status_dict[worker_id] = {
            "tier": tier_tag,
            "stage": f"[bold yellow]{spin} 解壓中[/bold yellow]",
            "name": archive_path.name,
            "progress": mapped_pct,
            "detail": f"{elapsed:.1f}s ({int(ratio * 100)}%)"
        }

    with tempfile.TemporaryDirectory(dir=temp_target_dir) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        extracted_dir = temp_dir / "extracted"
        processed_dir_tmp = temp_dir / "processed"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        processed_dir_tmp.mkdir(parents=True, exist_ok=True)

        success, reason = extract_archive_stream(archive_path, extracted_dir, update_extract_progress)
        if not success:
            return False, reason, 0

        status_dict[worker_id] = {
            "tier": tier_tag,
            "stage": "[cyan]掃描結構[/cyan]",
            "name": archive_path.name,
            "progress": 0.25,
            "detail": "分類中"
        }
        static_images = []
        animated_images = []
        media_files = []

        for root, _, files in os.walk(extracted_dir):
            for file in files:
                if file.startswith("._") or file == ".DS_Store":
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(extracted_dir)
                ext = file_path.suffix.lower()

                if ext in STATIC_IMAGE_EXTS:
                    if ext in ('.webp', '.gif') and is_image_animated(file_path):
                        animated_images.append((file_path, str(rel_path)))
                    else:
                        static_images.append((file_path, str(rel_path)))
                elif ext in MEDIA_EXTS:
                    media_files.append((file_path, str(rel_path)))

        if not static_images and not animated_images and not media_files:
            return False, "NO_VALID_FILES", 0

        # ========== 動態微批次自適應並行轉檔 (隨時吸收剛釋放的空閒核心) ==========
        total_imgs = len(static_images)
        processed_images = []

        tasks = [
            (idx, img_path, rel_path, processed_dir_tmp / f"img_{idx:05d}.jpg")
            for idx, (img_path, rel_path) in enumerate(static_images)
        ]

        CHUNK_SIZE = 24  # 每 24 張圖為一個調度週期
        max_system_cores = min(12, os.cpu_count() or 4)

        for chunk_start in range(0, total_imgs, CHUNK_SIZE):
            chunk_tasks = tasks[chunk_start:chunk_start + CHUNK_SIZE]

            idle_count = sum(
                1 for wid, info in status_dict.items()
                if "閒置" in info.get("stage", "") and wid != worker_id
            )

            current_concurrency = min(max(1, idle_count + 1), max_system_cores)
            stage_desc = f"[magenta]影像轉檔({current_concurrency}T)[/magenta]" if current_concurrency > 1 else "[magenta]影像轉檔[/magenta]"

            if current_concurrency > 1:
                with ThreadPoolExecutor(max_workers=current_concurrency) as chunk_pool:
                    chunk_results = list(chunk_pool.map(_process_single_page_task, chunk_tasks))
            else:
                chunk_results = [_process_single_page_task(t) for t in chunk_tasks]

            processed_images.extend(chunk_results)

            done_count = len(processed_images)
            pct = 0.25 + (0.65 * (done_count / max(1, total_imgs)))
            status_dict[worker_id] = {
                "tier": tier_tag,
                "stage": stage_desc,
                "name": archive_path.name,
                "progress": pct,
                "detail": f"{done_count}/{total_imgs} 頁"
            }
        # ========================================================================

        status_dict[worker_id] = {
            "tier": tier_tag,
            "stage": "[blue]快速封裝[/blue]",
            "name": archive_path.name,
            "progress": 0.95,
            "detail": "STORE 寫入"
        }
        # 漫畫維持根目錄直接存放圖片，方便閱讀器瀏覽
        if processed_images:
            create_zip_store(resized_dir / f"{stem_name}{ARCHIVE_MAIN_EXT}", processed_images)

        # 動態圖片與媒體檔案強制在內部包裹一層同名根目錄，確保解壓縮時必定產生同名資料夾
        if animated_images:
            create_zip_store(
                anim_dir / f"{stem_name}-Animated{ARCHIVE_OTHER_EXT}",
                animated_images,
                root_folder_name=f"{stem_name}-Animated"
            )
        if media_files:
            create_zip_store(
                media_dir / f"{stem_name}-Media{ARCHIVE_OTHER_EXT}",
                media_files,
                root_folder_name=f"{stem_name}-Media"
            )

    status_dict[worker_id] = {
        "tier": tier_tag,
        "stage": "[dim]移動歸檔[/dim]",
        "name": archive_path.name,
        "progress": 1.0,
        "detail": "搬移原檔"
    }
    safe_move_file(archive_path, original_files_dir)
    return True, "SUCCESS", len(static_images)


def worker_task(
    archive_path_str: str,
    target_tier: str,
    reserved_mb: float,
    resized_dir_str: str,
    anim_dir_str: str,
    media_dir_str: str,
    original_files_dir_str: str,
    error_dir_str: str,
    file_err_dir_str: str,
    worker_id: int,
    status_dict,
    recent_logs,
    ram_manager_tuple
):
    archive_path = Path(archive_path_str)
    resized_dir = Path(resized_dir_str)
    anim_dir = Path(anim_dir_str)
    media_dir = Path(media_dir_str)
    original_files_dir = Path(original_files_dir_str)
    error_dir = Path(error_dir_str)
    file_err_dir = Path(file_err_dir_str)

    current_allocated_ram, ram_budget_mb, ram_lock = ram_manager_tuple

    if target_tier == "RAM":
        tier_tag = "[green]RAM-DISK[/green]"
        temp_target_dir = str(RAM_DISK_MOUNT)
    else:
        tier_tag = "[yellow]SSD-執行[/yellow]"
        temp_target_dir = None

    start_task_time = time.time()
    clean_name = sanitize_log_text(archive_path.name)
    try:
        ok, reason, img_count = execute_pipeline(
            archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
            temp_target_dir, tier_tag, worker_id, status_dict
        )

        if not ok and reason == "NO_SPACE" and temp_target_dir is not None:
            recent_logs.append(("WARN", clean_name, "RAM轉SSD"))
            tier_tag = "[yellow]SSD-重試[/yellow]"
            ok, reason, img_count = execute_pipeline(
                archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
                None, tier_tag, worker_id, status_dict
            )
            if not ok:
                safe_move_file(archive_path, error_dir)
                recent_logs.append(("SYS_ERR", clean_name, "重試失敗"))
                status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
                return archive_path_str, "ERROR", 0

        elif not ok and reason in ("CORRUPTED", "NO_VALID_FILES"):
            safe_move_file(archive_path, file_err_dir)
            recent_logs.append(("FILE_ERR", clean_name, "損毀壞檔"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "FILE_ERR", 0

        elif not ok:
            safe_move_file(archive_path, error_dir)
            recent_logs.append(("SYS_ERR", clean_name, "執行異常"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ERROR", 0

    finally:
        if target_tier == "RAM" and reserved_mb > 0:
            with ram_lock:
                current_allocated_ram.value = max(0.0, current_allocated_ram.value - reserved_mb)

    total_cost = time.time() - start_task_time
    recent_logs.append(("OK", clean_name, f"{total_cost:.1f}s, {img_count}P"))
    status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": "等待指派"}
    return archive_path_str, "SUCCESS", total_cost


def create_mini_bar(pct: float, width=8) -> str:
    pct = max(0.0, min(1.0, pct))
    filled = int(width * pct)
    empty = width - filled
    bar_str = "█" * filled + "░" * empty
    return f"[cyan]{bar_str}[/cyan] [bold white]{int(pct * 100):3d}%[/bold white]"


def build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active: bool, ram_disk_gb: int, strict_ram_mode: bool):
    # 1. 核心工作泳道表格配置
    worker_table = Table(box=box.SIMPLE, expand=True, pad_edge=False, show_header=True)
    worker_table.add_column("核心", style="bold cyan", width=5, justify="center")
    worker_table.add_column("層級", width=9, justify="center")
    worker_table.add_column("狀態", width=12, justify="center")
    worker_table.add_column("進度", width=14)
    worker_table.add_column("檔案名稱", style="white", ratio=1, no_wrap=True, overflow="ellipsis")
    worker_table.add_column("細節", style="dim", width=11, justify="right", no_wrap=True)

    for wid in range(num_workers):
        info = worker_statuses.get(wid, {
            "tier": "[dim]-[/dim]",
            "stage": "準備",
            "name": "-",
            "progress": 0.0,
            "detail": ""
        })
        
        raw_name = sanitize_log_text(info.get("name", "-"))
        display_name = raw_name if raw_name != "-" else "[dim]-[/dim]"

        stage_str = info.get("stage", "準備")
        stage_display = stage_str if "閒置" not in stage_str else "[dim]閒置[/dim]"

        worker_table.add_row(
            f"C{wid+1:02d}",
            info.get("tier", "-"),
            stage_display,
            create_mini_bar(info.get("progress", 0.0), width=8),
            display_name,
            info.get("detail", "")
        )

    # 2. 近期動態表格配置（結構化三欄：狀態 / 彈性檔名 / 優先靠右數據）[cite: 7]
    logs_table = Table(box=box.SIMPLE, expand=True, show_header=False, pad_edge=False)
    logs_table.add_column("狀態", width=10, justify="center", no_wrap=True)
    logs_table.add_column("檔案名稱", ratio=1, no_wrap=True, overflow="ellipsis")
    logs_table.add_column("數據", width=16, justify="right", style="dim", no_wrap=True)
    
    log_display_lines = max(6, min(num_workers, 14))
    display_logs = list(recent_logs)[-log_display_lines:]
    
    if not display_logs:
        logs_table.add_row("", "[dim]尚無處理紀錄...[/dim]", "")
    else:
        for item in display_logs:
            if isinstance(item, (tuple, list)) and len(item) == 3:
                tag, name, stat = item
                if tag == "OK":
                    status_cell = "[bold green][OK][/bold green]"
                elif tag == "FILE_ERR":
                    status_cell = "[bold red][壞檔][/bold red]"
                elif tag == "SYS_ERR":
                    status_cell = "[bold red][異常][/bold red]"
                else:
                    status_cell = "[bold yellow][注意][/bold yellow]"
                logs_table.add_row(status_cell, name, f"({stat})")
            else:
                logs_table.add_row("[dim]::[/dim]", str(item), "")

    ram_usage_text, ram_pct = get_ram_disk_usage()
    ram_style = "bold red" if ram_pct > 85 else ("bold yellow" if ram_pct > 60 else "bold green")
    mode_text = "[bold green]RAM 獨占[/bold green]" if strict_ram_mode else "[yellow]RAM 彈性[/yellow]"

    header_markup = (
        f"  [dim]:: CPU:[/dim] [bold cyan]{num_workers}C[/bold cyan]  "
        f"|  [dim]:: RAM:[/dim] [{ram_style}]{ram_disk_gb}GB ({ram_usage_text})[/{ram_style}]  "
        f"|  [dim]:: MODE:[/dim] {mode_text}  "
        f"|  [dim]:: ABORT:[/dim] [bold red]qqq[/bold red]  "
        f"|  [dim]:: ENGINE:[/dim] [bold magenta]{SEVEN_ZIP_BIN} STORE[/bold magenta]"
    )
    header_info = Text.from_markup(header_markup)

    layout = Layout()
    layout.split_column(
        Layout(Panel(header_info, box=box.ROUNDED, style="on grey11"), size=3),
        Layout(Panel(progress, title="[bold cyan]總體任務進度[/bold cyan]", border_style="cyan"), size=4),
        Layout(name="body")
    )
    
    layout["body"].split_row(
        Layout(Panel(worker_table, title="[bold green]核心工作泳道[/bold green]", border_style="green"), ratio=52),
        Layout(Panel(logs_table, title="[bold white]近期動態[/bold white]", border_style="blue"), ratio=48)
    )
    return layout


def print_summary_card(
    console, total_time_sec, total_count, success_count, fail_err_count, corrupted_count,
    resized_dir, anim_dir, media_dir, original_files_dir, error_dir, file_err_dir, file_err_stems, aborted=False
):
    original_bytes = get_dir_size_bytes(original_files_dir)
    resized_bytes = get_dir_size_bytes(resized_dir)
    anim_bytes = get_dir_size_bytes(anim_dir)
    media_bytes = get_dir_size_bytes(media_dir)

    output_total_bytes = resized_bytes + anim_bytes + media_bytes
    saved_bytes = original_bytes - output_total_bytes
    pct_saved = (saved_bytes / original_bytes * 100) if original_bytes > 0 else 0.0

    hrs, rem = divmod(int(total_time_sec), 3600)
    mins, secs = divmod(rem, 60)
    time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
    done_count = success_count + corrupted_count + fail_err_count
    avg_per_file = (total_time_sec / max(1, done_count))

    summary_text = Text()
    if aborted:
        summary_text.append("[!] 使用者已連續輸入 [qqq] 中止作業，已妥善保存目前進度。\n\n", style="bold red")

    summary_text.append(">> 執行耗時 : ", style="bold cyan")
    summary_text.append(f"{time_str}", style="bold white")
    summary_text.append(f" (平均 {avg_per_file:.1f} 秒/檔案)\n", style="dim")

    summary_text.append(">> 檔案結算 : ", style="bold cyan")
    summary_text.append(f"共掃描 {total_count} 個 / 已處置 {done_count} 個", style="bold white")
    summary_text.append(f" (成功: ", style="dim")
    summary_text.append(f"{success_count}", style="bold green")
    summary_text.append(f", 損毀: ", style="dim")
    summary_text.append(f"{corrupted_count}", style="bold red" if corrupted_count > 0 else "dim")
    summary_text.append(f", 異常: ", style="dim")
    summary_text.append(f"{fail_err_count}", style="bold yellow" if fail_err_count > 0 else "dim")
    summary_text.append(")\n\n", style="dim")

    summary_text.append(">> 空間節省統計:\n", style="bold yellow")
    summary_text.append(f"   * 已歸檔原檔體積 (OriginalFiles) : {format_bytes(original_bytes)}\n", style="white")
    summary_text.append(f"   * 最佳化成品體積 (Resized+其他)  : {format_bytes(output_total_bytes)}\n", style="white")
    if saved_bytes > 0:
        summary_text.append(f"   * 空間縮減 (節省容量)          : ", style="white")
        summary_text.append(f"{format_bytes(saved_bytes)} (▼ {pct_saved:.1f}%)\n", style="bold green")
    else:
        summary_text.append(f"   * 空間變化                     : 原圖尺寸較小或已為高度壓縮檔\n", style="dim")

    summary_text.append("\n>> 目錄產出狀態:\n", style="bold magenta")
    if resized_dir.exists():
        summary_text.append(f"   * 漫畫書庫 : {resized_dir} ({format_bytes(resized_bytes)})\n", style="white")
    if anim_dir.exists():
        summary_text.append(f"   * 動態圖片 : {anim_dir} ({format_bytes(anim_bytes)})\n", style="white")
    if media_dir.exists():
        summary_text.append(f"   * 影音檔案 : {media_dir} ({format_bytes(media_bytes)})\n", style="white")
    if original_files_dir.exists():
        summary_text.append(f"   * 原檔歸檔 : {original_files_dir} ({format_bytes(original_bytes)})\n", style="white")
    
    # 輸出 FileErr 純檔名清單檔及 E-Hentai 搜尋導航 HTML (智慧合併當日歷史，避免同日多輪被覆蓋)
    if file_err_dir.exists() and (corrupted_count > 0 or (file_err_dir / "corrupted_list.txt").exists()):
        list_file = file_err_dir / "corrupted_list.txt"
        html_file = file_err_dir / "corrupted_search.html"
        try:
            existing_stems = set()
            if list_file.exists():
                for line in list_file.read_text(encoding="utf-8").splitlines():
                    clean_line = line.strip()
                    if clean_line:
                        existing_stems.add(clean_line)

            all_stems = existing_stems.union(set(file_err_stems))
            sorted_stems = sorted(list(all_stems), key=natural_sort_key)
            list_file.write_text("\n".join(sorted_stems), encoding="utf-8")

            records = []
            for raw_stem in sorted_stems:
                q = clean_to_query(raw_stem)
                if q:
                    encoded_q = urllib.parse.quote_plus(q)
                    eh_url = f"https://e-hentai.org/?f_search={encoded_q}&f_cats=0"
                    records.append((raw_stem, q, eh_url))

            if records:
                generate_eh_search_html(records, html_file)

            total_bad = len(sorted_stems)
            summary_text.append(f"   * 損毀檔案 : {file_err_dir} (本次新增: {corrupted_count} 個 / 當日累計: {total_bad} 個)\n", style="bold red")
            summary_text.append(f"     |- 清單已更新至: {list_file.name} (無副檔名)\n", style="dim")
            summary_text.append(f"     |- 導航已更新至: {html_file.name} (E-Hentai 搜尋導航表)\n", style="bold cyan")
        except Exception:
            summary_text.append(f"   * 損毀檔案 : {file_err_dir} ({corrupted_count} 個損毀檔)\n", style="bold red")

    if error_dir.exists() and fail_err_count > 0:
        summary_text.append(f"   * 執行異常 : {error_dir} ({fail_err_count} 個檔案)\n", style="bold yellow")

    card_title = "[bold red][ ABORTED ] 任務中止結算報告[/bold red]" if aborted else "[bold green][ COMPLETE ] 處理成果結算報告[/bold green]"
    border_style = "red" if aborted else "green"
    console.print(Panel(summary_text, title=card_title, border_style=border_style, expand=False))


def is_system_generated_path(path: Path, source_dir: Path) -> bool:
    """檢查路徑相對於 source_dir 的子目錄是否符合產出目錄前綴（不檢查父層及自身根路徑）"""
    try:
        rel_parts = path.relative_to(source_dir).parts
        for part in rel_parts[:-1]:
            if part.startswith(SYSTEM_DIR_PREFIXES):
                return True
    except Exception:
        pass
    return False


def main():
    console = Console()

    if len(sys.argv) < 2:
        src_folder = console.input("[bold yellow]請輸入包含壓縮檔的資料夾路徑: [/bold yellow]").strip()
    else:
        src_folder = sys.argv[1].strip()

    source_dir = Path(src_folder).expanduser().resolve()
    if not source_dir.is_dir():
        console.print(f"[bold red][ERR] 路徑不存在：{source_dir}[/bold red]")
        sys.exit(1)

    today_str = datetime.now().strftime("%Y-%m-%d")
    resized_dir = source_dir / f"Resized-{today_str}"
    anim_dir = source_dir / f"Animated-{today_str}"
    media_dir = source_dir / f"Media-{today_str}"
    original_files_dir = source_dir / f"OriginalFiles-{today_str}"
    error_dir = source_dir / f"Error-{today_str}"
    file_err_dir = source_dir / f"FileErr-{today_str}"

    archive_files = [
        p for p in source_dir.rglob("*")
        if p.is_file() 
        and p.suffix.lower() in ARCHIVE_EXTENSIONS 
        and not p.name.startswith("._")
        and not is_system_generated_path(p, source_dir)
    ]

    if not archive_files:
        console.print("[yellow]未找到任何待處理的壓縮檔案（可能已全數歸檔或全部屬於已處理目錄）。[/yellow]")
        return

    num_workers = max(1, os.cpu_count() - 1)

    # 1. 互動式手動設定 RAM Disk 大小
    suggested_gb = get_recommended_ram_disk_gb()
    user_ram_input = console.input(
        f"[bold yellow]請輸入欲配置的 RAM Disk 大小 (GB) [建議: {suggested_gb}，輸入 0 則不使用]: [/bold yellow]"
    ).strip()

    if user_ram_input == "":
        ram_disk_gb = suggested_gb
    else:
        try:
            ram_disk_gb = max(0, int(user_ram_input))
        except ValueError:
            console.print(f"[yellow]輸入格式無效，自動採用建議值: {suggested_gb} GB[/yellow]")
            ram_disk_gb = suggested_gb

    strict_ram_mode = False
    if ram_disk_gb > 0:
        strict_input = console.input(
            "[bold yellow]是否啟用「純 RAM 模式」？(空間不足時持續等待前一任務完成，不退回 SSD) \[Y/n]: [/bold yellow]"
        ).strip().lower()

        if strict_input == "" or strict_input in ('y', 'yes'):
            strict_ram_mode = True
        else:
            strict_ram_mode = False

        console.print(f"[cyan]正在初始化 {ram_disk_gb} GB RAM Disk 環境...[/cyan]")
        ram_path = setup_ram_disk(ram_disk_gb)
        ram_active = ram_path is not None
        if ram_active:
            mode_desc = "純 RAM 獨占排程 (保護 SSD)" if strict_ram_mode else "RAM 彈性排程 (超限走 SSD)"
            console.print(f"[bold green][OK] 已成功配置 {ram_disk_gb} GB RAM Disk！模式: {mode_desc}[/bold green]")
        else:
            console.print("[yellow][WARN] RAM Disk 建立失敗，將直接使用系統 SSD 進行暫存。[/yellow]")
    else:
        ram_active = False
        console.print("[yellow]已設定為 0 GB，本次作業將全面走本機 SSD 執行。[/yellow]")

    # 2. 空間記帳員狀態
    manager = multiprocessing.Manager()
    worker_statuses = manager.dict()
    recent_logs = manager.list()
    file_err_stems = manager.list()
    for i in range(num_workers):
        worker_statuses[i] = {"tier": "[dim]-[/dim]", "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}

    ram_budget_mb = (ram_disk_gb * 1024 * 0.96) if ram_active else 0.0
    current_allocated_ram = manager.Value('d', 0.0)
    ram_lock = manager.Lock()
    ram_manager_tuple = (current_allocated_ram, ram_budget_mb, ram_lock)

    # 3. 極速前置預檢 (搭配即時動態進度條)
    pending_queue = []
    max_inspect_threads = min(32, (os.cpu_count() or 4) * 4)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]:: 檔案展開尺寸預檢[/bold cyan]"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("-"),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[current_file]}[/dim]"),
        console=console
    ) as inspect_progress:
        inspect_task = inspect_progress.add_task(
            "inspect", total=len(archive_files), current_file="準備中..."
        )
        
        with ThreadPoolExecutor(max_workers=max_inspect_threads) as inspector:
            future_to_arch = {
                inspector.submit(inspect_archive_worker, arch): arch
                for arch in archive_files
            }
            
            for future in as_completed(future_to_arch):
                arch = future_to_arch[future]
                clean_inspect_name = sanitize_log_text(arch.name)
                short_name = clean_inspect_name if len(clean_inspect_name) <= 28 else clean_inspect_name[:12] + "..." + clean_inspect_name[-13:]
                try:
                    res = future.result()
                    pending_queue.append(res)
                except Exception:
                    pending_queue.append({
                        "path": arch,
                        "uncompressed_mb": (arch.stat().st_size * 1.2) / (1024 * 1024),
                        "retries": 0
                    })
                inspect_progress.update(inspect_task, advance=1, current_file=short_name)

    pending_queue.sort(key=lambda x: x["uncompressed_mb"], reverse=True)
    console.print("[bold green][OK] 檔案尺寸預檢完成！[/bold green]\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("-"),
        TimeRemainingColumn(),
    )
    task_id = progress.add_task("壓縮檔排程 (隨時輸入 qqq 中止)...", total=len(archive_files))

    abort_listener = KeyAbortListener()
    abort_listener.start()

    global_start_time = time.time()
    success_count = 0
    fail_err_count = 0
    corrupted_count = 0
    was_aborted = False

    available_workers = set(range(num_workers))
    active_futures = {}

    try:
        with Live(
            build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active, ram_disk_gb, strict_ram_mode),
            refresh_per_second=4,
            console=console
        ) as live:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                while (pending_queue or active_futures) and not was_aborted:
                    if abort_listener.aborted:
                        was_aborted = True
                        recent_logs.append(("SYS_ERR", "使用者連續輸入 qqq", "停止核心"))
                        for p in executor._processes.values():
                            try:
                                p.terminate()
                            except Exception:
                                pass
                        break

                    done_futures = [f for f in active_futures if f.done()]
                    for f in done_futures:
                        worker_id = active_futures.pop(f)
                        available_workers.add(worker_id)
                        
                        try:
                            arch_path_done, result_code, _ = f.result()
                            if result_code == "SUCCESS":
                                success_count += 1
                            elif result_code == "FILE_ERR":
                                corrupted_count += 1
                                file_err_stems.append(Path(arch_path_done).stem)
                            else:
                                fail_err_count += 1
                        except Exception:
                            fail_err_count += 1

                        progress.advance(task_id, 1)

                    while available_workers and pending_queue and not was_aborted:
                        if abort_listener.aborted:
                            was_aborted = True
                            break

                        assigned = False
                        for idx, item in enumerate(pending_queue):
                            needed_mb = item["uncompressed_mb"]
                            
                            if not ram_active or needed_mb > ram_budget_mb:
                                target_tier = "SSD"
                                reserved_mb = 0.0
                                chosen_item = pending_queue.pop(idx)
                                assigned = True
                                break

                            can_allocate = False
                            with ram_lock:
                                if current_allocated_ram.value + needed_mb <= ram_budget_mb:
                                    current_allocated_ram.value += needed_mb
                                    can_allocate = True

                            if can_allocate:
                                target_tier = "RAM"
                                reserved_mb = needed_mb
                                chosen_item = pending_queue.pop(idx)
                                assigned = True
                                break
                            else:
                                if strict_ram_mode:
                                    continue
                                else:
                                    if item["retries"] >= MAX_RAM_RETRIES:
                                        target_tier = "SSD"
                                        reserved_mb = 0.0
                                        chosen_item = pending_queue.pop(idx)
                                        assigned = True
                                        break
                                    else:
                                        item["retries"] += 1

                        if assigned:
                            worker_id = available_workers.pop()
                            f = executor.submit(
                                worker_task,
                                str(chosen_item["path"]),
                                target_tier,
                                reserved_mb,
                                str(resized_dir),
                                str(anim_dir),
                                str(media_dir),
                                str(original_files_dir),
                                str(error_dir),
                                str(file_err_dir),
                                worker_id,
                                worker_statuses,
                                recent_logs,
                                ram_manager_tuple
                            )
                            active_futures[f] = worker_id
                        else:
                            break

                    live.update(
                        build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active, ram_disk_gb, strict_ram_mode)
                    )
                    time.sleep(0.1)

    finally:
        abort_listener.stop()
        if ram_active:
            console.print("\n[cyan]正在安全卸載 RAM Disk...[/cyan]")
            cleanup_ram_disk()

    global_cost = time.time() - global_start_time

    print_summary_card(
        console,
        global_cost,
        len(archive_files),
        success_count,
        fail_err_count,
        corrupted_count,
        resized_dir,
        anim_dir,
        media_dir,
        original_files_dir,
        error_dir,
        file_err_dir,
        file_err_stems,
        aborted=was_aborted
    )


if __name__ == "__main__":
    main()