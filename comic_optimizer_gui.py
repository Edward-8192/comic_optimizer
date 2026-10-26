import os
import sys

# 抑制 macOS Cocoa/Qt 系統輸入法與輔助技術的底層嘈雜 Log
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false"
os.environ["OS_ACTIVITY_MODE"] = "disable"

import re
import csv
import json
import html
import shutil
import sqlite3
import zipfile
import subprocess
import tempfile
import multiprocessing
import time
import threading
import urllib.parse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QSpinBox, QCheckBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMessageBox, QFrame, QAbstractItemView, QTabWidget,
    QListWidget, QListWidgetItem, QComboBox
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor, QCloseEvent, QPainter, QFont, QIcon

# ==================== Core Configuration ====================
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
JPEG_QUALITY = 85

RESOLUTION_PRESETS = [
    ("4K UHD (3840×2160)", 3840, 2160),
    ("QHD 2K (2560×1440)", 2560, 1440),
    ("FHD 1080p (1920×1080)", 1920, 1080),
    ("Tablet HD (1600×1200)", 1600, 1200),
    ("Original Resolution (No Resize)", 0, 0),
]

MODERN_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 8px;
    background-color: #1e293b;
    top: -1px;
}
QTabBar::tab {
    background-color: #0f172a;
    color: #94a3b8;
    border: 1px solid #334155;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #1e293b;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}
QTabBar::tab:hover:!selected {
    background-color: #1e293b;
    color: #cbd5e1;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    selection-background-color: #0284c7;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QListWidget {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
    color: #f1f5f9;
}
QListWidget::item {
    padding: 5px 8px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #0369a1;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #1e293b;
}
QPushButton {
    background-color: #334155;
    color: #f1f5f9;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #475569;
    border-color: #64748b;
}
QPushButton:pressed {
    background-color: #1e293b;
}
QPushButton:disabled {
    background-color: #1e293b;
    color: #475569;
    border-color: #334155;
}
QTableWidget {
    background-color: #0f172a;
    alternate-background-color: #131c31;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #1e293b;
    color: #e2e8f0;
    selection-background-color: #0c4a6e;
    selection-color: #f8fafc;
}
QHeaderView::section {
    background-color: #1e293b;
    color: #94a3b8;
    font-weight: 700;
    font-size: 12px;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #334155;
    border-right: 1px solid #1e293b;
}
QProgressBar {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #0284c7;
    border-radius: 5px;
}
QCheckBox {
    spacing: 6px;
    color: #cbd5e1;
    font-weight: 500;
}
QSplitter::handle {
    background-color: #334155;
    width: 2px;
}
"""

def reveal_in_finder(target_path: Path):
    if not target_path:
        return
    try:
        if target_path.exists():
            if target_path.is_file():
                subprocess.Popen(["open", "-R", str(target_path)])
            else:
                subprocess.Popen(["open", str(target_path)])
        elif target_path.parent.exists():
            subprocess.Popen(["open", str(target_path.parent)])
    except Exception:
        pass
MAX_RAM_RETRIES = 150
RAM_DISK_MOUNT = Path("/Volumes/ComicRamDisk")

ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.cbz', '.cbr'}
STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'}
MEDIA_EXTS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg'
}

SYSTEM_DIR_PREFIXES = (
    "Resized-",
    "Comic-",
    "Animated-",
    "Media-",
    "OriginalFiles-",
    "Processed-",
    "FileErr-",
    "Error-",
    "Unzipped-",
)

ARCHIVE_MAIN_EXT = '.cbz'
ARCHIVE_OTHER_EXT = '.zip'

def get_app_support_dir() -> Path:
    custom_dir = os.environ.get("COMIC_OPTIMIZER_DATA_DIR")
    if custom_dir:
        return Path(custom_dir)
    primary = Path.home() / "Library" / "Application Support" / "ComicOptimizer"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        test_file = primary / ".write_probe"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return primary
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "ComicOptimizer"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

APP_SUPPORT_DIR = get_app_support_dir()
CONFIG_FILE_PATH = APP_SUPPORT_DIR / "config.json"
HISTORY_DB_PATH = APP_SUPPORT_DIR / "history.db"

def ensure_app_support_dir():
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)

def load_app_config() -> dict:
    ensure_app_support_dir()
    if CONFIG_FILE_PATH.exists():
        try:
            return json.loads(CONFIG_FILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_app_config(cfg: dict):
    ensure_app_support_dir()
    try:
        CONFIG_FILE_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

class HistoryDatabase:
    @staticmethod
    def init_db():
        ensure_app_support_dir()
        with sqlite3.connect(HISTORY_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversion_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_dir TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    page_count INTEGER DEFAULT 0,
                    orig_bytes INTEGER DEFAULT 0,
                    out_bytes INTEGER DEFAULT 0,
                    saved_bytes INTEGER DEFAULT 0,
                    duration_sec REAL DEFAULT 0.0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON conversion_history(id DESC)")
            conn.commit()

    @staticmethod
    def add_record(
        filename: str, source_dir: str, output_dir: str, status: str,
        page_count: int, orig_bytes: int, out_bytes: int, duration_sec: float
    ):
        ensure_app_support_dir()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        saved_bytes = (orig_bytes - out_bytes) if status == "SUCCESS" else 0
        try:
            with sqlite3.connect(HISTORY_DB_PATH, timeout=10.0) as conn:
                conn.execute("""
                    INSERT INTO conversion_history (
                        timestamp, filename, source_dir, output_dir, status,
                        page_count, orig_bytes, out_bytes, saved_bytes, duration_sec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts, filename, source_dir, output_dir, status,
                    page_count, orig_bytes, out_bytes, saved_bytes, duration_sec
                ))
                conn.commit()
        except Exception:
            pass

    @staticmethod
    def get_summary_stats() -> dict:
        ensure_app_support_dir()
        try:
            with sqlite3.connect(HISTORY_DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*),
                        SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN status = 'FILE_ERR' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN status = 'SUCCESS' THEN page_count ELSE 0 END),
                        SUM(CASE WHEN status = 'SUCCESS' THEN orig_bytes ELSE 0 END),
                        SUM(CASE WHEN status = 'SUCCESS' THEN out_bytes ELSE 0 END),
                        SUM(CASE WHEN status = 'SUCCESS' THEN saved_bytes ELSE 0 END)
                    FROM conversion_history
                """)
                row = cur.fetchone()
                if row:
                    return {
                        "total_count": row[0] or 0,
                        "success_count": row[1] or 0,
                        "corrupted_count": row[2] or 0,
                        "error_count": row[3] or 0,
                        "total_pages": row[4] or 0,
                        "total_orig_bytes": row[5] or 0,
                        "total_out_bytes": row[6] or 0,
                        "total_saved_bytes": row[7] or 0,
                    }
        except Exception:
            pass
        return {
            "total_count": 0, "success_count": 0, "corrupted_count": 0, "error_count": 0,
            "total_pages": 0, "total_orig_bytes": 0, "total_out_bytes": 0, "total_saved_bytes": 0
        }

    @staticmethod
    def query_records(search_text: str = "", limit: int = 1000) -> list:
        ensure_app_support_dir()
        try:
            with sqlite3.connect(HISTORY_DB_PATH) as conn:
                cur = conn.cursor()
                if search_text.strip():
                    kw = f"%{search_text.strip()}%"
                    cur.execute("""
                        SELECT timestamp, filename, status, page_count, orig_bytes, out_bytes, saved_bytes, duration_sec, source_dir, output_dir
                        FROM conversion_history
                        WHERE filename LIKE ? OR source_dir LIKE ? OR status LIKE ?
                        ORDER BY id DESC LIMIT ?
                    """, (kw, kw, kw, limit))
                else:
                    cur.execute("""
                        SELECT timestamp, filename, status, page_count, orig_bytes, out_bytes, saved_bytes, duration_sec, source_dir, output_dir
                        FROM conversion_history
                        ORDER BY id DESC LIMIT ?
                    """, (limit,))
                return cur.fetchall()
        except Exception:
            return []

    @staticmethod
    def clear_all():
        ensure_app_support_dir()
        try:
            with sqlite3.connect(HISTORY_DB_PATH) as conn:
                conn.execute("DELETE FROM conversion_history")
                conn.commit()
        except Exception:
            pass

def get_resource_path(relative_path: str) -> str:
    """取得 PyInstaller 打包後的內部資源路徑或開發時的本地路徑"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, relative_path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(os.path.abspath("."), relative_path)

def get_app_icon() -> QIcon:
    for icon_name in ("app_icon.png", "app_icon.icns"):
        icon_path = get_resource_path(icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
    return QIcon()

def find_7z_binary() -> str:
    bundled_7zz = get_resource_path("7zz")
    if os.path.exists(bundled_7zz) and os.access(bundled_7zz, os.X_OK):
        return bundled_7zz
    for binary in ["7zz", "7z"]:
        if shutil.which(binary):
            return binary
    return "7z"

SEVEN_ZIP_BIN = find_7z_binary()

def sanitize_log_text(text: str) -> str:
    # 僅濾除高位元面補充區的彩色 Emoji，完整保留中日韓漢字 (CJK)、假名與全形標點符號
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
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text)

def clean_to_query(line: str) -> str:
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
    rows_html = []
    for idx, (original, query, eh_url) in enumerate(records, 1):
        safe_orig = html.escape(original)
        safe_query = html.escape(query)
        rows_html.append(f"""
        <tr>
            <td style="text-align:center;">{idx}</td>
            <td style="word-break:break-all;">{safe_orig}</td>
            <td><code>{safe_query}</code></td>
            <td style="text-align:center;">
                <a href="{eh_url}" target="_blank" rel="noopener noreferrer" style="background:#6366f1;color:#fff;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:0.88rem;">
                    Search on E-Hentai
                </a>
            </td>
        </tr>
        """)
    table_rows = "\n".join(rows_html)
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Corrupted Archives Recovery Navigation</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f1f5f9; padding: 24px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.95rem; }}
        th, td {{ padding: 12px 14px; border-bottom: 1px solid #334155; text-align: left; }}
        th {{ background: #1e293b; position: sticky; top: 0; }}
        code {{ background: #1e293b; color: #38bdf8; padding: 3px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h2>Corrupted Archives Recovery List (Total: {len(records)})</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 50px; text-align: center;">#</th>
                <th style="width: 45%;">Original Filename</th>
                <th style="width: 35%;">Search Query</th>
                <th style="width: 15%; text-align: center;">Action</th>
            </tr>
        </thead>
        <tbody>{table_rows}</tbody>
    </table>
</body>
</html>"""
    output_filepath.write_text(html_content, encoding="utf-8")

def get_recommended_ram_disk_gb() -> int:
    try:
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        total_ram_gb = mem_bytes / (1024 ** 3)
        if total_ram_gb >= 64.0: return 36
        elif total_ram_gb >= 36.0: return 20
        elif total_ram_gb >= 24.0: return 14
        elif total_ram_gb >= 16.0: return 9
        else: return 4
    except Exception:
        return 12

def setup_ram_disk(size_gb: int) -> Path:
    if size_gb <= 0: return None
    if RAM_DISK_MOUNT.exists(): return RAM_DISK_MOUNT
    sectors = size_gb * 1024 * 1024 * 1024 // 512
    try:
        dev = subprocess.check_output(["hdiutil", "attach", "-nomount", f"ram://{sectors}"], stderr=subprocess.DEVNULL).decode().strip()
        subprocess.check_call(["diskutil", "erasevolume", "HFS+", RAM_DISK_MOUNT.name, dev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return RAM_DISK_MOUNT
    except Exception:
        return None

def cleanup_ram_disk():
    if RAM_DISK_MOUNT.exists():
        subprocess.run(["diskutil", "eject", str(RAM_DISK_MOUNT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_ram_disk_usage():
    if not RAM_DISK_MOUNT.exists(): return "Disabled", 0.0
    try:
        stat = shutil.disk_usage(RAM_DISK_MOUNT)
        used_mb = (stat.total - stat.free) / (1024 * 1024)
        total_mb = stat.total / (1024 * 1024)
        pct = (used_mb / total_mb) * 100
        return f"{used_mb:.0f}MB/{total_mb/1024:.1f}GB ({pct:.1f}%)", pct
    except Exception:
        return "Unknown", 0.0

def get_ram_disk_free_mb() -> float:
    if not RAM_DISK_MOUNT.exists():
        return 0.0
    try:
        return shutil.disk_usage(RAM_DISK_MOUNT).free / (1024 * 1024)
    except Exception:
        return 0.0

def get_uncompressed_size_mb_fast(archive_path: Path) -> float:
    ext = archive_path.suffix.lower()
    try:
        if ext in ('.zip', '.cbz'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                total_bytes = sum(zinfo.file_size for zinfo in zf.infolist())
                # 預留 8% 檔案系統區塊與暫存緩衝
                return (total_bytes * 1.08) / (1024 * 1024)
        else:
            return (archive_path.stat().st_size * 1.30) / (1024 * 1024)
    except Exception:
        return (archive_path.stat().st_size * 1.30) / (1024 * 1024)

def inspect_archive_worker(item_dict: dict):
    arch = item_dict["path"]
    return {
        "path": arch,
        "src_root": item_dict["src_root"],
        "uncompressed_mb": get_uncompressed_size_mb_fast(arch),
        "retries": 0,
        "ram_oom_retries": 0,
        "force_ssd": False
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

def resize_and_convert_image(
    src_path: Path, dst_path: Path,
    max_w: int = MAX_WIDTH, max_h: int = MAX_HEIGHT, jpeg_quality: int = JPEG_QUALITY
):
    with Image.open(src_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha_img = img.convert("RGBA")
            background.paste(alpha_img, mask=alpha_img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if max_w > 0 and max_h > 0:
            orig_w, orig_h = img.size
            ratio = min(max_w / orig_w, max_h / orig_h)
            if ratio < 1.0:
                new_w = int(orig_w * ratio)
                new_h = int(orig_h * ratio)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        img.save(dst_path, format="JPEG", quality=jpeg_quality, optimize=True)

def extract_archive_stream(archive_path: Path, extract_dir: Path, progress_callback=None, abort_flag=None):
    ext = archive_path.suffix.lower()
    start_time = time.time()
    try:
        if ext in ('.zip', '.cbz'):
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    members = zf.infolist()
                    total = len(members)
                    for idx, member in enumerate(members):
                        if abort_flag is not None and abort_flag.value:
                            return False, "ABORTED"
                        zf.extract(member, extract_dir)
                        if progress_callback and (idx % 12 == 0 or idx == total - 1):
                            elapsed = time.time() - start_time
                            progress_callback((idx + 1) / max(1, total), elapsed)
                return True, "SUCCESS"
            except OSError as e:
                if e.errno == 28 or "No space left on device" in str(e):
                    return False, "NO_SPACE"
                return False, "CORRUPTED"
            except Exception:
                return False, "CORRUPTED"
        elif ext in ('.rar', '.cbr', '.7z'):
            cmd = [SEVEN_ZIP_BIN, "x", str(archive_path), f"-o{extract_dir}", "-y", "-p-", "-bsp1"]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            except FileNotFoundError:
                return False, "CORRUPTED"
            pct_pattern = re.compile(r'(\d+)%')
            current_pct = 0.0
            captured_output = []
            while True:
                if abort_flag is not None and abort_flag.value:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return False, "ABORTED"
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
            if abort_flag is not None and abort_flag.value:
                return False, "ABORTED"
            if proc.returncode == 0:
                return True, "SUCCESS"
            all_err = "".join(captured_output) + (" " + stderr_out if stderr_out else "")
            if any(k in all_err.lower() for k in ["no space left", "not enough space", "disk full", "write error"]):
                return False, "NO_SPACE"
            return False, "CORRUPTED"
    except Exception as e:
        if "No space left on device" in str(e): return False, "NO_SPACE"
        return False, "CORRUPTED"

def create_zip_store(
    target_archive: Path, file_pairs: list, root_folder_name: str = None,
    consume_source: bool = False, abort_flag=None, progress_callback=None
):
    if not file_pairs: return
    target_archive.parent.mkdir(parents=True, exist_ok=True)
    file_pairs.sort(key=lambda x: natural_sort_key(x[1]))

    needs_wrapper = False
    if root_folder_name:
        top_dirs = set()
        has_root_files = False
        for _, arc_name in file_pairs:
            parts = Path(arc_name).parts
            if len(parts) > 1:
                top_dirs.add(parts[0])
            else:
                has_root_files = True
        if has_root_files or len(top_dirs) != 1 or next(iter(top_dirs)) != root_folder_name:
            needs_wrapper = True

    total = len(file_pairs)
    with zipfile.ZipFile(target_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
        for idx, (disk_path, arc_name) in enumerate(file_pairs):
            if abort_flag is not None and abort_flag.value:
                raise InterruptedError("ABORTED")
            final_arc_name = f"{root_folder_name}/{arc_name}" if needs_wrapper else arc_name
            zf.write(disk_path, arcname=final_arc_name)
            if consume_source:
                try:
                    Path(disk_path).unlink(missing_ok=True)
                except Exception:
                    pass
            if progress_callback and (idx % 15 == 0 or idx == total - 1):
                progress_callback((idx + 1) / max(1, total))

def safe_move_file(src_path: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / src_path.name
    counter = 1
    while dst_path.exists():
        dst_path = dst_dir / f"{src_path.stem}_{counter}{src_path.suffix}"
        counter += 1
    shutil.move(str(src_path), str(dst_path))

def get_dir_size_bytes(directory: Path) -> int:
    if not directory or not directory.exists(): return 0
    total = 0
    for p in directory.rglob("*"):
        if p.is_file() and not p.is_symlink():
            try: total += p.stat().st_size
            except Exception: pass
    return total

def format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3: return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2: return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024: return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"

def is_system_generated_path(path: Path, source_dir: Path) -> bool:
    try:
        rel_parts = path.relative_to(source_dir).parts
        for part in rel_parts[:-1]:
            if part.startswith(SYSTEM_DIR_PREFIXES):
                return True
    except Exception:
        pass
    return False

def _process_single_page_task(args):
    idx, img_path, rel_path, out_img_path, max_w, max_h, jpeg_quality = args
    try:
        resize_and_convert_image(img_path, out_img_path, max_w=max_w, max_h=max_h, jpeg_quality=jpeg_quality)
        # 邊轉邊刪：轉換成功寫入後，立刻刪除暫存原圖，避免 RAM Disk 空間倍增
        if out_img_path.exists() and out_img_path.stat().st_size > 0:
            try:
                img_path.unlink(missing_ok=True)
            except Exception:
                pass
        new_rel_path = str(Path(rel_path).with_suffix('.jpg'))
        return (out_img_path, new_rel_path)
    except OSError as e:
        try:
            out_img_path.unlink(missing_ok=True)
        except Exception:
            pass
        if e.errno == 28 or "No space left on device" in str(e):
            raise
        return (img_path, rel_path)
    except Exception:
        return (img_path, rel_path)

def execute_pipeline(
    archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
    temp_target_dir, tier_tag, worker_id, status_dict, cpu_token_manager,
    max_w: int = MAX_WIDTH, max_h: int = MAX_HEIGHT, jpeg_quality: int = JPEG_QUALITY,
    io_controller=None, abort_flag=None
):
    stem_name = archive_path.stem
    allocated_tokens, cpu_token_lock = cpu_token_manager

    def update_extract_progress(ratio: float, elapsed: float):
        status_dict[worker_id] = {
            "tier": tier_tag, "stage": "Extracting", "name": archive_path.name,
            "progress": ratio * 0.25, "detail": f"{elapsed:.1f}s ({int(ratio * 100)}%)"
        }

    with tempfile.TemporaryDirectory(dir=temp_target_dir) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        extracted_dir = temp_dir / "extracted"
        processed_dir_tmp = temp_dir / "processed"
        staged_out_dir = temp_dir / "staged_out"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        processed_dir_tmp.mkdir(parents=True, exist_ok=True)
        staged_out_dir.mkdir(parents=True, exist_ok=True)

        # 階段 1: 透過 Disk I/O 閘門控制併發解壓縮讀取（若有已完成待寫出的任務則優先禮讓）
        if io_controller is not None:
            active_io_streams, waiting_writers, io_lock, max_io_streams = io_controller
            status_dict[worker_id] = {
                "tier": tier_tag, "stage": "Queued I/O", "name": archive_path.name,
                "progress": 0.0, "detail": "Waiting Disk"
            }
            acquired_read = False
            try:
                while True:
                    if abort_flag is not None and abort_flag.value:
                        return False, "ABORTED", 0, 0
                    with io_lock:
                        if active_io_streams.value < max_io_streams and waiting_writers.value == 0:
                            active_io_streams.value += 1
                            acquired_read = True
                            break
                    time.sleep(0.04)
                success, reason = extract_archive_stream(
                    archive_path, extracted_dir, update_extract_progress, abort_flag=abort_flag
                )
            finally:
                if acquired_read:
                    with io_lock:
                        active_io_streams.value = max(0, active_io_streams.value - 1)
        else:
            success, reason = extract_archive_stream(
                archive_path, extracted_dir, update_extract_progress, abort_flag=abort_flag
            )

        if not success:
            return False, reason, 0, 0

        if abort_flag is not None and abort_flag.value:
            return False, "ABORTED", 0, 0

        status_dict[worker_id] = {
            "tier": tier_tag, "stage": "Scanning", "name": archive_path.name,
            "progress": 0.25, "detail": "Indexing"
        }
        static_images, animated_images, media_files = [], [], []

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
            return False, "NO_VALID_FILES", 0, 0

        total_imgs = len(static_images)
        processed_images = []
        tasks = [
            (idx, img_path, rel_path, processed_dir_tmp / f"img_{idx:05d}.jpg", max_w, max_h, jpeg_quality)
            for idx, (img_path, rel_path) in enumerate(static_images)
        ]

        CHUNK_SIZE = 24
        try:
            for chunk_start in range(0, total_imgs, CHUNK_SIZE):
                if abort_flag is not None and abort_flag.value:
                    return False, "ABORTED", 0, 0
                chunk_tasks = tasks[chunk_start:chunk_start + CHUNK_SIZE]

                borrowed_tokens = 0
                borrowed_idle_specs = []
                with cpu_token_lock:
                    # Idle 或正在排隊等硬碟 I/O (Queued I/O) 的核心皆不耗 CPU，可全數借出協助圖片縮放
                    idle_candidates = [
                        (wid, dict(info)) for wid, info in status_dict.items()
                        if wid != worker_id and info.get("stage", "") in ("Idle", "Queued I/O")
                    ]
                    available_tokens = max(0, len(idle_candidates) - allocated_tokens.value)
                    if available_tokens > 0:
                        desired = available_tokens
                        allocated_tokens.value += desired
                        borrowed_tokens = desired
                        borrowed_idle_specs = idle_candidates[:desired]

                for b_wid, prev_info in borrowed_idle_specs:
                    status_dict[b_wid] = {
                        "tier": "CPU", "stage": "Assisting", "name": f"Borrowed by C{worker_id+1:02d}",
                        "progress": 0.99, "detail": "Thread"
                    }

                current_concurrency = 1 + borrowed_tokens
                stage_desc = f"Resizing({current_concurrency}T)" if current_concurrency > 1 else "Resizing"

                try:
                    if current_concurrency > 1:
                        with ThreadPoolExecutor(max_workers=current_concurrency) as chunk_pool:
                            chunk_results = list(chunk_pool.map(_process_single_page_task, chunk_tasks))
                    else:
                        chunk_results = [_process_single_page_task(t) for t in chunk_tasks]
                    processed_images.extend(chunk_results)
                finally:
                    if borrowed_tokens > 0:
                        with cpu_token_lock:
                            allocated_tokens.value = max(0, allocated_tokens.value - borrowed_tokens)
                        for b_wid, prev_info in borrowed_idle_specs:
                            if status_dict.get(b_wid, {}).get("stage") == "Assisting":
                                status_dict[b_wid] = prev_info

                done_count = len(processed_images)
                pct = 0.25 + (0.65 * (done_count / max(1, total_imgs)))
                status_dict[worker_id] = {
                    "tier": tier_tag, "stage": stage_desc, "name": archive_path.name,
                    "progress": pct, "detail": f"{done_count}/{total_imgs}P"
                }
        except OSError as e:
            if e.errno == 28 or "No space left on device" in str(e):
                return False, "NO_SPACE", 0, 0
            raise

        if abort_flag is not None and abort_flag.value:
            return False, "ABORTED", 0, 0

        # 階段 3: 在 RAM Disk / Local Temp 內部瞬間封裝好 ZIP/CBZ，並「邊包邊刪」來源暫存檔以保持零重複空間佔用
        pkg_label = "RAM Build" if tier_tag == "RAM" else "Local Build"
        def update_pkg_progress(ratio: float):
            status_dict[worker_id] = {
                "tier": tier_tag, "stage": "Packaging", "name": archive_path.name,
                "progress": 0.90 + (0.06 * ratio), "detail": f"{pkg_label} ({int(ratio * 100)}%)"
            }

        update_pkg_progress(0.0)
        out_bytes = 0
        staged_moves = []
        try:
            if processed_images:
                staged_main = staged_out_dir / f"{stem_name}{ARCHIVE_MAIN_EXT}"
                create_zip_store(
                    staged_main, processed_images, consume_source=True,
                    abort_flag=abort_flag, progress_callback=update_pkg_progress
                )
                if staged_main.exists():
                    out_bytes += staged_main.stat().st_size
                    staged_moves.append((staged_main, resized_dir))
            if animated_images:
                staged_anim = staged_out_dir / f"{stem_name}-Animated{ARCHIVE_OTHER_EXT}"
                create_zip_store(
                    staged_anim, animated_images, root_folder_name=f"{stem_name}-Animated",
                    consume_source=True, abort_flag=abort_flag
                )
                if staged_anim.exists():
                    out_bytes += staged_anim.stat().st_size
                    staged_moves.append((staged_anim, anim_dir))
            if media_files:
                staged_media = staged_out_dir / f"{stem_name}-Media{ARCHIVE_OTHER_EXT}"
                create_zip_store(
                    staged_media, media_files, root_folder_name=f"{stem_name}-Media",
                    consume_source=True, abort_flag=abort_flag
                )
                if staged_media.exists():
                    out_bytes += staged_media.stat().st_size
                    staged_moves.append((staged_media, media_dir))
            shutil.rmtree(extracted_dir, ignore_errors=True)
            shutil.rmtree(processed_dir_tmp, ignore_errors=True)
        except InterruptedError:
            return False, "ABORTED", 0, 0
        except OSError as e:
            if e.errno == 28 or "No space left on device" in str(e):
                return False, "NO_SPACE", 0, 0
            raise

        if abort_flag is not None and abort_flag.value:
            return False, "ABORTED", 0, 0

        # 階段 4: 組裝完畢後透過最高優先權 (Write-Priority) 立刻搬往目的地資料夾，瞬間騰出 RAM Disk
        def _flush_to_disk():
            status_dict[worker_id] = {
                "tier": tier_tag, "stage": "Archiving", "name": archive_path.name,
                "progress": 0.98, "detail": "Seq Write"
            }
            for st_file, target_d in staged_moves:
                safe_move_file(st_file, target_d)
            safe_move_file(archive_path, original_files_dir)

        if io_controller is not None:
            active_io_streams, waiting_writers, io_lock, max_io_streams = io_controller
            with io_lock:
                waiting_writers.value += 1
            acquired_write = False
            try:
                status_dict[worker_id] = {
                    "tier": tier_tag, "stage": "Queued I/O", "name": archive_path.name,
                    "progress": 0.96, "detail": "Priority Flush"
                }
                while True:
                    if abort_flag is not None and abort_flag.value:
                        return False, "ABORTED", 0, 0
                    with io_lock:
                        if active_io_streams.value < max_io_streams:
                            active_io_streams.value += 1
                            waiting_writers.value = max(0, waiting_writers.value - 1)
                            acquired_write = True
                            break
                    time.sleep(0.03)
                _flush_to_disk()
            finally:
                with io_lock:
                    if acquired_write:
                        active_io_streams.value = max(0, active_io_streams.value - 1)
                    else:
                        waiting_writers.value = max(0, waiting_writers.value - 1)
        else:
            _flush_to_disk()

    return True, "SUCCESS", len(static_images), out_bytes

def worker_task(
    archive_path_str: str, target_tier: str, reserved_mb: float,
    resized_dir_str: str, anim_dir_str: str, media_dir_str: str,
    original_files_dir_str: str, error_dir_str: str, file_err_dir_str: str,
    worker_id: int, status_dict, recent_logs, ram_manager_tuple, cpu_token_manager,
    max_w: int = MAX_WIDTH, max_h: int = MAX_HEIGHT, jpeg_quality: int = JPEG_QUALITY,
    io_controller=None, strict_ram: bool = True, abort_flag=None
):
    archive_path = Path(archive_path_str)
    resized_dir = Path(resized_dir_str)
    anim_dir = Path(anim_dir_str)
    media_dir = Path(media_dir_str)
    original_files_dir = Path(original_files_dir_str)
    error_dir = Path(error_dir_str)
    file_err_dir = Path(file_err_dir_str)

    try:
        orig_bytes = archive_path.stat().st_size
    except Exception:
        orig_bytes = 0

    current_allocated_ram, ram_budget_mb, ram_lock = ram_manager_tuple
    tier_tag = "RAM" if target_tier == "RAM" else "SSD"
    temp_target_dir = str(RAM_DISK_MOUNT) if target_tier == "RAM" else None

    start_task_time = time.time()
    clean_name = sanitize_log_text(archive_path.name)
    try:
        if abort_flag is not None and abort_flag.value:
            status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ABORTED", 0.0, 0, orig_bytes, 0

        ok, reason, img_count, out_bytes = execute_pipeline(
            archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
            temp_target_dir, tier_tag, worker_id, status_dict, cpu_token_manager,
            max_w=max_w, max_h=max_h, jpeg_quality=jpeg_quality, io_controller=io_controller,
            abort_flag=abort_flag
        )

        if not ok and (reason == "ABORTED" or (abort_flag is not None and abort_flag.value)):
            status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ABORTED", time.time() - start_task_time, 0, orig_bytes, 0

        if not ok and reason == "NO_SPACE" and temp_target_dir is not None:
            if strict_ram:
                # 強制 RAM Disk 模式下絕不偷偷退回 SSD，先釋放暫存並排回佇列頂端等待 RAM Disk 空間
                recent_logs.append(("WARN", clean_name, "RAM Busy -> Wait RAM"))
                status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
                return archive_path_str, "RETRY_RAM", time.time() - start_task_time, 0, orig_bytes, 0
            else:
                recent_logs.append(("WARN", clean_name, "RAM limit -> SSD"))
                tier_tag = "SSD"
                ok, reason, img_count, out_bytes = execute_pipeline(
                    archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
                    None, tier_tag, worker_id, status_dict, cpu_token_manager,
                    max_w=max_w, max_h=max_h, jpeg_quality=jpeg_quality, io_controller=io_controller,
                    abort_flag=abort_flag
                )
                if not ok and (reason == "ABORTED" or (abort_flag is not None and abort_flag.value)):
                    status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
                    return archive_path_str, "ABORTED", time.time() - start_task_time, 0, orig_bytes, 0
                if not ok:
                    safe_move_file(archive_path, error_dir)
                    recent_logs.append(("SYS_ERR", clean_name, "Retry Failed"))
                    status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
                    return archive_path_str, "ERROR", time.time() - start_task_time, 0, orig_bytes, 0

        elif not ok and reason in ("CORRUPTED", "NO_VALID_FILES"):
            safe_move_file(archive_path, file_err_dir)
            recent_logs.append(("FILE_ERR", clean_name, "Corrupted File"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "FILE_ERR", time.time() - start_task_time, 0, orig_bytes, 0

        elif not ok:
            safe_move_file(archive_path, error_dir)
            recent_logs.append(("SYS_ERR", clean_name, "Execution Error"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ERROR", time.time() - start_task_time, 0, orig_bytes, 0
    finally:
        if target_tier == "RAM" and reserved_mb > 0:
            with ram_lock:
                current_allocated_ram.value = max(0.0, current_allocated_ram.value - reserved_mb)

    total_cost = time.time() - start_task_time
    recent_logs.append(("OK", clean_name, f"{total_cost:.1f}s, {img_count}P"))
    status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
    return archive_path_str, "SUCCESS", total_cost, img_count, orig_bytes, out_bytes

def pack_folder_worker(
    folder_path_str: str, out_ext: str, worker_id: int,
    status_dict, recent_logs, move_to_orig_dir_str: str = None, abort_flag=None
):
    if abort_flag is not None and abort_flag.value:
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return folder_path_str, "ABORTED"

    folder_path = Path(folder_path_str)
    target_archive = folder_path.parent / f"{folder_path.name}{out_ext}"
    temp_archive = folder_path.parent / f".packing_{folder_path.name}{out_ext}.tmp"
    start_time = time.time()

    clean_name = sanitize_log_text(folder_path.name)
    status_dict[worker_id] = {
        "tier": "DISK", "stage": "Packing", "name": clean_name,
        "progress": 0.05, "detail": "Listing"
    }

    file_pairs = []
    for root, _, files in os.walk(folder_path):
        if abort_flag is not None and abort_flag.value:
            status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return folder_path_str, "ABORTED"
        for f in files:
            if f.startswith("._") or f == ".DS_Store":
                continue
            fp = Path(root) / f
            rel = fp.relative_to(folder_path)
            file_pairs.append((fp, str(rel)))

    if not file_pairs:
        recent_logs.append(("SKIP", clean_name, "Empty Directory"))
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return folder_path_str, "SKIP"

    total_files = len(file_pairs)
    file_pairs.sort(key=lambda x: natural_sort_key(x[1]))

    try:
        with zipfile.ZipFile(temp_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
            for idx, (fp, arc_name) in enumerate(file_pairs):
                if abort_flag is not None and abort_flag.value:
                    raise InterruptedError("ABORTED")
                zf.write(fp, arcname=arc_name)
                if idx % 10 == 0 or idx == total_files - 1:
                    pct = 0.10 + (0.85 * ((idx + 1) / max(1, total_files)))
                    status_dict[worker_id] = {
                        "tier": "DISK", "stage": "Storing", "name": clean_name,
                        "progress": pct, "detail": f"{idx + 1}/{total_files}F"
                    }
    except BaseException:
        try:
            temp_archive.unlink(missing_ok=True)
        except Exception:
            pass
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return folder_path_str, "ABORTED"

    if abort_flag is not None and abort_flag.value:
        try:
            temp_archive.unlink(missing_ok=True)
        except Exception:
            pass
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return folder_path_str, "ABORTED"

    temp_archive.replace(target_archive)

    if move_to_orig_dir_str:
        orig_dest = Path(move_to_orig_dir_str)
        safe_move_file(folder_path, orig_dest)

    cost = time.time() - start_time
    recent_logs.append(("OK", clean_name, f"Packed ({cost:.1f}s, {total_files}F)"))
    status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
    return folder_path_str, "SUCCESS"

def unpack_archive_worker(
    archive_path_str: str, unzipped_root_str: str, worker_id: int,
    status_dict, recent_logs, move_to_orig_dir_str: str = None,
    file_err_dir_str: str = None, smart_flatten: bool = True, abort_flag=None
):
    if abort_flag is not None and abort_flag.value:
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return archive_path_str, "ABORTED"

    archive_path = Path(archive_path_str)
    unzipped_root = Path(unzipped_root_str)
    unzipped_root.mkdir(parents=True, exist_ok=True)
    temp_extract_dir = unzipped_root / f".unpacking_{archive_path.stem}_{worker_id}.tmp"
    if temp_extract_dir.exists():
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    clean_name = sanitize_log_text(archive_path.name)

    def update_unpack_progress(ratio: float, elapsed: float):
        status_dict[worker_id] = {
            "tier": "DISK", "stage": "Extracting", "name": clean_name,
            "progress": ratio * 0.92, "detail": f"{elapsed:.1f}s ({int(ratio * 100)}%)"
        }

    try:
        success, reason = extract_archive_stream(
            archive_path, temp_extract_dir, progress_callback=update_unpack_progress, abort_flag=abort_flag
        )
    except BaseException:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return archive_path_str, "ABORTED"

    if not success or (abort_flag is not None and abort_flag.value):
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        if reason == "ABORTED" or (abort_flag is not None and abort_flag.value):
            return archive_path_str, "ABORTED"
        if reason == "CORRUPTED" and file_err_dir_str:
            safe_move_file(archive_path, Path(file_err_dir_str))
            recent_logs.append(("FILE_ERR", clean_name, "Corrupted Archive"))
            return archive_path_str, "FILE_ERR"
        recent_logs.append(("SYS_ERR", clean_name, f"Extract Failed ({reason})"))
        return archive_path_str, "ERROR"

    # 清除 macOS 垃圾目錄與隱藏檔 (__MACOSX, .DS_Store, ._*)
    file_count = 0
    for root, dirs, files in os.walk(temp_extract_dir, topdown=False):
        root_p = Path(root)
        for f in files:
            fp = root_p / f
            if f == ".DS_Store" or f.startswith("._"):
                try:
                    fp.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                file_count += 1
        for d in dirs:
            dp = root_p / d
            if d == "__MACOSX":
                shutil.rmtree(dp, ignore_errors=True)

    if file_count == 0:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        recent_logs.append(("SKIP", clean_name, "Empty Archive"))
        status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
        return archive_path_str, "SKIP"

    # 智慧單層目錄標準化 (Smart Flatten)：若解壓後內層只有唯一一個資料夾且無散落檔案，自動消除多餘的套娃層級
    source_to_move = temp_extract_dir
    if smart_flatten:
        while True:
            entries = [e for e in source_to_move.iterdir() if not e.name.startswith(".")]
            if len(entries) == 1 and entries[0].is_dir():
                source_to_move = entries[0]
            else:
                break

    final_dir = unzipped_root / archive_path.stem
    counter = 1
    while final_dir.exists():
        final_dir = unzipped_root / f"{archive_path.stem}_{counter}"
        counter += 1

    try:
        shutil.move(str(source_to_move), str(final_dir))
    finally:
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

    if move_to_orig_dir_str:
        safe_move_file(archive_path, Path(move_to_orig_dir_str))

    cost = time.time() - start_time
    recent_logs.append(("OK", clean_name, f"Unpacked ({cost:.1f}s, {file_count}F)"))
    status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
    return archive_path_str, "SUCCESS"

def terminate_executor_immediately(executor: ProcessPoolExecutor, futures_iterable=()):
    """立即取消未執行任務並強制終止所有 Worker 行程及其衍生子行程 (如 7zz)，不阻塞等待"""
    for f in list(futures_iterable):
        try:
            f.cancel()
        except Exception:
            pass
    procs = []
    if hasattr(executor, "_processes") and executor._processes:
        procs = list(executor._processes.values())
    for p in procs:
        try:
            if p.pid:
                subprocess.run(["pkill", "-9", "-P", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.terminate()
        except Exception:
            pass
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    for p in procs:
        try:
            if p.is_alive():
                p.kill()
        except Exception:
            pass

# ==================== Background Threads ====================
class OptimizerThread(QThread):
    progress_signal = pyqtSignal(int, int)
    worker_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(list)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(
        self, source_dirs_list: list, global_output_dir_str: str,
        ram_gb: int, strict_ram: bool,
        max_w: int = MAX_WIDTH, max_h: int = MAX_HEIGHT, jpeg_quality: int = JPEG_QUALITY,
        io_limit: int = 3
    ):
        super().__init__()
        self.source_dirs = [Path(d) for d in source_dirs_list]
        self.global_output_dir = Path(global_output_dir_str) if global_output_dir_str else None
        self.ram_gb = ram_gb
        self.strict_ram = strict_ram
        self.max_w = max_w
        self.max_h = max_h
        self.jpeg_quality = jpeg_quality
        self.io_limit = max(1, io_limit)
        self.is_aborted = False
        self.abort_flag = None

    def abort(self):
        self.is_aborted = True
        if self.abort_flag is not None:
            try:
                self.abort_flag.value = True
            except Exception:
                pass

    def _cleanup_leftover_tmp_packs(self):
        for s_dir in self.source_dirs:
            try:
                for p in s_dir.glob(".packing_*.tmp"):
                    p.unlink(missing_ok=True)
            except Exception:
                pass

    def run(self):
        global_start_time = time.time()
        today_str = datetime.now().strftime("%Y-%m-%d")
        num_workers = max(1, os.cpu_count() - 1)
        manager = multiprocessing.Manager()
        self.abort_flag = manager.Value('b', self.is_aborted)
        worker_statuses = manager.dict()
        recent_logs = manager.list()
        file_err_stems = manager.list()
        for i in range(num_workers):
            worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}

        out_loc_desc = str(self.global_output_dir) if self.global_output_dir else "Respective source folders"

        def _emit_early_abort(total_f=0):
            self._cleanup_leftover_tmp_packs()
            for i in range(num_workers):
                worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            self.worker_signal.emit(dict(worker_statuses))
            self.log_signal.emit(list(recent_logs))
            self.finished_signal.emit({
                "mode": "optimizer",
                "total_time": time.time() - global_start_time,
                "total_files": total_f,
                "success": 0,
                "corrupted": 0,
                "error": 0,
                "aborted": True,
                "out_loc": out_loc_desc,
                "source_count": len(self.source_dirs),
                "orig_bytes": 0,
                "out_bytes": 0
            })

        # === 步驟 1: 對所有來源資料夾分別執行前置 Quick Folder Packer ===
        all_pre_sub_dirs = []
        for s_dir in self.source_dirs:
            orig_dest = s_dir / f"OriginalFiles-{today_str}"
            try:
                for item in s_dir.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        if not item.name.startswith(SYSTEM_DIR_PREFIXES):
                            all_pre_sub_dirs.append((item, orig_dest))
            except Exception:
                pass

        if all_pre_sub_dirs and not self.is_aborted:
            recent_logs.append(("INFO", "Pre-pack", f"Found {len(all_pre_sub_dirs)} subfolders across {len(self.source_dirs)} sources"))
            self.log_signal.emit(list(recent_logs))
            pre_queue = list(all_pre_sub_dirs)
            pre_avail_workers = set(range(min(num_workers, self.io_limit)))
            pack_futures = {}
            pre_done = 0
            pack_executor = ProcessPoolExecutor(max_workers=min(num_workers, self.io_limit))
            try:
                while (pre_queue or pack_futures) and not self.is_aborted:
                    done_pf = [f for f in pack_futures if f.done()]
                    for f in done_pf:
                        wid = pack_futures.pop(f)
                        pre_avail_workers.add(wid)
                        pre_done += 1
                        self.progress_signal.emit(pre_done, len(all_pre_sub_dirs))

                    while pre_avail_workers and pre_queue and not self.is_aborted:
                        folder, orig_dest = pre_queue.pop(0)
                        wid = pre_avail_workers.pop()
                        f = pack_executor.submit(
                            pack_folder_worker, str(folder), ".zip", wid,
                            worker_statuses, recent_logs, str(orig_dest), self.abort_flag
                        )
                        pack_futures[f] = wid

                    self.worker_signal.emit(dict(worker_statuses))
                    self.log_signal.emit(list(recent_logs))
                    time.sleep(0.1)
            finally:
                if self.is_aborted:
                    terminate_executor_immediately(pack_executor, pack_futures.keys())
                else:
                    pack_executor.shutdown(wait=True)

        if self.is_aborted:
            _emit_early_abort(0)
            return

        # === 步驟 2: 掃描所有來源資料夾底下的待處理壓縮檔 ===
        archive_items = []
        for s_dir in self.source_dirs:
            for p in s_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in ARCHIVE_EXTENSIONS:
                    if not p.name.startswith("._") and not is_system_generated_path(p, s_dir):
                        archive_items.append({"path": p, "src_root": s_dir})

        if not archive_items:
            self.error_signal.emit("No supported comic archives found in any of the specified source folders.")
            return

        ram_active = False
        if self.ram_gb > 0:
            ram_path = setup_ram_disk(self.ram_gb)
            ram_active = ram_path is not None

        ram_budget_mb = (self.ram_gb * 1024 * 0.96) if ram_active else 0.0
        ram_total_mb = (self.ram_gb * 1024.0) if ram_active else 0.0
        current_allocated_ram = manager.Value('d', 0.0)
        ram_lock = manager.Lock()
        ram_manager_tuple = (current_allocated_ram, ram_budget_mb, ram_lock)

        allocated_cpu_tokens = manager.Value('i', 0)
        cpu_token_lock = manager.Lock()
        cpu_token_manager = (allocated_cpu_tokens, cpu_token_lock)

        active_io_streams = manager.Value('i', 0)
        waiting_writers = manager.Value('i', 0)
        io_lock = manager.Lock()
        io_controller = (active_io_streams, waiting_writers, io_lock, self.io_limit)

        pending_queue = []
        max_inspect_threads = min(32, (os.cpu_count() or 4) * 4)
        with ThreadPoolExecutor(max_workers=max_inspect_threads) as inspector:
            futures = [inspector.submit(inspect_archive_worker, item) for item in archive_items]
            for f in as_completed(futures):
                if self.is_aborted:
                    for pending_f in futures:
                        pending_f.cancel()
                    break
                try: pending_queue.append(f.result())
                except Exception: pass

        if self.is_aborted:
            if ram_active: cleanup_ram_disk()
            _emit_early_abort(len(archive_items))
            return

        pending_queue.sort(key=lambda x: x["uncompressed_mb"], reverse=True)

        success_count = 0
        fail_err_count = 0
        corrupted_count = 0
        done_total = 0
        session_orig_bytes = 0
        session_out_bytes = 0

        available_workers = set(range(num_workers))
        active_futures = {}
        executor = ProcessPoolExecutor(max_workers=num_workers)

        try:
            while (pending_queue or active_futures) and not self.is_aborted:
                done_futures = [f for f in active_futures if f.done()]
                for f in done_futures:
                    task_meta = active_futures.pop(f)
                    worker_id = task_meta["wid"]
                    src_root_str = task_meta["src_root"]
                    dest_root_str = task_meta["dest_root"]
                    orig_item = task_meta["item"]
                    available_workers.add(worker_id)
                    try:
                        arch_path_done, result_code, cost_sec, page_cnt, f_orig_b, f_out_b = f.result()
                        if result_code == "ABORTED":
                            continue
                        if result_code == "RETRY_RAM":
                            # 強制 RAM Disk 模式下若發生空間不足，調高該檔預留額度並排回佇列最前端重新在 RAM Disk 執行
                            orig_item["ram_oom_retries"] = orig_item.get("ram_oom_retries", 0) + 1
                            if orig_item["ram_oom_retries"] >= 3:
                                orig_item["force_ssd"] = True
                                recent_logs.append(("WARN", sanitize_log_text(orig_item["path"].name), "Exceeds Total RAM -> SSD"))
                            else:
                                orig_item["uncompressed_mb"] = min(
                                    ram_budget_mb,
                                    max(orig_item["uncompressed_mb"] * 1.25, ram_budget_mb * 0.5)
                                )
                            pending_queue.insert(0, orig_item)
                            continue

                        done_total += 1
                        arch_name = Path(arch_path_done).name
                        if result_code == "SUCCESS":
                            success_count += 1
                            session_orig_bytes += f_orig_b
                            session_out_bytes += f_out_b
                        elif result_code == "FILE_ERR":
                            corrupted_count += 1
                            file_err_stems.append(Path(arch_path_done).stem)
                        else:
                            fail_err_count += 1

                        HistoryDatabase.add_record(
                            filename=arch_name,
                            source_dir=src_root_str,
                            output_dir=dest_root_str,
                            status=result_code,
                            page_count=page_cnt,
                            orig_bytes=f_orig_b,
                            out_bytes=f_out_b,
                            duration_sec=cost_sec
                        )
                    except Exception:
                        if not self.is_aborted:
                            done_total += 1
                            fail_err_count += 1
                    self.progress_signal.emit(done_total, len(archive_items))

                while available_workers and pending_queue and not self.is_aborted:
                    # 按需串流派發 (Just-In-Time Stream Dispatch)：
                    # 當有任務正在寫出釋放 RAM Disk，或正在讀取解壓的串流數已達 io_limit 時，
                    # 不提前把多餘任務塞進 Waiting Disk 預佔 RAM Disk 空間，讓閒置核心專心支援 Resizing！
                    if waiting_writers.value > 0:
                        break
                    active_wids = [m["wid"] for m in active_futures.values()]
                    active_readers = sum(
                        1 for wid in active_wids
                        if worker_statuses.get(wid, {}).get("stage") in ("Queued I/O", "Extracting")
                        and worker_statuses.get(wid, {}).get("progress", 0.0) < 0.25
                    )
                    if active_readers >= self.io_limit:
                        break

                    assigned = False
                    for idx, item in enumerate(pending_queue):
                        needed_mb = item["uncompressed_mb"]
                        exceeds_physical_ram = (needed_mb > ram_total_mb) if self.strict_ram else (needed_mb > ram_budget_mb)
                        if not ram_active or item.get("force_ssd", False) or exceeds_physical_ram:
                            target_tier = "SSD"
                            reserved_mb = 0.0
                            chosen_item = pending_queue.pop(idx)
                            assigned = True
                            break

                        effective_needed_mb = min(needed_mb, ram_budget_mb)
                        can_allocate = False
                        with ram_lock:
                            actual_free_mb = get_ram_disk_free_mb()
                            if current_allocated_ram.value <= 0.01:
                                # 當 RAM Disk 處於淨空狀態時，任何小於 RAM Disk 總容量的檔案皆可直接進駐
                                if actual_free_mb >= min(effective_needed_mb * 0.90, ram_budget_mb * 0.90):
                                    current_allocated_ram.value += effective_needed_mb
                                    can_allocate = True
                            else:
                                # 雙重空間檢核：帳面預留與實體剩餘空間皆足夠才放行
                                if (current_allocated_ram.value + effective_needed_mb <= ram_budget_mb) and (actual_free_mb >= effective_needed_mb):
                                    current_allocated_ram.value += effective_needed_mb
                                    can_allocate = True

                        if can_allocate:
                            target_tier = "RAM"
                            reserved_mb = effective_needed_mb
                            chosen_item = pending_queue.pop(idx)
                            assigned = True
                            break
                        else:
                            if self.strict_ram:
                                continue
                            else:
                                if idx == 0:
                                    item["retries"] += 1
                                if item["retries"] >= MAX_RAM_RETRIES:
                                    target_tier = "SSD"
                                    reserved_mb = 0.0
                                    chosen_item = pending_queue.pop(idx)
                                    assigned = True
                                    break

                    if assigned:
                        worker_id = available_workers.pop()
                        # 立即標記為 Queued I/O，確保迴圈能精確統計 active_readers
                        worker_statuses[worker_id] = {
                            "tier": target_tier, "stage": "Queued I/O",
                            "name": chosen_item["path"].name, "progress": 0.0, "detail": "Starting"
                        }
                        # 動態計算該檔案的產出目錄
                        src_root = chosen_item["src_root"]
                        dest_root = self.global_output_dir if self.global_output_dir else src_root
                        
                        resized_dir = dest_root / f"Resized-{today_str}"
                        anim_dir = dest_root / f"Animated-{today_str}"
                        media_dir = dest_root / f"Media-{today_str}"
                        error_dir = dest_root / f"Error-{today_str}"
                        file_err_dir = dest_root / f"FileErr-{today_str}"
                        # 原檔固定搬移到原本所屬資料夾
                        original_files_dir = src_root / f"OriginalFiles-{today_str}"

                        f = executor.submit(
                            worker_task, str(chosen_item["path"]), target_tier, reserved_mb,
                            str(resized_dir), str(anim_dir), str(media_dir),
                            str(original_files_dir), str(error_dir), str(file_err_dir),
                            worker_id, worker_statuses, recent_logs, ram_manager_tuple, cpu_token_manager,
                            self.max_w, self.max_h, self.jpeg_quality, io_controller, self.strict_ram,
                            self.abort_flag
                        )
                        active_futures[f] = {
                            "wid": worker_id,
                            "src_root": str(src_root),
                            "dest_root": str(dest_root),
                            "item": chosen_item
                        }
                    else:
                        break

                self.worker_signal.emit(dict(worker_statuses))
                self.log_signal.emit(list(recent_logs))
                time.sleep(0.1)
        finally:
            if self.is_aborted:
                terminate_executor_immediately(executor, active_futures.keys())
            else:
                executor.shutdown(wait=True)
            for i in range(num_workers):
                worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            self.worker_signal.emit(dict(worker_statuses))
            self.log_signal.emit(list(recent_logs))
            if ram_active:
                cleanup_ram_disk()

        total_cost = time.time() - global_start_time

        # 彙整產出損毀檔案 HTML 與清單
        report_dest_dir = self.global_output_dir if self.global_output_dir else self.source_dirs[0]
        file_err_dest = report_dest_dir / f"FileErr-{today_str}"

        if corrupted_count > 0 or (file_err_dest.exists() and (file_err_dest / "corrupted_list.txt").exists()):
            file_err_dest.mkdir(parents=True, exist_ok=True)
            list_file = file_err_dest / "corrupted_list.txt"
            html_file = file_err_dest / "corrupted_search.html"
            try:
                existing_stems = set()
                if list_file.exists():
                    for line in list_file.read_text(encoding="utf-8").splitlines():
                        if line.strip(): existing_stems.add(line.strip())
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
            except Exception:
                pass

        # 空間統計計算 (以本次執行實際處理的檔案大小為準)
        total_orig_bytes = session_orig_bytes
        total_out_bytes = session_out_bytes

        summary_payload = {
            "mode": "optimizer",
            "total_time": total_cost,
            "total_files": len(archive_items),
            "success": success_count,
            "corrupted": corrupted_count,
            "error": fail_err_count,
            "aborted": self.is_aborted,
            "out_loc": out_loc_desc,
            "source_count": len(self.source_dirs),
            "orig_bytes": total_orig_bytes,
            "out_bytes": total_out_bytes
        }
        self.finished_signal.emit(summary_payload)

class FolderPackerThread(QThread):
    progress_signal = pyqtSignal(int, int)
    worker_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(list)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, source_dir_str: str, out_ext: str, move_orig: bool = False, io_limit: int = 3):
        super().__init__()
        self.source_dir = Path(source_dir_str)
        self.out_ext = out_ext
        self.move_orig = move_orig
        self.io_limit = max(1, io_limit)
        self.is_aborted = False
        self.abort_flag = None

    def abort(self):
        self.is_aborted = True
        if self.abort_flag is not None:
            try:
                self.abort_flag.value = True
            except Exception:
                pass

    def _cleanup_leftover_tmp_packs(self):
        try:
            for p in self.source_dir.glob(".packing_*.tmp"):
                p.unlink(missing_ok=True)
        except Exception:
            pass

    def run(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        sub_dirs = []
        try:
            for item in self.source_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    if not item.name.startswith(SYSTEM_DIR_PREFIXES):
                        sub_dirs.append(item)
        except Exception as e:
            self.error_signal.emit(f"Failed to access directory: {e}")
            return

        if not sub_dirs:
            self.error_signal.emit("No valid first-level subfolders found to pack.")
            return

        sub_dirs.sort(key=lambda x: natural_sort_key(x.name))
        num_workers = max(1, os.cpu_count() - 1)
        effective_workers = min(num_workers, self.io_limit)

        manager = multiprocessing.Manager()
        self.abort_flag = manager.Value('b', self.is_aborted)
        worker_statuses = manager.dict()
        recent_logs = manager.list()
        for i in range(num_workers):
            worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}

        global_start_time = time.time()
        success_count = 0
        skip_count = 0
        done_total = 0

        orig_dest_str = str(self.source_dir / f"OriginalFiles-{today_str}") if self.move_orig else None
        pending_queue = list(sub_dirs)
        available_workers = set(range(effective_workers))
        active_futures = {}
        executor = ProcessPoolExecutor(max_workers=effective_workers)

        try:
            while (pending_queue or active_futures) and not self.is_aborted:
                done_futures = [f for f in active_futures if f.done()]
                for f in done_futures:
                    worker_id = active_futures.pop(f)
                    available_workers.add(worker_id)
                    try:
                        _, code = f.result()
                        if code == "ABORTED":
                            continue
                        done_total += 1
                        if code == "SUCCESS": success_count += 1
                        else: skip_count += 1
                    except Exception:
                        if not self.is_aborted:
                            done_total += 1
                            skip_count += 1
                    self.progress_signal.emit(done_total, len(sub_dirs))

                while available_workers and pending_queue and not self.is_aborted:
                    chosen_folder = pending_queue.pop(0)
                    worker_id = available_workers.pop()
                    f = executor.submit(
                        pack_folder_worker, str(chosen_folder), self.out_ext,
                        worker_id, worker_statuses, recent_logs, orig_dest_str, self.abort_flag
                    )
                    active_futures[f] = worker_id

                self.worker_signal.emit(dict(worker_statuses))
                self.log_signal.emit(list(recent_logs))
                time.sleep(0.1)
        finally:
            if self.is_aborted:
                terminate_executor_immediately(executor, active_futures.keys())
                self._cleanup_leftover_tmp_packs()
            else:
                executor.shutdown(wait=True)
            for i in range(num_workers):
                worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            self.worker_signal.emit(dict(worker_statuses))
            self.log_signal.emit(list(recent_logs))

        total_cost = time.time() - global_start_time
        summary_payload = {
            "mode": "packer",
            "total_time": total_cost,
            "total_dirs": len(sub_dirs),
            "success": success_count,
            "skipped": skip_count,
            "aborted": self.is_aborted,
            "target_dir": str(self.source_dir)
        }
        self.finished_signal.emit(summary_payload)

class ArchiveUnpackerThread(QThread):
    progress_signal = pyqtSignal(int, int)
    worker_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(list)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(
        self, source_dir_str: str, smart_flatten: bool = True,
        move_orig: bool = True, io_limit: int = 3
    ):
        super().__init__()
        self.source_dir = Path(source_dir_str)
        self.smart_flatten = smart_flatten
        self.move_orig = move_orig
        self.io_limit = max(1, io_limit)
        self.is_aborted = False
        self.abort_flag = None

    def abort(self):
        self.is_aborted = True
        if self.abort_flag is not None:
            try:
                self.abort_flag.value = True
            except Exception:
                pass

    def _cleanup_leftover_tmp_unpacks(self, unzipped_root: Path):
        if not unzipped_root.exists():
            return
        try:
            for p in unzipped_root.glob(".unpacking_*.tmp"):
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    def run(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        unzipped_root = self.source_dir / f"Unzipped-{today_str}"
        orig_dest_str = str(self.source_dir / f"OriginalFiles-{today_str}") if self.move_orig else None
        file_err_str = str(self.source_dir / f"FileErr-{today_str}")

        archives = []
        try:
            for item in self.source_dir.iterdir():
                if item.is_file() and not item.name.startswith("."):
                    if item.suffix.lower() in ARCHIVE_EXTENSIONS:
                        archives.append(item)
        except Exception as e:
            self.error_signal.emit(f"Failed to access directory: {e}")
            return

        if not archives:
            self.error_signal.emit("No supported archives (.zip, .cbz, .rar, .cbr, .7z) found in the target directory.")
            return

        archives.sort(key=lambda x: natural_sort_key(x.name))
        num_workers = max(1, os.cpu_count() - 1)
        effective_workers = min(num_workers, self.io_limit)

        manager = multiprocessing.Manager()
        self.abort_flag = manager.Value('b', self.is_aborted)
        worker_statuses = manager.dict()
        recent_logs = manager.list()
        for i in range(num_workers):
            worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}

        global_start_time = time.time()
        success_count = 0
        corrupted_count = 0
        skip_count = 0
        error_count = 0
        done_total = 0

        pending_queue = list(archives)
        available_workers = set(range(effective_workers))
        active_futures = {}
        executor = ProcessPoolExecutor(max_workers=effective_workers)

        try:
            while (pending_queue or active_futures) and not self.is_aborted:
                done_futures = [f for f in active_futures if f.done()]
                for f in done_futures:
                    worker_id = active_futures.pop(f)
                    available_workers.add(worker_id)
                    try:
                        _, code = f.result()
                        if code == "ABORTED":
                            continue
                        done_total += 1
                        if code == "SUCCESS":
                            success_count += 1
                        elif code == "FILE_ERR":
                            corrupted_count += 1
                        elif code == "SYS_ERR":
                            error_count += 1
                        else:
                            skip_count += 1
                    except Exception:
                        if not self.is_aborted:
                            done_total += 1
                            error_count += 1
                    self.progress_signal.emit(done_total, len(archives))

                while available_workers and pending_queue and not self.is_aborted:
                    chosen_arch = pending_queue.pop(0)
                    worker_id = available_workers.pop()
                    f = executor.submit(
                        unpack_archive_worker, str(chosen_arch), str(unzipped_root),
                        worker_id, worker_statuses, recent_logs,
                        orig_dest_str, file_err_str, self.smart_flatten, self.abort_flag
                    )
                    active_futures[f] = worker_id

                self.worker_signal.emit(dict(worker_statuses))
                self.log_signal.emit(list(recent_logs))
                time.sleep(0.1)
        finally:
            if self.is_aborted:
                terminate_executor_immediately(executor, active_futures.keys())
                self._cleanup_leftover_tmp_unpacks(unzipped_root)
            else:
                executor.shutdown(wait=True)
            for i in range(num_workers):
                worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            self.worker_signal.emit(dict(worker_statuses))
            self.log_signal.emit(list(recent_logs))

        total_cost = time.time() - global_start_time
        summary_payload = {
            "mode": "unpacker",
            "total_time": total_cost,
            "total_files": len(archives),
            "success": success_count,
            "corrupted": corrupted_count,
            "skipped": skip_count,
            "error": error_count,
            "aborted": self.is_aborted,
            "unzipped_dir": str(unzipped_root),
            "target_dir": str(unzipped_root),
        }
        self.finished_signal.emit(summary_payload)

# ==================== Main Window GUI ====================
class DropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.setStyleSheet("QLineEdit { border: 1.5px solid #38bdf8; background-color: #131c31; }")
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("")
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                self.setText(local_path)
                break

class DropListWidget(QListWidget):
    """支援直接拖曳多個資料夾加入清單並具備空白引導與高亮的自訂 ListWidget"""
    items_changed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._dragging = False

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self._dragging = True
            self.setStyleSheet("QListWidget { border: 2px dashed #38bdf8; background-color: #131c31; }")
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._dragging = False
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._dragging = False
        self.setStyleSheet("")
        added = False
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                existing = [self.item(i).text() for i in range(self.count())]
                if local_path not in existing:
                    self.addItem(local_path)
                    added = True
        if added:
            self.items_changed_signal.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor("#38bdf8") if self._dragging else QColor("#64748b")
            painter.setPen(color)
            font = painter.font()
            font.setPointSize(13)
            font.setBold(self._dragging)
            painter.setFont(font)
            hint_text = "📂  Drag & Drop Comic Folders Here\nor click 'Add Folder...' on the right (Double-click item to open in Finder)"
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, hint_text)
            painter.end()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Comic Optimizer & Fast Packer (macOS)")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(1340, 900)
        self.setAcceptDrops(True)
        self.setStyleSheet(MODERN_DARK_STYLESHEET)
        self.worker_thread = None
        self.batch_start_time = None
        self.num_workers = max(1, os.cpu_count() - 1)
        HistoryDatabase.init_db()
        self.init_ui()
        self.load_user_settings()
        self.refresh_history_view()
        self.update_monitor_visibility()

    def closeEvent(self, event: QCloseEvent):
        self.save_user_settings()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.abort()
            self.worker_thread.wait(2500)
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                if self.tabs.currentIndex() == 0:
                    self.add_source_folder(local_path)
                elif self.tabs.currentIndex() == 1:
                    self.path_input_pack.setText(local_path)
                    self.save_user_settings()

    def add_source_folder(self, path_str: str):
        existing = [self.sources_list.item(i).text() for i in range(self.sources_list.count())]
        if path_str not in existing:
            self.sources_list.addItem(path_str)
        self.update_sources_count_label()
        self.save_user_settings()

    def on_sources_list_dropped(self):
        self.update_sources_count_label()
        self.save_user_settings()

    def update_sources_count_label(self):
        cnt = self.sources_list.count()
        self.sources_count_label.setText(f"Sources Selected: {cnt}")
        self.sources_list.viewport().update()

    @staticmethod
    def _create_kpi_card(title_text: str, value_text: str, sub_text: str, accent_color: str):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #0f172a;
                border: 1px solid #334155;
                border-left: 4px solid {accent_color};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)

        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700; border: none;")

        val_lbl = QLabel(value_text)
        val_lbl.setStyleSheet(f"color: {accent_color}; font-size: 20px; font-weight: 800; border: none;")

        sub_lbl = QLabel(sub_text)
        sub_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600; border: none;")

        lay.addWidget(title_lbl)
        lay.addWidget(val_lbl)
        lay.addWidget(sub_lbl)
        return card, val_lbl, sub_lbl

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 14, 14, 14)

        self.tabs = QTabWidget()

        # ---- Tab 1: Comic Optimizer (Multi-source) ----
        tab_opt = QWidget()
        layout_opt = QVBoxLayout(tab_opt)
        layout_opt.setContentsMargins(12, 12, 12, 12)
        layout_opt.setSpacing(10)

        # 複數來源清單區
        src_box = QHBoxLayout()
        self.sources_list = DropListWidget()
        self.sources_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sources_list.setMinimumHeight(105)
        self.sources_list.items_changed_signal.connect(self.on_sources_list_dropped)
        self.sources_list.itemDoubleClicked.connect(lambda item: reveal_in_finder(Path(item.text())))

        src_btn_layout = QVBoxLayout()
        src_btn_layout.setSpacing(6)
        add_src_btn = QPushButton("+ Add Folder...")
        add_src_btn.clicked.connect(self.browse_add_source)
        remove_src_btn = QPushButton("Remove Selected")
        remove_src_btn.clicked.connect(self.remove_selected_source)
        clear_src_btn = QPushButton("Clear All")
        clear_src_btn.clicked.connect(self.clear_all_sources)
        self.sources_count_label = QLabel("Sources Selected: 0")
        self.sources_count_label.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 12px;")

        src_btn_layout.addWidget(add_src_btn)
        src_btn_layout.addWidget(remove_src_btn)
        src_btn_layout.addWidget(clear_src_btn)
        src_btn_layout.addStretch()
        src_btn_layout.addWidget(self.sources_count_label)

        src_box.addWidget(self.sources_list, stretch=5)
        src_box.addLayout(src_btn_layout, stretch=1)
        layout_opt.addLayout(src_box)

        # 輸出目的資料夾列 (可選)
        row_out = QHBoxLayout()
        self.path_output_opt = DropLineEdit()
        self.path_output_opt.setPlaceholderText("Output destination (Optional, leave empty to save into each source folder)...")
        self.path_output_opt.textChanged.connect(lambda _: self.save_user_settings())
        browse_out_btn = QPushButton("Browse...")
        browse_out_btn.clicked.connect(lambda: self.browse_folder(self.path_output_opt))
        open_out_btn = QPushButton("Open in Finder")
        open_out_btn.clicked.connect(self.open_current_output_in_finder)
        clear_out_btn = QPushButton("Clear")
        clear_out_btn.clicked.connect(lambda: self.path_output_opt.clear())
        out_lbl = QLabel("Output:")
        out_lbl.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        row_out.addWidget(out_lbl)
        row_out.addWidget(self.path_output_opt, stretch=2)
        row_out.addWidget(browse_out_btn)
        row_out.addWidget(open_out_btn)
        row_out.addWidget(clear_out_btn)
        layout_opt.addLayout(row_out)

        # 控制與啟動列 (包含畫質與解析度 Preset)
        row_ctrl = QHBoxLayout()
        row_ctrl.setSpacing(10)

        self.res_preset_combo = QComboBox()
        for label, _, _ in RESOLUTION_PRESETS:
            self.res_preset_combo.addItem(label)
        self.res_preset_combo.setCurrentIndex(0)
        self.res_preset_combo.currentIndexChanged.connect(lambda _: self.save_user_settings())

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(50, 100)
        self.quality_spin.setValue(JPEG_QUALITY)
        self.quality_spin.setSuffix(" %")
        self.quality_spin.valueChanged.connect(lambda _: self.save_user_settings())

        rec_ram = get_recommended_ram_disk_gb()
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(0, 128)
        self.ram_spin.setValue(rec_ram)
        self.ram_spin.setSuffix(" GB")
        self.ram_spin.valueChanged.connect(lambda _: self.save_user_settings())

        self.strict_check = QCheckBox("Strict RAM")
        self.strict_check.setChecked(True)
        self.strict_check.setToolTip("Wait for RAM Disk space instead of spilling over to SSD")
        self.strict_check.toggled.connect(lambda _: self.save_user_settings())

        self.io_limit_spin = QSpinBox()
        self.io_limit_spin.setRange(1, max(1, self.num_workers))
        self.io_limit_spin.setValue(3)
        self.io_limit_spin.setSuffix(" Streams")
        self.io_limit_spin.setToolTip(
            "Max concurrent disk reads/writes (Recommended: 2~3 for External DAS/HDD/NAS to prevent disk thrashing and free up CPU cores for resizing)"
        )
        self.io_limit_spin.valueChanged.connect(lambda _: self.save_user_settings())

        self.start_btn_opt = QPushButton("▶  Start Optimizer")
        self.start_btn_opt.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; font-weight: bold;
                padding: 7px 20px; border: 1px solid #10b981; font-size: 13px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #1e293b; color: #475569; border-color: #334155; }
        """)
        self.start_btn_opt.clicked.connect(self.start_optimizer)

        row_ctrl.addWidget(QLabel("Max Resolution:"))
        row_ctrl.addWidget(self.res_preset_combo)
        row_ctrl.addSpacing(6)
        row_ctrl.addWidget(QLabel("JPEG Quality:"))
        row_ctrl.addWidget(self.quality_spin)
        row_ctrl.addSpacing(6)
        row_ctrl.addWidget(QLabel("RAM Disk:"))
        row_ctrl.addWidget(self.ram_spin)
        row_ctrl.addWidget(self.strict_check)
        row_ctrl.addSpacing(6)
        row_ctrl.addWidget(QLabel("Disk I/O Limit:"))
        row_ctrl.addWidget(self.io_limit_spin)
        row_ctrl.addStretch()
        row_ctrl.addWidget(self.start_btn_opt)
        layout_opt.addLayout(row_ctrl)

        self.tabs.addTab(tab_opt, "⚡ Comic Optimizer (Multi-Source & Resize)")

        # ---- Tab 2: Pack & Unpack Studio (Dual-Card Symmetrical Workspace) ----
        tab_pack = QWidget()
        layout_pack = QVBoxLayout(tab_pack)
        layout_pack.setContentsMargins(12, 10, 12, 10)
        layout_pack.setSpacing(8)

        # Shared Target Directory Bar + Live Inspector Badge
        row_pack = QHBoxLayout()
        row_pack.setSpacing(8)
        self.path_input_pack = DropLineEdit()
        self.path_input_pack.setPlaceholderText("Drag & drop target folder here, or click Browse...")
        self.path_input_pack.textChanged.connect(self.on_pack_target_changed)

        browse_btn_pack = QPushButton("Browse...")
        browse_btn_pack.clicked.connect(lambda: self.browse_folder(self.path_input_pack))

        open_pack_btn = QPushButton("Open in Finder")
        open_pack_btn.clicked.connect(
            lambda: reveal_in_finder(Path(self.path_input_pack.text().strip()))
            if self.path_input_pack.text().strip() else None
        )

        self.use_unzipped_btn = QPushButton("🎯 Switch to Unzipped")
        self.use_unzipped_btn.setToolTip(
            "One-click round-trip workflow: Jump into the latest Unzipped-YYYY-MM-DD folder to re-pack edited subfolders, or jump back to parent."
        )
        self.use_unzipped_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #38bdf8; font-weight: 600;
                border: 1px solid #0284c7; padding: 5px 11px;
            }
            QPushButton:hover { background-color: #0f172a; border-color: #38bdf8; }
            QPushButton:disabled { color: #475569; border-color: #1e293b; }
        """)
        self.use_unzipped_btn.setEnabled(False)
        self.use_unzipped_btn.clicked.connect(self.switch_pack_target_to_unzipped)

        target_lbl = QLabel("Target Folder:")
        target_lbl.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        row_pack.addWidget(target_lbl)
        row_pack.addWidget(self.path_input_pack, stretch=2)
        row_pack.addWidget(browse_btn_pack)
        row_pack.addWidget(open_pack_btn)
        row_pack.addWidget(self.use_unzipped_btn)
        layout_pack.addLayout(row_pack)

        # Live Directory Inspector Bar
        inspect_bar = QHBoxLayout()
        inspect_bar.setContentsMargins(2, 0, 2, 0)
        self.pack_inspect_label = QLabel("💡 Select or drop a target directory above to inspect subfolders & archives.")
        self.pack_inspect_label.setStyleSheet(
            "color: #94a3b8; font-size: 12px; font-weight: 600; background-color: #0b1120; "
            "border: 1px solid #1e293b; border-radius: 5px; padding: 4px 10px;"
        )
        inspect_bar.addWidget(self.pack_inspect_label, stretch=1)
        layout_pack.addLayout(inspect_bar)

        # Dual Action Cards (Left: Quick Folder Packer | Right: Quick Archive Unpacker)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        # --- Left Card: Quick Folder Packer ---
        pack_card = QFrame()
        pack_card.setStyleSheet("""
            QFrame {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QLabel { border: none; background: transparent; }
            QCheckBox { border: none; background: transparent; }
        """)
        pack_card_layout = QVBoxLayout(pack_card)
        pack_card_layout.setContentsMargins(14, 10, 14, 10)
        pack_card_layout.setSpacing(6)

        pack_title = QLabel("📦 Quick Folder Packer  (Subfolders ➔ Archive)")
        pack_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #60a5fa;")
        pack_sub = QLabel(
            "Packs each first-level subfolder into a zero-compression archive (ZIP_STORED / zip -0) with natural page sorting."
        )
        pack_sub.setWordWrap(True)
        pack_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")

        pack_opts_row = QHBoxLayout()
        self.cbz_format_check = QCheckBox("Output .cbz instead of .zip")
        self.cbz_format_check.setChecked(False)
        self.cbz_format_check.setToolTip("Save packed archives with .cbz comic book extension instead of .zip")
        self.cbz_format_check.toggled.connect(lambda _: self.save_user_settings())

        self.pack_move_orig_check = QCheckBox("Move subfolders to OriginalFiles-YYYY-MM-DD")
        self.pack_move_orig_check.setChecked(True)
        self.pack_move_orig_check.setToolTip(
            "After a subfolder is safely packed, move the original subfolder into OriginalFiles-YYYY-MM-DD"
        )
        self.pack_move_orig_check.toggled.connect(lambda _: self.save_user_settings())

        pack_opts_row.addWidget(self.cbz_format_check)
        pack_opts_row.addSpacing(10)
        pack_opts_row.addWidget(self.pack_move_orig_check)
        pack_opts_row.addStretch()

        self.start_btn_pack = QPushButton("📦  Pack All Subfolders")
        self.start_btn_pack.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white; font-weight: bold;
                padding: 7px 18px; border: 1px solid #3b82f6; font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #3b82f6; }
            QPushButton:disabled { background-color: #1e293b; color: #475569; border-color: #334155; }
        """)
        self.start_btn_pack.clicked.connect(self.start_folder_packer)

        pack_card_layout.addWidget(pack_title)
        pack_card_layout.addWidget(pack_sub)
        pack_card_layout.addLayout(pack_opts_row)
        pack_card_layout.addStretch()
        pack_card_layout.addWidget(self.start_btn_pack)

        # --- Right Card: Quick Archive Unpacker ---
        unpack_card = QFrame()
        unpack_card.setStyleSheet("""
            QFrame {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QLabel { border: none; background: transparent; }
            QCheckBox { border: none; background: transparent; }
        """)
        unpack_card_layout = QVBoxLayout(unpack_card)
        unpack_card_layout.setContentsMargins(14, 10, 14, 10)
        unpack_card_layout.setSpacing(6)

        unpack_title = QLabel("📂 Quick Archive Unpacker  (Archives ➔ Unzipped-YYYY-MM-DD)")
        unpack_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #c084fc;")
        unpack_sub = QLabel(
            "Batch-extracts .zip, .cbz, .rar, .cbr, .7z into Unzipped-YYYY-MM-DD/<ArchiveName>/ and isolates bad files to FileErr."
        )
        unpack_sub.setWordWrap(True)
        unpack_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")

        unpack_opts_row = QHBoxLayout()
        self.unpack_flatten_check = QCheckBox("Smart Flatten (Unwrap nested folder & clean junk)")
        self.unpack_flatten_check.setChecked(True)
        self.unpack_flatten_check.setToolTip(
            "Prevent double-nesting (Unzipped/Book/Book/001.jpg ➔ Unzipped/Book/001.jpg) and remove __MACOSX & .DS_Store"
        )
        self.unpack_flatten_check.toggled.connect(lambda _: self.save_user_settings())

        self.unpack_move_orig_check = QCheckBox("Move archives to OriginalFiles-YYYY-MM-DD")
        self.unpack_move_orig_check.setChecked(True)
        self.unpack_move_orig_check.setToolTip(
            "After an archive is safely extracted, move the original archive into OriginalFiles-YYYY-MM-DD"
        )
        self.unpack_move_orig_check.toggled.connect(lambda _: self.save_user_settings())

        unpack_opts_row.addWidget(self.unpack_flatten_check)
        unpack_opts_row.addSpacing(10)
        unpack_opts_row.addWidget(self.unpack_move_orig_check)
        unpack_opts_row.addStretch()

        self.start_btn_unpack = QPushButton("📂  Unpack All Archives")
        self.start_btn_unpack.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed; color: white; font-weight: bold;
                padding: 7px 18px; border: 1px solid #8b5cf6; font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #8b5cf6; }
            QPushButton:disabled { background-color: #1e293b; color: #475569; border-color: #334155; }
        """)
        self.start_btn_unpack.clicked.connect(self.start_archive_unpacker)

        unpack_card_layout.addWidget(unpack_title)
        unpack_card_layout.addWidget(unpack_sub)
        unpack_card_layout.addLayout(unpack_opts_row)
        unpack_card_layout.addStretch()
        unpack_card_layout.addWidget(self.start_btn_unpack)

        cards_row.addWidget(pack_card, stretch=1)
        cards_row.addWidget(unpack_card, stretch=1)
        layout_pack.addLayout(cards_row)

        self.tabs.addTab(tab_pack, "📦 Pack & Unpack Studio")

        # ---- Tab 3: History & Statistics (Full-Height Workspace) ----
        tab_hist = QWidget()
        layout_hist = QVBoxLayout(tab_hist)
        layout_hist.setContentsMargins(12, 12, 12, 12)
        layout_hist.setSpacing(12)

        # 頂部 4 張大字體 KPI 數據卡
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        c1, self.kpi_files_val, self.kpi_files_sub = self._create_kpi_card(
            "PROCESSED ARCHIVES", "0", "0 Pages | 0 Errors", "#f8fafc"
        )
        c2, self.kpi_orig_val, self.kpi_orig_sub = self._create_kpi_card(
            "ALL-TIME ORIGINAL SIZE", "0 B", "Raw input archives", "#94a3b8"
        )
        c3, self.kpi_out_val, self.kpi_out_sub = self._create_kpi_card(
            "ALL-TIME OPTIMIZED SIZE", "0 B", "Resized + Media output", "#38bdf8"
        )
        c4, self.kpi_saved_val, self.kpi_saved_sub = self._create_kpi_card(
            "TOTAL SPACE SAVED", "0 B", "▼ 0.0% Reduction", "#10b981"
        )

        kpi_row.addWidget(c1, stretch=1)
        kpi_row.addWidget(c2, stretch=1)
        kpi_row.addWidget(c3, stretch=1)
        kpi_row.addWidget(c4, stretch=1)
        layout_hist.addLayout(kpi_row)

        # 搜尋與管理列
        hist_ctrl_layout = QHBoxLayout()
        self.hist_search_input = QLineEdit()
        self.hist_search_input.setPlaceholderText("🔍 Filter by filename, source path, or status (SUCCESS / FILE_ERR)...")
        self.hist_search_input.textChanged.connect(lambda _: self.refresh_history_view())

        reveal_hist_btn = QPushButton("Open Selected in Finder")
        reveal_hist_btn.clicked.connect(self.reveal_selected_history_in_finder)
        refresh_hist_btn = QPushButton("Refresh")
        refresh_hist_btn.clicked.connect(self.refresh_history_view)
        export_csv_btn = QPushButton("Export CSV...")
        export_csv_btn.clicked.connect(self.export_history_csv)
        clear_hist_btn = QPushButton("Clear History")
        clear_hist_btn.setStyleSheet("QPushButton { color: #f87171; }")
        clear_hist_btn.clicked.connect(self.clear_history_records)

        hist_ctrl_layout.addWidget(self.hist_search_input, stretch=2)
        hist_ctrl_layout.addWidget(reveal_hist_btn)
        hist_ctrl_layout.addWidget(refresh_hist_btn)
        hist_ctrl_layout.addWidget(export_csv_btn)
        hist_ctrl_layout.addWidget(clear_hist_btn)
        layout_hist.addLayout(hist_ctrl_layout)

        # 歷史明細表格 (雙擊可在 Finder 開啟)
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels([
            "Timestamp", "Filename (Double-click to open folder)", "Status", "Pages",
            "Original Size", "Optimized Size", "Space Saved (%)", "Duration"
        ])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.verticalHeader().setDefaultSectionSize(28)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.cellDoubleClicked.connect(self.on_history_row_double_clicked)

        h_header = self.history_table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history_table.setColumnWidth(0, 150)
        self.history_table.setColumnWidth(2, 95)
        self.history_table.setColumnWidth(3, 75)
        self.history_table.setColumnWidth(4, 115)
        self.history_table.setColumnWidth(5, 115)
        self.history_table.setColumnWidth(6, 165)
        self.history_table.setColumnWidth(7, 85)
        layout_hist.addWidget(self.history_table, stretch=1)

        self.tabs.addTab(tab_hist, "📊 History & Statistics (All-Time)")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)

        # ---- 即時執行監控區 (切換到 Tab 3 時自動隱藏，將空間留給歷史大表) ----
        self.monitor_container = QWidget()
        monitor_layout = QVBoxLayout(self.monitor_container)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.setSpacing(8)

        prog_layout = QHBoxLayout()
        self.overall_progress = QProgressBar()
        self.overall_progress.setValue(0)
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("font-weight: 700; color: #38bdf8; min-width: 115px;")
        self.eta_label = QLabel("Elapsed: 00:00 | ETA: --:--")
        self.eta_label.setStyleSheet("color: #94a3b8; font-weight: 600;")

        self.ram_usage_label = QLabel("RAM Disk: Disabled")
        self.ram_usage_label.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(0)
        self.ram_bar.setFixedWidth(85)
        self.ram_bar.setTextVisible(False)

        self.abort_btn = QPushButton("⏹  Abort")
        self.abort_btn.setEnabled(False)
        self.abort_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: bold;
                padding: 4px 14px; border: 1px solid #ef4444;
            }
            QPushButton:hover { background-color: #ef4444; }
            QPushButton:disabled { background-color: #1e293b; color: #475569; border-color: #334155; }
        """)
        self.abort_btn.clicked.connect(self.abort_processing)

        prog_layout.addWidget(self.overall_progress, stretch=3)
        prog_layout.addSpacing(8)
        prog_layout.addWidget(self.status_label)
        prog_layout.addSpacing(6)
        prog_layout.addWidget(self.eta_label)
        prog_layout.addSpacing(10)
        prog_layout.addWidget(self.ram_usage_label)
        prog_layout.addWidget(self.ram_bar)
        prog_layout.addSpacing(8)
        prog_layout.addWidget(self.abort_btn)
        monitor_layout.addLayout(prog_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.worker_table = QTableWidget(self.num_workers, 5)
        self.worker_table.setHorizontalHeaderLabels(["Core", "Tier", "Stage", "Current Task", "Progress / Detail"])
        self.worker_table.verticalHeader().setVisible(False)
        self.worker_table.verticalHeader().setDefaultSectionSize(26)
        self.worker_table.setAlternatingRowColors(True)
        self.worker_table.setShowGrid(False)
        self.worker_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.worker_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        w_header = self.worker_table.horizontalHeader()
        w_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        w_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.worker_table.setColumnWidth(0, 58)
        self.worker_table.setColumnWidth(1, 68)
        self.worker_table.setColumnWidth(2, 120)
        self.worker_table.setColumnWidth(4, 130)
        splitter.addWidget(self.worker_table)

        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["Status", "Target Name", "Stats"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.verticalHeader().setDefaultSectionSize(26)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setShowGrid(False)
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.log_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        l_header = self.log_table.horizontalHeader()
        l_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        l_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.log_table.setColumnWidth(0, 88)
        self.log_table.setColumnWidth(2, 125)
        splitter.addWidget(self.log_table)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        monitor_layout.addWidget(splitter, stretch=1)
        main_layout.addWidget(self.monitor_container, stretch=1)

        for i in range(self.num_workers):
            c_item = QTableWidgetItem(f"C{i+1:02d}")
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.worker_table.setItem(i, 0, c_item)
            self.worker_table.setItem(i, 1, QTableWidgetItem("-"))
            self.worker_table.setItem(i, 2, QTableWidgetItem("Idle"))
            self.worker_table.setItem(i, 3, QTableWidgetItem("-"))
            self.worker_table.setItem(i, 4, QTableWidgetItem("-"))

        self.ram_timer = QTimer(self)
        self.ram_timer.timeout.connect(self.update_ram_usage)
        self.ram_timer.start(1000)

    def update_monitor_visibility(self):
        is_history_tab = (self.tabs.currentIndex() == 2)
        self.monitor_container.setVisible(not is_history_tab)
        self.tabs.parentWidget().layout().setStretchFactor(self.tabs, 1 if is_history_tab else 0)

    def open_current_output_in_finder(self):
        out_p = self.path_output_opt.text().strip()
        if out_p and os.path.exists(out_p):
            reveal_in_finder(Path(out_p))
        elif self.sources_list.count() > 0:
            reveal_in_finder(Path(self.sources_list.item(0).text()))

    def on_history_row_double_clicked(self, row: int, _col: int):
        item = self.history_table.item(row, 1)
        if not item:
            return
        out_dir = item.data(Qt.ItemDataRole.UserRole)
        src_dir = item.data(Qt.ItemDataRole.UserRole + 1)
        if out_dir and Path(out_dir).exists():
            reveal_in_finder(Path(out_dir))
        elif src_dir and Path(src_dir).exists():
            reveal_in_finder(Path(src_dir))

    def reveal_selected_history_in_finder(self):
        row = self.history_table.currentRow()
        if row >= 0:
            self.on_history_row_double_clicked(row, 1)

    def browse_add_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Source Folder")
        if folder:
            self.add_source_folder(folder)

    def remove_selected_source(self):
        for item in self.sources_list.selectedItems():
            self.sources_list.takeItem(self.sources_list.row(item))
        self.update_sources_count_label()
        self.save_user_settings()

    def clear_all_sources(self):
        self.sources_list.clear()
        self.update_sources_count_label()
        self.save_user_settings()

    def browse_folder(self, target_line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            target_line_edit.setText(folder)
            self.save_user_settings()

    def on_pack_target_changed(self, _text: str = ""):
        self.refresh_pack_target_stats()
        self.save_user_settings()

    def refresh_pack_target_stats(self):
        if not hasattr(self, "pack_inspect_label"):
            return
        folder_str = self.path_input_pack.text().strip()
        if not folder_str:
            self.pack_inspect_label.setText(
                "💡 Select or drop a target directory above to inspect subfolders & archives."
            )
            self.start_btn_pack.setText("📦  Pack All Subfolders")
            self.start_btn_unpack.setText("📂  Unpack All Archives")
            self.use_unzipped_btn.setEnabled(False)
            self.use_unzipped_btn.setText("🎯 Switch to Unzipped")
            return

        p = Path(folder_str)
        if not p.is_dir():
            self.pack_inspect_label.setText("⚠️ Target directory does not exist.")
            self.start_btn_pack.setText("📦  Pack All Subfolders")
            self.start_btn_unpack.setText("📂  Unpack All Archives")
            self.use_unzipped_btn.setEnabled(False)
            return

        subfolders_cnt = 0
        archives_cnt = 0
        unzipped_dirs = []
        try:
            for item in p.iterdir():
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    if item.name.startswith("Unzipped-"):
                        unzipped_dirs.append(item)
                    if not item.name.startswith(SYSTEM_DIR_PREFIXES):
                        subfolders_cnt += 1
                elif item.is_file() and item.suffix.lower() in ARCHIVE_EXTENSIONS:
                    archives_cnt += 1
        except Exception:
            pass

        self.start_btn_pack.setText(f"📦  Pack Subfolders ({subfolders_cnt})")
        self.start_btn_unpack.setText(f"📂  Unpack Archives ({archives_cnt})")

        # Configure the round-trip quick-switch button
        if p.name.startswith("Unzipped-") and p.parent.is_dir():
            self.use_unzipped_btn.setEnabled(True)
            self.use_unzipped_btn.setText("⬆️ Back to Parent Folder")
            self.use_unzipped_btn.setProperty("target_jump", str(p.parent))
        elif unzipped_dirs:
            latest_unz = sorted(unzipped_dirs, key=lambda x: x.name)[-1]
            self.use_unzipped_btn.setEnabled(True)
            self.use_unzipped_btn.setText(f"🎯 Switch to {latest_unz.name}")
            self.use_unzipped_btn.setProperty("target_jump", str(latest_unz))
        else:
            self.use_unzipped_btn.setEnabled(False)
            self.use_unzipped_btn.setText("🎯 Switch to Unzipped")
            self.use_unzipped_btn.setProperty("target_jump", "")

        unz_hint = (
            f"   |   ✨ Found {len(unzipped_dirs)} Unzipped folder(s) — click '{self.use_unzipped_btn.text()}' to re-pack!"
            if unzipped_dirs else ""
        )
        self.pack_inspect_label.setText(
            f"📊 Live Target Scan:   📦 {subfolders_cnt} Subfolder(s) ready to Pack   |   "
            f"📂 {archives_cnt} Archive(s) (.zip/.cbz/.rar/.cbr/.7z) ready to Unpack{unz_hint}"
        )

    def switch_pack_target_to_unzipped(self):
        jump_to = self.use_unzipped_btn.property("target_jump")
        if jump_to and os.path.isdir(jump_to):
            self.path_input_pack.setText(jump_to)

    def on_tab_changed(self, idx: int):
        if idx == 1:
            self.refresh_pack_target_stats()
        elif idx == 2:
            self.refresh_history_view()
        self.update_monitor_visibility()
        self.save_user_settings()

    def load_user_settings(self):
        self._loading_settings = True
        try:
            cfg = load_app_config()
            if not cfg:
                return
            for src in cfg.get("source_dirs", []):
                if isinstance(src, str) and src.strip():
                    existing = [self.sources_list.item(i).text() for i in range(self.sources_list.count())]
                    if src not in existing:
                        self.sources_list.addItem(src)
            self.update_sources_count_label()

            if "output_dir" in cfg:
                self.path_output_opt.setText(str(cfg["output_dir"]))
            if "ram_gb" in cfg and isinstance(cfg["ram_gb"], int):
                self.ram_spin.setValue(max(0, min(128, cfg["ram_gb"])))
            if "strict_ram" in cfg:
                self.strict_check.setChecked(bool(cfg["strict_ram"]))
            if "resolution_preset_index" in cfg and isinstance(cfg["resolution_preset_index"], int):
                p_idx = cfg["resolution_preset_index"]
                if 0 <= p_idx < len(RESOLUTION_PRESETS):
                    self.res_preset_combo.setCurrentIndex(p_idx)
            if "jpeg_quality" in cfg and isinstance(cfg["jpeg_quality"], int):
                self.quality_spin.setValue(max(50, min(100, cfg["jpeg_quality"])))
            if "io_limit" in cfg and isinstance(cfg["io_limit"], int):
                self.io_limit_spin.setValue(max(1, min(self.num_workers, cfg["io_limit"])))
            if "pack_target_dir" in cfg:
                self.path_input_pack.setText(str(cfg["pack_target_dir"]))
            if "pack_cbz_format" in cfg:
                self.cbz_format_check.setChecked(bool(cfg["pack_cbz_format"]))
            if "pack_move_orig" in cfg:
                self.pack_move_orig_check.setChecked(bool(cfg["pack_move_orig"]))
            if "unpack_smart_flatten" in cfg:
                self.unpack_flatten_check.setChecked(bool(cfg["unpack_smart_flatten"]))
            if "unpack_move_orig" in cfg:
                self.unpack_move_orig_check.setChecked(bool(cfg["unpack_move_orig"]))
            if "current_tab_index" in cfg and isinstance(cfg["current_tab_index"], int):
                tab_idx = cfg["current_tab_index"]
                if 0 <= tab_idx < self.tabs.count():
                    self.tabs.setCurrentIndex(tab_idx)
        finally:
            self._loading_settings = False
            self.refresh_pack_target_stats()

    def save_user_settings(self):
        if getattr(self, "_loading_settings", False):
            return
        cfg = {
            "source_dirs": [self.sources_list.item(i).text() for i in range(self.sources_list.count())],
            "output_dir": self.path_output_opt.text().strip(),
            "ram_gb": self.ram_spin.value(),
            "strict_ram": self.strict_check.isChecked(),
            "resolution_preset_index": self.res_preset_combo.currentIndex(),
            "jpeg_quality": self.quality_spin.value(),
            "io_limit": self.io_limit_spin.value(),
            "pack_target_dir": self.path_input_pack.text().strip(),
            "pack_cbz_format": self.cbz_format_check.isChecked(),
            "pack_move_orig": self.pack_move_orig_check.isChecked(),
            "unpack_smart_flatten": self.unpack_flatten_check.isChecked(),
            "unpack_move_orig": self.unpack_move_orig_check.isChecked(),
            "current_tab_index": self.tabs.currentIndex(),
        }
        save_app_config(cfg)

    def refresh_history_view(self):
        stats = HistoryDatabase.get_summary_stats()
        ok_cnt = stats["success_count"]
        err_cnt = stats["corrupted_count"] + stats["error_count"]
        pages = stats["total_pages"]
        orig_b = stats["total_orig_bytes"]
        out_b = stats["total_out_bytes"]
        saved_b = stats["total_saved_bytes"]
        saved_pct = (saved_b / orig_b * 100.0) if orig_b > 0 else 0.0

        self.kpi_files_val.setText(f"{ok_cnt:,} OK")
        self.kpi_files_sub.setText(f"{pages:,} Pages  |  {err_cnt:,} Errors")
        self.kpi_orig_val.setText(format_bytes(orig_b))
        self.kpi_out_val.setText(format_bytes(out_b))
        self.kpi_saved_val.setText(format_bytes(max(0, saved_b)))
        self.kpi_saved_sub.setText(f"▼ {saved_pct:.1f}% Storage Reduction")

        search_kw = self.hist_search_input.text() if hasattr(self, "hist_search_input") else ""
        rows = HistoryDatabase.query_records(search_kw, limit=1000)
        self.history_table.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            ts, fname, status, page_cnt, f_orig, f_out, f_saved, dur, src_d, out_d = row

            ts_item = QTableWidgetItem(ts)
            ts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            fn_item = QTableWidgetItem(fname)
            fn_item.setToolTip(f"File: {fname}\nSource: {src_d}\nOutput: {out_d}\n(Double-click to open in Finder)")
            fn_item.setData(Qt.ItemDataRole.UserRole, out_d)
            fn_item.setData(Qt.ItemDataRole.UserRole + 1, src_d)

            st_item = QTableWidgetItem(status)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "SUCCESS":
                st_item.setForeground(QColor("#10b981"))
            else:
                st_item.setForeground(QColor("#ef4444"))

            pg_item = QTableWidgetItem(f"{page_cnt}P" if status == "SUCCESS" else "-")
            pg_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            orig_item = QTableWidgetItem(format_bytes(f_orig) if f_orig > 0 else "-")
            orig_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            out_item = QTableWidgetItem(format_bytes(f_out) if status == "SUCCESS" else "-")
            out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if status == "SUCCESS" and f_orig > 0:
                pct = (f_saved / f_orig) * 100.0
                sign = "▼" if f_saved >= 0 else "▲"
                sav_str = f"{format_bytes(abs(f_saved))} ({sign} {abs(pct):.1f}%)"
                sav_item = QTableWidgetItem(sav_str)
                sav_item.setForeground(QColor("#10b981") if f_saved >= 0 else QColor("#f59e0b"))
            else:
                sav_item = QTableWidgetItem("-")
            sav_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            dur_item = QTableWidgetItem(f"{dur:.1f}s")
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.history_table.setItem(r_idx, 0, ts_item)
            self.history_table.setItem(r_idx, 1, fn_item)
            self.history_table.setItem(r_idx, 2, st_item)
            self.history_table.setItem(r_idx, 3, pg_item)
            self.history_table.setItem(r_idx, 4, orig_item)
            self.history_table.setItem(r_idx, 5, out_item)
            self.history_table.setItem(r_idx, 6, sav_item)
            self.history_table.setItem(r_idx, 7, dur_item)

    def export_history_csv(self):
        rows = HistoryDatabase.query_records(self.hist_search_input.text(), limit=100000)
        if not rows:
            QMessageBox.information(self, "Export CSV", "No history records to export.")
            return
        default_name = str(Path.home() / f"comic_optimizer_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        file_path, _ = QFileDialog.getSaveFileName(self, "Export History to CSV", default_name, "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Filename", "Status", "Pages",
                    "Original Bytes", "Optimized Bytes", "Saved Bytes", "Saved (%)",
                    "Duration (s)", "Source Directory", "Output Directory"
                ])
                for r in rows:
                    ts, fname, status, page_cnt, f_orig, f_out, f_saved, dur, src_d, out_d = r
                    pct = f"{(f_saved / f_orig * 100.0):.2f}%" if (status == "SUCCESS" and f_orig > 0) else "0.00%"
                    writer.writerow([
                        ts, fname, status, page_cnt,
                        f_orig, f_out, f_saved, pct,
                        f"{dur:.2f}", src_d, out_d
                    ])
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} records to:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Failed to write CSV:\n{e}")

    def clear_history_records(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to permanently clear all conversion history and all-time statistics?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            HistoryDatabase.clear_all()
            self.refresh_history_view()

    def update_ram_usage(self):
        text, pct = get_ram_disk_usage()
        self.ram_usage_label.setText(f"RAM Disk: {text}")
        self.ram_bar.setValue(int(min(100.0, max(0.0, pct))))
        if pct >= 85.0:
            self.ram_bar.setStyleSheet("QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }")
        else:
            self.ram_bar.setStyleSheet("QProgressBar::chunk { background-color: #10b981; border-radius: 4px; }")

    def start_optimizer(self):
        source_dirs = [self.sources_list.item(i).text() for i in range(self.sources_list.count())]
        out_path = self.path_output_opt.text().strip()

        if not source_dirs:
            QMessageBox.warning(self, "Input Error", "Please add at least one source directory.")
            return

        for d in source_dirs:
            if not os.path.isdir(d):
                QMessageBox.warning(self, "Input Error", f"Source directory does not exist:\n{d}")
                return

        if out_path and not os.path.isdir(out_path):
            QMessageBox.warning(self, "Input Error", "The specified output directory does not exist.")
            return

        preset_idx = self.res_preset_combo.currentIndex()
        _, max_w, max_h = RESOLUTION_PRESETS[preset_idx] if 0 <= preset_idx < len(RESOLUTION_PRESETS) else (None, MAX_WIDTH, MAX_HEIGHT)
        jpeg_q = self.quality_spin.value()

        self.save_user_settings()
        self.prepare_ui_for_start()
        self.worker_thread = OptimizerThread(
            source_dirs_list=source_dirs,
            global_output_dir_str=out_path,
            ram_gb=self.ram_spin.value(),
            strict_ram=self.strict_check.isChecked(),
            max_w=max_w,
            max_h=max_h,
            jpeg_quality=jpeg_q,
            io_limit=self.io_limit_spin.value()
        )
        self.bind_and_start_thread()

    def start_folder_packer(self):
        folder_path = self.path_input_pack.text().strip()
        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Input Error", "Please provide a valid directory containing subfolders.")
            return

        self.save_user_settings()
        out_ext = ".cbz" if self.cbz_format_check.isChecked() else ".zip"
        move_orig = self.pack_move_orig_check.isChecked()
        self.prepare_ui_for_start()
        self.worker_thread = FolderPackerThread(
            source_dir_str=folder_path,
            out_ext=out_ext,
            move_orig=move_orig,
            io_limit=self.io_limit_spin.value()
        )
        self.bind_and_start_thread()

    def start_archive_unpacker(self):
        folder_path = self.path_input_pack.text().strip()
        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Input Error", "Please provide a valid directory containing archives.")
            return

        self.save_user_settings()
        smart_flatten = self.unpack_flatten_check.isChecked()
        move_orig = self.unpack_move_orig_check.isChecked()
        self.prepare_ui_for_start()
        self.worker_thread = ArchiveUnpackerThread(
            source_dir_str=folder_path,
            smart_flatten=smart_flatten,
            move_orig=move_orig,
            io_limit=self.io_limit_spin.value()
        )
        self.bind_and_start_thread()

    def prepare_ui_for_start(self):
        self.batch_start_time = time.time()
        self._rendered_log_count = 0
        self.start_btn_opt.setEnabled(False)
        self.start_btn_pack.setEnabled(False)
        self.start_btn_unpack.setEnabled(False)
        self.use_unzipped_btn.setEnabled(False)
        self.tabs.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.log_table.setRowCount(0)
        self.log_table.setHorizontalHeaderLabels(["Status", "Target Name", "Stats"])
        self.overall_progress.setValue(0)
        self.status_label.setText("Processing...")
        self.eta_label.setText("Elapsed: 00:00 | ETA: Calculating...")

    def bind_and_start_thread(self):
        self.worker_thread.progress_signal.connect(self.on_progress)
        self.worker_thread.worker_signal.connect(self.on_worker_update)
        self.worker_thread.log_signal.connect(self.on_log_update)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()

    def abort_processing(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.status_label.setText("Aborting...")
            self.worker_thread.abort()
            self.abort_btn.setEnabled(False)

    @staticmethod
    def _format_mm_ss(seconds: float) -> str:
        secs = max(0, int(seconds))
        hrs, rem = divmod(secs, 3600)
        mins, s = divmod(rem, 60)
        return f"{hrs:02d}:{mins:02d}:{s:02d}" if hrs > 0 else f"{mins:02d}:{s:02d}"

    def on_progress(self, done: int, total: int):
        self.overall_progress.setMaximum(total)
        self.overall_progress.setValue(done)
        self.status_label.setText(f"{done}/{total} Completed")
        if self.batch_start_time and done > 0 and total > 0:
            elapsed = max(0.1, time.time() - self.batch_start_time)
            rate_per_min = (done / elapsed) * 60.0
            remaining = max(0, total - done)
            eta_sec = (elapsed / done) * remaining
            self.eta_label.setText(
                f"Elapsed: {self._format_mm_ss(elapsed)} | {rate_per_min:.1f} files/min | ETA: ~{self._format_mm_ss(eta_sec)}"
            )

    def on_worker_update(self, worker_statuses: dict):
        for wid, info in worker_statuses.items():
            if wid < self.num_workers:
                stage = info.get("stage", "Idle")
                name = info.get("name", "-")

                tier_item = QTableWidgetItem(info.get("tier", "-"))
                tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.worker_table.setItem(wid, 1, tier_item)

                stage_item = QTableWidgetItem(stage)
                stage_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if stage == "Assisting":
                    stage_item.setForeground(QColor("#f59e0b"))
                elif "Resizing" in stage or stage == "Storing":
                    stage_item.setForeground(QColor("#a855f7"))
                elif stage in ("Extracting", "Packing", "Archiving"):
                    stage_item.setForeground(QColor("#eab308"))
                elif stage == "Queued I/O":
                    stage_item.setForeground(QColor("#38bdf8"))
                self.worker_table.setItem(wid, 2, stage_item)

                name_item = QTableWidgetItem(name)
                name_item.setToolTip(name)
                self.worker_table.setItem(wid, 3, name_item)

                pct = int(info.get("progress", 0.0) * 100)
                detail = info.get("detail", "")
                detail_str = f"{pct}% {detail}".strip() if name != "-" else "-"
                detail_item = QTableWidgetItem(detail_str)
                detail_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.worker_table.setItem(wid, 4, detail_item)

    def on_log_update(self, logs: list):
        total_logs = len(logs)
        rendered = getattr(self, "_rendered_log_count", 0)
        if total_logs <= rendered:
            return

        v_bar = self.log_table.verticalScrollBar()
        was_at_top = v_bar.value() <= 2
        old_val = v_bar.value()

        new_items = logs[rendered:total_logs]
        self.log_table.setUpdatesEnabled(False)
        try:
            for item in new_items:
                if isinstance(item, (tuple, list)) and len(item) == 3:
                    tag, name, stat = item
                    self.log_table.insertRow(0)

                    status_item = QTableWidgetItem(f"[{tag}]")
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if tag == "OK":
                        status_item.setForeground(QColor("#10b981"))
                    elif tag in ("FILE_ERR", "SYS_ERR"):
                        status_item.setForeground(QColor("#ef4444"))
                    elif tag in ("SKIP", "INFO"):
                        status_item.setForeground(QColor("#94a3b8"))
                    else:
                        status_item.setForeground(QColor("#f59e0b"))

                    name_item = QTableWidgetItem(name)
                    name_item.setToolTip(name)

                    stat_item = QTableWidgetItem(f"({stat})")
                    stat_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                    self.log_table.setItem(0, 0, status_item)
                    self.log_table.setItem(0, 1, name_item)
                    self.log_table.setItem(0, 2, stat_item)
            self._rendered_log_count = total_logs
            self.log_table.setHorizontalHeaderLabels(["Status", f"Target Name ({total_logs})", "Stats"])
        finally:
            self.log_table.setUpdatesEnabled(True)

        if was_at_top:
            v_bar.setValue(0)
        else:
            v_bar.setValue(old_val + len(new_items) * 26)

    def on_error(self, message: str):
        QMessageBox.warning(self, "Error", message)
        self.reset_ui()

    def on_finished(self, summary: dict):
        self.reset_ui()
        self.refresh_history_view()
        self.refresh_pack_target_stats()
        mode = summary.get("mode")
        hrs, rem = divmod(int(summary["total_time"]), 3600)
        mins, secs = divmod(rem, 60)
        time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

        if mode == "optimizer":
            orig_b = summary.get("orig_bytes", 0)
            out_b = summary.get("out_bytes", 0)
            saved_bytes = orig_b - out_b
            saved_pct = (saved_bytes / orig_b * 100) if orig_b > 0 else 0.0
            msg = (
                f"Execution Time: {time_str}\n"
                f"Sources Processed: {summary.get('source_count', 0)} directories\n"
                f"Files Completed: {summary.get('success', 0)} OK / {summary.get('corrupted', 0)} Corrupted / {summary.get('error', 0)} Failed\n\n"
                f"Original Size: {format_bytes(orig_b)}\n"
                f"Optimized Size: {format_bytes(out_b)}\n"
                f"Space Saved: {format_bytes(max(0, saved_bytes))} (▼ {saved_pct:.1f}%)\n\n"
                f"Output Location:\n- {summary.get('out_loc', '')}"
            )
        elif mode == "unpacker":
            unz_dest = summary.get("unzipped_dir") or summary.get("target_dir", "")
            msg = (
                f"Execution Time: {time_str}\n"
                f"Archives Unpacked: {summary.get('success', 0)} OK / {summary.get('corrupted', 0)} Corrupted / "
                f"{summary.get('skipped', 0)} Skipped / {summary.get('error', 0)} Failed\n\n"
                f"Unzipped Destination:\n- {unz_dest}\n\n"
                f"💡 Tip: Click '🎯 Switch to Unzipped' in the Studio toolbar to inspect or re-pack!"
            )
        else:
            msg = (
                f"Execution Time: {time_str}\n"
                f"Subfolders Packed: {summary.get('success', 0)} OK / {summary.get('skipped', 0)} Skipped\n\n"
                f"Target Location:\n- {summary.get('target_dir', '')}"
            )

        title = "Execution Aborted" if summary["aborted"] else "Processing Complete"
        QMessageBox.information(self, title, msg)

    def reset_ui(self):
        self.start_btn_opt.setEnabled(True)
        self.start_btn_pack.setEnabled(True)
        self.start_btn_unpack.setEnabled(True)
        self.tabs.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.status_label.setText("Idle")
        self.eta_label.setText("Elapsed: 00:00 | ETA: --:--")
        self.refresh_pack_target_stats()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)
    app = QApplication(sys.argv)
    app.setApplicationName("Comic Optimizer")
    app.setApplicationDisplayName("Comic Optimizer")
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())