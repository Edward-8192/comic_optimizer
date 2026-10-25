import os
import sys

# 抑制 macOS Cocoa/Qt 系統輸入法與輔助技術的底層嘈雜 Log
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false"
os.environ["OS_ACTIVITY_MODE"] = "disable"

import re
import html
import shutil
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
    QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor

# ==================== Core Configuration ====================
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
JPEG_QUALITY = 85
MAX_RAM_RETRIES = 5
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
)

ARCHIVE_MAIN_EXT = '.cbz'
ARCHIVE_OTHER_EXT = '.zip'

def get_resource_path(relative_path: str) -> str:
    """取得 PyInstaller 打包後的內部資源路徑或開發時的本地路徑"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

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

def get_uncompressed_size_mb_fast(archive_path: Path) -> float:
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

def inspect_archive_worker(item_dict: dict):
    arch = item_dict["path"]
    return {
        "path": arch,
        "src_root": item_dict["src_root"],
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
            all_err = "".join(captured_output) + (" " + stderr_out if stderr_out else "")
            if any(k in all_err.lower() for k in ["no space left", "not enough space", "disk full", "write error"]):
                return False, "NO_SPACE"
            return False, "CORRUPTED"
    except Exception as e:
        if "No space left on device" in str(e): return False, "NO_SPACE"
        return False, "CORRUPTED"

def create_zip_store(target_archive: Path, file_pairs: list, root_folder_name: str = None):
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
        if has_root_files or len(top_dirs) > 1:
            needs_wrapper = True

    with zipfile.ZipFile(target_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
        for disk_path, arc_name in file_pairs:
            final_arc_name = f"{root_folder_name}/{arc_name}" if needs_wrapper else arc_name
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
    idx, img_path, rel_path, out_img_path = args
    try:
        resize_and_convert_image(img_path, out_img_path)
        new_rel_path = str(Path(rel_path).with_suffix('.jpg'))
        return (out_img_path, new_rel_path)
    except Exception:
        return (img_path, rel_path)

def execute_pipeline(
    archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
    temp_target_dir, tier_tag, worker_id, status_dict, cpu_token_manager
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
        extracted_dir.mkdir(parents=True, exist_ok=True)
        processed_dir_tmp.mkdir(parents=True, exist_ok=True)

        success, reason = extract_archive_stream(archive_path, extracted_dir, update_extract_progress)
        if not success:
            return False, reason, 0

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
            return False, "NO_VALID_FILES", 0

        total_imgs = len(static_images)
        processed_images = []
        tasks = [
            (idx, img_path, rel_path, processed_dir_tmp / f"img_{idx:05d}.jpg")
            for idx, (img_path, rel_path) in enumerate(static_images)
        ]

        CHUNK_SIZE = 24
        for chunk_start in range(0, total_imgs, CHUNK_SIZE):
            chunk_tasks = tasks[chunk_start:chunk_start + CHUNK_SIZE]

            borrowed_tokens = 0
            borrowed_idle_wids = []
            with cpu_token_lock:
                idle_wids = [
                    wid for wid, info in status_dict.items()
                    if wid != worker_id and info.get("stage", "") == "Idle"
                ]
                available_tokens = max(0, len(idle_wids) - allocated_tokens.value)
                if available_tokens > 0:
                    desired = min(7, available_tokens)
                    allocated_tokens.value += desired
                    borrowed_tokens = desired
                    borrowed_idle_wids = idle_wids[:desired]

            for b_wid in borrowed_idle_wids:
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
                    for b_wid in borrowed_idle_wids:
                        status_dict[b_wid] = {
                            "tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""
                        }

            done_count = len(processed_images)
            pct = 0.25 + (0.65 * (done_count / max(1, total_imgs)))
            status_dict[worker_id] = {
                "tier": tier_tag, "stage": stage_desc, "name": archive_path.name,
                "progress": pct, "detail": f"{done_count}/{total_imgs}P"
            }

        status_dict[worker_id] = {
            "tier": tier_tag, "stage": "Packaging", "name": archive_path.name,
            "progress": 0.95, "detail": "STORE Write"
        }
        if processed_images:
            create_zip_store(resized_dir / f"{stem_name}{ARCHIVE_MAIN_EXT}", processed_images)
        if animated_images:
            create_zip_store(anim_dir / f"{stem_name}-Animated{ARCHIVE_OTHER_EXT}", animated_images, root_folder_name=f"{stem_name}-Animated")
        if media_files:
            create_zip_store(media_dir / f"{stem_name}-Media{ARCHIVE_OTHER_EXT}", media_files, root_folder_name=f"{stem_name}-Media")

    status_dict[worker_id] = {
        "tier": tier_tag, "stage": "Archiving", "name": archive_path.name,
        "progress": 1.0, "detail": "Moving"
    }
    safe_move_file(archive_path, original_files_dir)
    return True, "SUCCESS", len(static_images)

def worker_task(
    archive_path_str: str, target_tier: str, reserved_mb: float,
    resized_dir_str: str, anim_dir_str: str, media_dir_str: str,
    original_files_dir_str: str, error_dir_str: str, file_err_dir_str: str,
    worker_id: int, status_dict, recent_logs, ram_manager_tuple, cpu_token_manager
):
    archive_path = Path(archive_path_str)
    resized_dir = Path(resized_dir_str)
    anim_dir = Path(anim_dir_str)
    media_dir = Path(media_dir_str)
    original_files_dir = Path(original_files_dir_str)
    error_dir = Path(error_dir_str)
    file_err_dir = Path(file_err_dir_str)

    current_allocated_ram, ram_budget_mb, ram_lock = ram_manager_tuple
    tier_tag = "RAM" if target_tier == "RAM" else "SSD"
    temp_target_dir = str(RAM_DISK_MOUNT) if target_tier == "RAM" else None

    start_task_time = time.time()
    clean_name = sanitize_log_text(archive_path.name)
    try:
        ok, reason, img_count = execute_pipeline(
            archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
            temp_target_dir, tier_tag, worker_id, status_dict, cpu_token_manager
        )

        if not ok and reason == "NO_SPACE" and temp_target_dir is not None:
            recent_logs.append(("WARN", clean_name, "RAM limit -> SSD"))
            tier_tag = "SSD"
            ok, reason, img_count = execute_pipeline(
                archive_path, resized_dir, anim_dir, media_dir, original_files_dir,
                None, tier_tag, worker_id, status_dict, cpu_token_manager
            )
            if not ok:
                safe_move_file(archive_path, error_dir)
                recent_logs.append(("SYS_ERR", clean_name, "Retry Failed"))
                status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
                return archive_path_str, "ERROR", 0

        elif not ok and reason in ("CORRUPTED", "NO_VALID_FILES"):
            safe_move_file(archive_path, file_err_dir)
            recent_logs.append(("FILE_ERR", clean_name, "Corrupted File"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "FILE_ERR", 0

        elif not ok:
            safe_move_file(archive_path, error_dir)
            recent_logs.append(("SYS_ERR", clean_name, "Execution Error"))
            status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ERROR", 0
    finally:
        if target_tier == "RAM" and reserved_mb > 0:
            with ram_lock:
                current_allocated_ram.value = max(0.0, current_allocated_ram.value - reserved_mb)

    total_cost = time.time() - start_task_time
    recent_logs.append(("OK", clean_name, f"{total_cost:.1f}s, {img_count}P"))
    status_dict[worker_id] = {"tier": tier_tag, "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
    return archive_path_str, "SUCCESS", total_cost

def pack_folder_worker(folder_path_str: str, out_ext: str, worker_id: int, status_dict, recent_logs, move_to_orig_dir_str: str = None):
    folder_path = Path(folder_path_str)
    target_archive = folder_path.parent / f"{folder_path.name}{out_ext}"
    start_time = time.time()

    clean_name = sanitize_log_text(folder_path.name)
    status_dict[worker_id] = {
        "tier": "DISK", "stage": "Packing", "name": clean_name,
        "progress": 0.1, "detail": "Listing"
    }

    file_pairs = []
    for root, _, files in os.walk(folder_path):
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
    status_dict[worker_id] = {
        "tier": "DISK", "stage": "Storing", "name": clean_name,
        "progress": 0.4, "detail": f"{total_files} Files"
    }

    file_pairs.sort(key=lambda x: natural_sort_key(x[1]))
    with zipfile.ZipFile(target_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
        for fp, arc_name in file_pairs:
            zf.write(fp, arcname=arc_name)

    if move_to_orig_dir_str:
        orig_dest = Path(move_to_orig_dir_str)
        safe_move_file(folder_path, orig_dest)

    cost = time.time() - start_time
    recent_logs.append(("OK", clean_name, f"Packed ({cost:.1f}s, {total_files}F)"))
    status_dict[worker_id] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}
    return folder_path_str, "SUCCESS"

# ==================== Background Threads ====================
class OptimizerThread(QThread):
    progress_signal = pyqtSignal(int, int)
    worker_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(list)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, source_dirs_list: list, global_output_dir_str: str, ram_gb: int, strict_ram: bool):
        super().__init__()
        self.source_dirs = [Path(d) for d in source_dirs_list]
        self.global_output_dir = Path(global_output_dir_str) if global_output_dir_str else None
        self.ram_gb = ram_gb
        self.strict_ram = strict_ram
        self.is_aborted = False

    def abort(self):
        self.is_aborted = True

    def run(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        num_workers = max(1, os.cpu_count() - 1)
        manager = multiprocessing.Manager()
        worker_statuses = manager.dict()
        recent_logs = manager.list()
        file_err_stems = manager.list()
        for i in range(num_workers):
            worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}

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
            with ProcessPoolExecutor(max_workers=num_workers) as pack_executor:
                pack_futures = {}
                for idx, (folder, orig_dest) in enumerate(all_pre_sub_dirs):
                    wid = idx % num_workers
                    f = pack_executor.submit(
                        pack_folder_worker, str(folder), ".zip", wid,
                        worker_statuses, recent_logs, str(orig_dest)
                    )
                    pack_futures[f] = folder

                for f in as_completed(pack_futures):
                    if self.is_aborted:
                        break
                    self.worker_signal.emit(dict(worker_statuses))
                    self.log_signal.emit(list(recent_logs))

        if self.is_aborted:
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
        current_allocated_ram = manager.Value('d', 0.0)
        ram_lock = manager.Lock()
        ram_manager_tuple = (current_allocated_ram, ram_budget_mb, ram_lock)

        allocated_cpu_tokens = manager.Value('i', 0)
        cpu_token_lock = manager.Lock()
        cpu_token_manager = (allocated_cpu_tokens, cpu_token_lock)

        pending_queue = []
        max_inspect_threads = min(32, (os.cpu_count() or 4) * 4)
        with ThreadPoolExecutor(max_workers=max_inspect_threads) as inspector:
            futures = [inspector.submit(inspect_archive_worker, item) for item in archive_items]
            for f in as_completed(futures):
                if self.is_aborted: break
                try: pending_queue.append(f.result())
                except Exception: pass

        if self.is_aborted:
            if ram_active: cleanup_ram_disk()
            return

        pending_queue.sort(key=lambda x: x["uncompressed_mb"], reverse=True)

        global_start_time = time.time()
        success_count = 0
        fail_err_count = 0
        corrupted_count = 0
        done_total = 0

        available_workers = set(range(num_workers))
        active_futures = {}

        try:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                while (pending_queue or active_futures) and not self.is_aborted:
                    done_futures = [f for f in active_futures if f.done()]
                    for f in done_futures:
                        worker_id = active_futures.pop(f)
                        available_workers.add(worker_id)
                        done_total += 1
                        try:
                            arch_path_done, result_code, _ = f.result()
                            if result_code == "SUCCESS": success_count += 1
                            elif result_code == "FILE_ERR":
                                corrupted_count += 1
                                file_err_stems.append(Path(arch_path_done).stem)
                            else: fail_err_count += 1
                        except Exception:
                            fail_err_count += 1
                        self.progress_signal.emit(done_total, len(archive_items))

                    while available_workers and pending_queue and not self.is_aborted:
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
                                if self.strict_ram: continue
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
                                worker_id, worker_statuses, recent_logs, ram_manager_tuple, cpu_token_manager
                            )
                            active_futures[f] = worker_id
                        else:
                            break

                    self.worker_signal.emit(dict(worker_statuses))
                    self.log_signal.emit(list(recent_logs))
                    time.sleep(0.1)

                if self.is_aborted:
                    for p in executor._processes.values():
                        try: p.terminate()
                        except Exception: pass
        finally:
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

        # 空間統計計算
        total_orig_bytes = sum(get_dir_size_bytes(s / f"OriginalFiles-{today_str}") for s in self.source_dirs)
        if self.global_output_dir:
            total_out_bytes = (
                get_dir_size_bytes(self.global_output_dir / f"Resized-{today_str}") +
                get_dir_size_bytes(self.global_output_dir / f"Animated-{today_str}") +
                get_dir_size_bytes(self.global_output_dir / f"Media-{today_str}")
            )
            out_loc_desc = str(self.global_output_dir)
        else:
            total_out_bytes = sum(
                get_dir_size_bytes(s / f"Resized-{today_str}") +
                get_dir_size_bytes(s / f"Animated-{today_str}") +
                get_dir_size_bytes(s / f"Media-{today_str}")
                for s in self.source_dirs
            )
            out_loc_desc = "Respective source folders"

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

    def __init__(self, source_dir_str: str, out_ext: str):
        super().__init__()
        self.source_dir = Path(source_dir_str)
        self.out_ext = out_ext
        self.is_aborted = False

    def abort(self):
        self.is_aborted = True

    def run(self):
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
            self.error_signal.emit("No valid first-level directories found to compress.")
            return

        sub_dirs.sort(key=lambda x: natural_sort_key(x.name))
        num_workers = max(1, os.cpu_count() - 1)

        manager = multiprocessing.Manager()
        worker_statuses = manager.dict()
        recent_logs = manager.list()
        for i in range(num_workers):
            worker_statuses[i] = {"tier": "-", "stage": "Idle", "name": "-", "progress": 0.0, "detail": ""}

        global_start_time = time.time()
        success_count = 0
        skip_count = 0
        done_total = 0

        pending_queue = list(sub_dirs)
        available_workers = set(range(num_workers))
        active_futures = {}

        try:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                while (pending_queue or active_futures) and not self.is_aborted:
                    done_futures = [f for f in active_futures if f.done()]
                    for f in done_futures:
                        worker_id = active_futures.pop(f)
                        available_workers.add(worker_id)
                        done_total += 1
                        try:
                            _, code = f.result()
                            if code == "SUCCESS": success_count += 1
                            else: skip_count += 1
                        except Exception:
                            skip_count += 1
                        self.progress_signal.emit(done_total, len(sub_dirs))

                    while available_workers and pending_queue and not self.is_aborted:
                        chosen_folder = pending_queue.pop(0)
                        worker_id = available_workers.pop()
                        f = executor.submit(
                            pack_folder_worker, str(chosen_folder), self.out_ext,
                            worker_id, worker_statuses, recent_logs, None
                        )
                        active_futures[f] = worker_id

                    self.worker_signal.emit(dict(worker_statuses))
                    self.log_signal.emit(list(recent_logs))
                    time.sleep(0.1)

                if self.is_aborted:
                    for p in executor._processes.values():
                        try: p.terminate()
                        except Exception: pass
        finally:
            pass

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

# ==================== Main Window GUI ====================
class DropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                self.setText(local_path)
                break

class DropListWidget(QListWidget):
    """支援直接拖曳多個資料夾加入清單的自訂 ListWidget"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                # 避免重複加入
                existing = [self.item(i).text() for i in range(self.count())]
                if local_path not in existing:
                    self.addItem(local_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Comic Optimizer & Fast Packer (macOS)")
        self.resize(1300, 880)
        self.setAcceptDrops(True)
        self.worker_thread = None
        self.num_workers = max(1, os.cpu_count() - 1)
        self.init_ui()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isdir(local_path):
                if self.tabs.currentIndex() == 0:
                    self.add_source_folder(local_path)
                else:
                    self.path_input_pack.setText(local_path)

    def add_source_folder(self, path_str: str):
        existing = [self.sources_list.item(i).text() for i in range(self.sources_list.count())]
        if path_str not in existing:
            self.sources_list.addItem(path_str)
        self.update_sources_count_label()

    def update_sources_count_label(self):
        cnt = self.sources_list.count()
        self.sources_count_label.setText(f"Sources Selected: {cnt}")

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
        layout_opt.setContentsMargins(8, 8, 8, 8)
        layout_opt.setSpacing(8)

        # 複數來源清單區
        src_box = QHBoxLayout()
        self.sources_list = DropListWidget()
        self.sources_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sources_list.setStyleSheet("QListWidget { font-size: 0.9rem; }")
        
        src_btn_layout = QVBoxLayout()
        add_src_btn = QPushButton("Add Folder...")
        add_src_btn.clicked.connect(self.browse_add_source)
        remove_src_btn = QPushButton("Remove")
        remove_src_btn.clicked.connect(self.remove_selected_source)
        clear_src_btn = QPushButton("Clear All")
        clear_src_btn.clicked.connect(self.clear_all_sources)
        self.sources_count_label = QLabel("Sources Selected: 0")
        self.sources_count_label.setStyleSheet("font-weight: bold; color: #38bdf8;")

        src_btn_layout.addWidget(add_src_btn)
        src_btn_layout.addWidget(remove_src_btn)
        src_btn_layout.addWidget(clear_src_btn)
        src_btn_layout.addStretch()
        src_btn_layout.addWidget(self.sources_count_label)

        src_box.addWidget(self.sources_list, stretch=4)
        src_box.addLayout(src_btn_layout, stretch=1)
        layout_opt.addLayout(src_box)

        # 輸出目的資料夾列 (可選)
        row_out = QHBoxLayout()
        self.path_output_opt = DropLineEdit()
        self.path_output_opt.setPlaceholderText("Output destination (Optional, leave empty to save into each source folder)...")
        browse_out_btn = QPushButton("Browse...")
        browse_out_btn.clicked.connect(lambda: self.browse_folder(self.path_output_opt))
        clear_out_btn = QPushButton("Clear")
        clear_out_btn.clicked.connect(lambda: self.path_output_opt.clear())
        row_out.addWidget(QLabel("Output:"))
        row_out.addWidget(self.path_output_opt, stretch=2)
        row_out.addWidget(browse_out_btn)
        row_out.addWidget(clear_out_btn)
        layout_opt.addLayout(row_out)

        # 控制與啟動列
        row_ctrl = QHBoxLayout()
        rec_ram = get_recommended_ram_disk_gb()
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(0, 128)
        self.ram_spin.setValue(rec_ram)
        self.ram_spin.setSuffix(" GB")

        self.strict_check = QCheckBox("Strict RAM")
        self.strict_check.setChecked(True)

        self.start_btn_opt = QPushButton("Start Optimizer")
        self.start_btn_opt.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px 16px;")
        self.start_btn_opt.clicked.connect(self.start_optimizer)

        row_ctrl.addWidget(QLabel("RAM Disk:"))
        row_ctrl.addWidget(self.ram_spin)
        row_ctrl.addWidget(self.strict_check)
        row_ctrl.addStretch()
        row_ctrl.addWidget(self.start_btn_opt)
        layout_opt.addLayout(row_ctrl)

        self.tabs.addTab(tab_opt, "Comic Optimizer (Multi-Source & Resize)")

        # ---- Tab 2: First-level Folder Store Packer ----
        tab_pack = QWidget()
        layout_pack = QHBoxLayout(tab_pack)
        layout_pack.setContentsMargins(8, 8, 8, 8)

        self.path_input_pack = DropLineEdit()
        self.path_input_pack.setPlaceholderText("Target folder whose subfolders will be packed to zip (zip -0 -r)...")
        browse_btn_pack = QPushButton("Browse...")
        browse_btn_pack.clicked.connect(lambda: self.browse_folder(self.path_input_pack))

        self.cbz_format_check = QCheckBox("Output .cbz instead of .zip")
        self.cbz_format_check.setChecked(False)

        self.start_btn_pack = QPushButton("Pack Subfolders")
        self.start_btn_pack.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 6px 14px;")
        self.start_btn_pack.clicked.connect(self.start_folder_packer)

        layout_pack.addWidget(QLabel("Target:"))
        layout_pack.addWidget(self.path_input_pack, stretch=2)
        layout_pack.addWidget(browse_btn_pack)
        layout_pack.addWidget(self.cbz_format_check)
        layout_pack.addWidget(self.start_btn_pack)
        self.tabs.addTab(tab_pack, "Quick Folder Packer (Store zip -0)")

        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(self.tabs, stretch=1)
        self.abort_btn = QPushButton("Abort")
        self.abort_btn.setEnabled(False)
        self.abort_btn.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; padding: 8px 18px;")
        self.abort_btn.clicked.connect(self.abort_processing)
        top_bar_layout.addWidget(self.abort_btn)
        main_layout.addLayout(top_bar_layout)

        prog_layout = QHBoxLayout()
        self.overall_progress = QProgressBar()
        self.overall_progress.setValue(0)
        self.status_label = QLabel("Idle")
        self.ram_usage_label = QLabel("RAM Disk: Disabled")
        prog_layout.addWidget(self.overall_progress, stretch=3)
        prog_layout.addWidget(self.status_label)
        prog_layout.addWidget(self.ram_usage_label)
        main_layout.addLayout(prog_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.worker_table = QTableWidget(self.num_workers, 5)
        self.worker_table.setHorizontalHeaderLabels(["Core", "Tier", "Stage", "Current Task", "Progress / Detail"])
        self.worker_table.verticalHeader().setVisible(False)
        self.worker_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.worker_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        w_header = self.worker_table.horizontalHeader()
        w_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.worker_table.setColumnWidth(0, 60)
        self.worker_table.setColumnWidth(1, 70)
        self.worker_table.setColumnWidth(2, 120)
        self.worker_table.setColumnWidth(3, 380)
        self.worker_table.setColumnWidth(4, 130)
        splitter.addWidget(self.worker_table)

        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["Status", "Target Name", "Stats"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        l_header = self.log_table.horizontalHeader()
        l_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.log_table.setColumnWidth(0, 90)
        self.log_table.setColumnWidth(1, 320)
        self.log_table.setColumnWidth(2, 120)
        splitter.addWidget(self.log_table)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        main_layout.addWidget(splitter, stretch=1)

        for i in range(self.num_workers):
            self.worker_table.setItem(i, 0, QTableWidgetItem(f"C{i+1:02d}"))
            self.worker_table.setItem(i, 1, QTableWidgetItem("-"))
            self.worker_table.setItem(i, 2, QTableWidgetItem("Idle"))
            self.worker_table.setItem(i, 3, QTableWidgetItem("-"))
            self.worker_table.setItem(i, 4, QTableWidgetItem("-"))

        self.ram_timer = QTimer(self)
        self.ram_timer.timeout.connect(self.update_ram_usage)
        self.ram_timer.start(1000)

    def browse_add_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Source Folder")
        if folder:
            self.add_source_folder(folder)

    def remove_selected_source(self):
        for item in self.sources_list.selectedItems():
            self.sources_list.takeItem(self.sources_list.row(item))
        self.update_sources_count_label()

    def clear_all_sources(self):
        self.sources_list.clear()
        self.update_sources_count_label()

    def browse_folder(self, target_line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            target_line_edit.setText(folder)

    def update_ram_usage(self):
        text, _ = get_ram_disk_usage()
        self.ram_usage_label.setText(f"RAM Disk: {text}")

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

        self.prepare_ui_for_start()
        self.worker_thread = OptimizerThread(
            source_dirs_list=source_dirs,
            global_output_dir_str=out_path,
            ram_gb=self.ram_spin.value(),
            strict_ram=self.strict_check.isChecked()
        )
        self.bind_and_start_thread()

    def start_folder_packer(self):
        folder_path = self.path_input_pack.text().strip()
        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Input Error", "Please provide a valid directory containing subfolders.")
            return

        out_ext = ".cbz" if self.cbz_format_check.isChecked() else ".zip"
        self.prepare_ui_for_start()
        self.worker_thread = FolderPackerThread(
            source_dir_str=folder_path,
            out_ext=out_ext
        )
        self.bind_and_start_thread()

    def prepare_ui_for_start(self):
        self.start_btn_opt.setEnabled(False)
        self.start_btn_pack.setEnabled(False)
        self.tabs.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.log_table.setRowCount(0)
        self.status_label.setText("Processing...")

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

    def on_progress(self, done: int, total: int):
        self.overall_progress.setMaximum(total)
        self.overall_progress.setValue(done)
        self.status_label.setText(f"{done}/{total} Completed")

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
                elif stage in ("Extracting", "Packing"):
                    stage_item.setForeground(QColor("#eab308"))
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
        display_logs = logs[-30:]
        self.log_table.setRowCount(len(display_logs))
        for row, item in enumerate(reversed(display_logs)):
            if isinstance(item, (tuple, list)) and len(item) == 3:
                tag, name, stat = item
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

                self.log_table.setItem(row, 0, status_item)
                self.log_table.setItem(row, 1, name_item)
                self.log_table.setItem(row, 2, stat_item)

    def on_error(self, message: str):
        QMessageBox.warning(self, "Error", message)
        self.reset_ui()

    def on_finished(self, summary: dict):
        self.reset_ui()
        mode = summary.get("mode")
        hrs, rem = divmod(int(summary["total_time"]), 3600)
        mins, secs = divmod(rem, 60)
        time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

        if mode == "optimizer":
            saved_bytes = summary["orig_bytes"] - summary["out_bytes"]
            saved_pct = (saved_bytes / summary["orig_bytes"] * 100) if summary["orig_bytes"] > 0 else 0.0
            msg = (
                f"Execution Time: {time_str}\n"
                f"Sources Processed: {summary['source_count']} directories\n"
                f"Files Completed: {summary['success']} OK / {summary['corrupted']} Corrupted / {summary['error']} Failed\n\n"
                f"Original Size: {format_bytes(summary['orig_bytes'])}\n"
                f"Optimized Size: {format_bytes(summary['out_bytes'])}\n"
                f"Space Saved: {format_bytes(max(0, saved_bytes))} (▼ {saved_pct:.1f}%)\n\n"
                f"Output Location:\n- {summary['out_loc']}"
            )
        else:
            msg = (
                f"Execution Time: {time_str}\n"
                f"Subfolders Packed: {summary['success']} OK / {summary['skipped']} Skipped\n\n"
                f"Target Location:\n- {summary['target_dir']}"
            )

        title = "Execution Aborted" if summary["aborted"] else "Processing Complete"
        QMessageBox.information(self, title, msg)

    def reset_ui(self):
        self.start_btn_opt.setEnabled(True)
        self.start_btn_pack.setEnabled(True)
        self.tabs.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.status_label.setText("Idle")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())