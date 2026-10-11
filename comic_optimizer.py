import os
import sys
import re
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
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
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

MAX_RAM_RETRIES = 3            # 暫時放不進 RAM 的最大重試次數，超過才迫降 SSD
RAM_DISK_MOUNT = Path("/Volumes/ComicRamDisk")

ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.cbz', '.cbr'}
STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'}
MEDIA_EXTS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg'
}

ARCHIVE_MAIN_EXT = '.cbz'
ARCHIVE_OTHER_EXT = '.zip'

SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
# =================================================


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


def calculate_dynamic_ram_disk_gb(num_workers: int) -> int:
    """
    激進型動態 RAM Disk 計算引擎：
    充分釋放 Apple Silicon 統一記憶體優勢，大幅拉高配額，避免大量檔案退回 SSD。
    """
    try:
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        total_ram_gb = mem_bytes / (1024 ** 3)

        vm = subprocess.check_output(["vm_stat"]).decode()
        page_size_match = re.search(r'page size of (\d+) bytes', vm)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096

        def get_pages(key):
            m = re.search(rf'{key}:\s+(\d+)\.', vm)
            return int(m.group(1)) if m else 0

        free_pages = get_pages("Pages free")
        inactive_pages = get_pages("Pages inactive")
        spec_pages = get_pages("Pages speculative")
        purgeable_pages = get_pages("Pages purgeable")
        
        # 實質可回收/可複寫空間（Free + Inactive + Speculative + Purgeable）
        available_gb = ((free_pages + inactive_pages + spec_pages + purgeable_pages) * page_size) / (1024 ** 3)

        # 激進策略：
        # 針對 24GB 機型：若當前非極端吃緊（可用 >= 6GB），直接配置 12GB ~ 14GB！
        if total_ram_gb >= 24.0:
            if available_gb >= 8.0:
                target_gb = 14
            elif available_gb >= 5.0:
                target_gb = 10
            else:
                target_gb = 6
        elif total_ram_gb >= 16.0:
            if available_gb >= 6.0:
                target_gb = 8
            elif available_gb >= 4.0:
                target_gb = 6
            else:
                target_gb = 4
        else:
            target_gb = max(2, int(available_gb * 0.6))

        return target_gb

    except Exception:
        return 8


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


def get_uncompressed_size_mb(archive_path: Path) -> float:
    """快速讀取壓縮檔未壓縮大小 (MB)"""
    ext = archive_path.suffix.lower()
    total_bytes = 0
    try:
        if ext in ('.zip', '.cbz'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                total_bytes = sum(zinfo.file_size for zinfo in zf.infolist())
        elif ext in ('.rar', '.cbr', '.7z'):
            res = subprocess.run(
                ["7z", "l", "-slt", str(archive_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            sizes = re.findall(r'^Size = (\d+)', res.stdout, re.MULTILINE)
            if sizes:
                parsed_sizes = [int(s) for s in sizes]
                total_bytes = max(parsed_sizes) if len(parsed_sizes) == 1 else sum(parsed_sizes[1:])
    except Exception:
        total_bytes = archive_path.stat().st_size * 2.0

    if total_bytes == 0:
        total_bytes = archive_path.stat().st_size * 2.0

    return total_bytes / (1024 * 1024)


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
            cmd = ["7z", "x", str(archive_path), f"-o{extract_dir}", "-y", "-bsp1"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

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


def create_zip_store(target_archive: Path, file_pairs: list):
    if not file_pairs:
        return
    target_archive.parent.mkdir(parents=True, exist_ok=True)
    file_pairs.sort(key=lambda x: natural_sort_key(x[1]))
    with zipfile.ZipFile(target_archive, 'w', compression=zipfile.ZIP_STORED) as zf:
        for disk_path, arc_name in file_pairs:
            zf.write(disk_path, arcname=arc_name)


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


def execute_pipeline(archive_path, comic_dir, anim_dir, media_dir, processed_dir, temp_target_dir, tier_tag, worker_id, status_dict):
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

        total_imgs = len(static_images)
        processed_images = []
        for idx, (img_path, rel_path) in enumerate(static_images):
            pct = 0.25 + (0.65 * ((idx + 1) / max(1, total_imgs)))
            status_dict[worker_id] = {
                "tier": tier_tag,
                "stage": "[magenta]影像轉檔[/magenta]",
                "name": archive_path.name,
                "progress": pct,
                "detail": f"{idx+1}/{total_imgs} 頁"
            }
            new_rel_path = str(Path(rel_path).with_suffix('.jpg'))
            out_img_path = processed_dir_tmp / f"img_{idx:05d}.jpg"
            try:
                resize_and_convert_image(img_path, out_img_path)
                processed_images.append((out_img_path, new_rel_path))
            except Exception:
                processed_images.append((img_path, rel_path))

        status_dict[worker_id] = {
            "tier": tier_tag,
            "stage": "[blue]快速封裝[/blue]",
            "name": archive_path.name,
            "progress": 0.95,
            "detail": "STORE 寫入"
        }
        if processed_images:
            create_zip_store(comic_dir / f"{stem_name}{ARCHIVE_MAIN_EXT}", processed_images)
        if animated_images:
            create_zip_store(anim_dir / f"{stem_name}-Animated{ARCHIVE_OTHER_EXT}", animated_images)
        if media_files:
            create_zip_store(media_dir / f"{stem_name}-Media{ARCHIVE_OTHER_EXT}", media_files)

    status_dict[worker_id] = {
        "tier": tier_tag,
        "stage": "[dim]移動歸檔[/dim]",
        "name": archive_path.name,
        "progress": 1.0,
        "detail": "搬移原檔"
    }
    safe_move_file(archive_path, processed_dir)
    return True, "SUCCESS", len(static_images)


def worker_task(
    archive_path_str: str,
    target_tier: str,
    reserved_mb: float,
    comic_dir_str: str,
    anim_dir_str: str,
    media_dir_str: str,
    processed_dir_str: str,
    error_dir_str: str,
    file_err_dir_str: str,
    worker_id: int,
    status_dict,
    recent_logs,
    ram_manager_tuple
):
    archive_path = Path(archive_path_str)
    comic_dir = Path(comic_dir_str)
    anim_dir = Path(anim_dir_str)
    media_dir = Path(media_dir_str)
    processed_dir = Path(processed_dir_str)
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
    try:
        ok, reason, img_count = execute_pipeline(
            archive_path, comic_dir, anim_dir, media_dir, processed_dir,
            temp_target_dir, tier_tag, worker_id, status_dict
        )

        if not ok and reason == "NO_SPACE" and temp_target_dir is not None:
            recent_logs.append(f"[bold yellow]⚠️ RAM Disk 突發空間不足，轉用 SSD: [/bold yellow]{archive_path.name}")
            tier_tag = "[yellow]SSD-重試[/yellow]"
            ok, reason, img_count = execute_pipeline(
                archive_path, comic_dir, anim_dir, media_dir, processed_dir,
                None, tier_tag, worker_id, status_dict
            )
            if not ok:
                safe_move_file(archive_path, error_dir)
                recent_logs.append(f"[bold red]❌ SSD 重試亦失敗 (已移至 Error): [/bold red]{archive_path.name}")
                status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
                return archive_path_str, "ERROR", 0

        elif not ok and reason in ("CORRUPTED", "NO_VALID_FILES"):
            safe_move_file(archive_path, file_err_dir)
            recent_logs.append(f"[bold red]❌ 檔案損毀/無法解壓 (已移至 FileErr): [/bold red]{archive_path.name}")
            status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "FILE_ERR", 0

        elif not ok:
            safe_move_file(archive_path, error_dir)
            recent_logs.append(f"[bold red]❌ 執行異常 (已移至 Error): [/bold red]{archive_path.name}")
            status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}
            return archive_path_str, "ERROR", 0

    finally:
        if target_tier == "RAM" and reserved_mb > 0:
            with ram_lock:
                current_allocated_ram.value = max(0.0, current_allocated_ram.value - reserved_mb)

    total_cost = time.time() - start_task_time
    recent_logs.append(f"[bold green]✔ 完成[/bold green] {archive_path.name} [dim]({total_cost:.1f}s, {img_count}P)[/dim]")
    status_dict[worker_id] = {"tier": tier_tag, "stage": "閒置", "name": "-", "progress": 0.0, "detail": "等待指派"}
    return archive_path_str, "SUCCESS", total_cost


def create_mini_bar(pct: float, width=12) -> str:
    pct = max(0.0, min(1.0, pct))
    filled = int(width * pct)
    empty = width - filled
    bar_str = "█" * filled + "░" * empty
    return f"[cyan]{bar_str}[/cyan] [bold white]{int(pct * 100):3d}%[/bold white]"


def build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active: bool, ram_disk_gb: int):
    worker_table = Table(box=box.SIMPLE, expand=True, pad_edge=False, show_header=True)
    worker_table.add_column("核心", style="bold cyan", width=7, justify="center")
    worker_table.add_column("層級", width=10, justify="center")
    worker_table.add_column("狀態", width=12, justify="center")
    worker_table.add_column("進度", width=18)
    worker_table.add_column("檔案名稱", style="white", ratio=1)
    worker_table.add_column("細節", style="dim", width=14, justify="right")

    for wid in range(num_workers):
        info = worker_statuses.get(wid, {
            "tier": "[dim]-[/dim]",
            "stage": "準備",
            "name": "-",
            "progress": 0.0,
            "detail": ""
        })
        short_name = info.get("name", "-")
        if len(short_name) > 36:
            short_name = short_name[:16] + "..." + short_name[-17:]

        stage_str = info.get("stage", "準備")
        stage_display = stage_str if "閒置" not in stage_str else "[dim]閒置[/dim]"

        worker_table.add_row(
            f"Core {wid+1:02d}",
            info.get("tier", "-"),
            stage_display,
            create_mini_bar(info.get("progress", 0.0)),
            short_name,
            info.get("detail", "")
        )

    logs_table = Table(box=box.SIMPLE, expand=True, show_header=False)
    logs_table.add_column("Log", ratio=1)
    display_logs = list(recent_logs)[-6:]
    if not display_logs:
        logs_table.add_row("[dim]尚無處理完成紀錄...[/dim]")
    else:
        for log in display_logs:
            logs_table.add_row(log)

    ram_usage_text, ram_pct = get_ram_disk_usage()
    ram_style = "bold red" if ram_pct > 85 else ("bold yellow" if ram_pct > 60 else "bold green")

    header_info = Text.assemble(
        ("  ⚡ 核心: ", "dim"), (f"{num_workers}C  ", "bold cyan"),
        ("│  💾 RAM Disk: ", "dim"), (f"{ram_disk_gb}GB ({ram_usage_text})  ", ram_style),
        ("│  ⌨️  中止熱鍵: ", "dim"), ("[bold red]連續輸入 qqq[/bold red]  ", "bold white"),
        ("│  ⚙️ 規格: ", "dim"), (f"4K STORE  ", "bold magenta"),
    )

    layout = Layout()
    layout.split_column(
        Layout(Panel(header_info, box=box.ROUNDED, style="on grey11"), size=3),
        Layout(Panel(progress, title="[bold cyan]總體任務進度[/bold cyan]", border_style="cyan"), size=4),
        Layout(name="body")
    )
    layout["body"].split_row(
        Layout(Panel(worker_table, title="[bold green]核心工作泳道[/bold green]", border_style="green"), ratio=7),
        Layout(Panel(logs_table, title="[bold white]近期動態[/bold white]", border_style="blue"), ratio=3)
    )
    return layout


def print_summary_card(
    console, total_time_sec, total_count, success_count, fail_err_count, corrupted_count,
    comic_dir, anim_dir, media_dir, processed_dir, error_dir, file_err_dir, file_err_stems, aborted=False
):
    processed_bytes = get_dir_size_bytes(processed_dir)
    comic_bytes = get_dir_size_bytes(comic_dir)
    anim_bytes = get_dir_size_bytes(anim_dir)
    media_bytes = get_dir_size_bytes(media_dir)

    output_total_bytes = comic_bytes + anim_bytes + media_bytes
    saved_bytes = processed_bytes - output_total_bytes
    pct_saved = (saved_bytes / processed_bytes * 100) if processed_bytes > 0 else 0.0

    hrs, rem = divmod(int(total_time_sec), 3600)
    mins, secs = divmod(rem, 60)
    time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
    done_count = success_count + corrupted_count + fail_err_count
    avg_per_file = (total_time_sec / max(1, done_count))

    summary_text = Text()
    if aborted:
        summary_text.append("⚠️  使用者已連續輸入 [qqq] 手動中止作業！已保存完成之進度。\n\n", style="bold red")

    summary_text.append(f"⏱️  總執行耗時: ", style="bold white")
    summary_text.append(f"{time_str}", style="bold cyan")
    summary_text.append(f" (平均 {avg_per_file:.1f} 秒/檔案)\n", style="dim")

    summary_text.append(f"📊 檔案結算: ", style="bold white")
    summary_text.append(f"共掃描 {total_count} 個 / 已處置 {done_count} 個", style="bold white")
    summary_text.append(f" (成功: ", style="dim")
    summary_text.append(f"{success_count}", style="bold green")
    summary_text.append(f", 損毀: ", style="dim")
    summary_text.append(f"{corrupted_count}", style="bold red" if corrupted_count > 0 else "dim")
    summary_text.append(f", 異常: ", style="dim")
    summary_text.append(f"{fail_err_count}", style="bold yellow" if fail_err_count > 0 else "dim")
    summary_text.append(f")\n\n", style="dim")

    summary_text.append(f"💾 空間節省統計:\n", style="bold yellow")
    summary_text.append(f"   • 已歸檔原檔體積 (Processed) : {format_bytes(processed_bytes)}\n", style="white")
    summary_text.append(f"   • 最佳化成品體積 (Comic+其他) : {format_bytes(output_total_bytes)}\n", style="white")
    if saved_bytes > 0:
        summary_text.append(f"   • 空間縮減 (節省容量)         : ", style="white")
        summary_text.append(f"{format_bytes(saved_bytes)} (▼ {pct_saved:.1f}%)\n", style="bold green")
    else:
        summary_text.append(f"   • 空間變化                    : 原圖尺寸較小或已為高度壓縮檔\n", style="dim")

    summary_text.append(f"\n📂 目錄產出狀態:\n", style="bold cyan")
    if comic_dir.exists():
        summary_text.append(f"   • 📖 漫畫書庫 : {comic_dir} ({format_bytes(comic_bytes)})\n", style="white")
    if anim_dir.exists():
        summary_text.append(f"   • 🎬 動態圖片 : {anim_dir} ({format_bytes(anim_bytes)})\n", style="white")
    if media_dir.exists():
        summary_text.append(f"   • 🎵 影音檔案 : {media_dir} ({format_bytes(media_bytes)})\n", style="white")
    if processed_dir.exists():
        summary_text.append(f"   • 📦 原檔歸檔 : {processed_dir} ({format_bytes(processed_bytes)})\n", style="white")
    
    if file_err_dir.exists() and corrupted_count > 0:
        list_file = file_err_dir / "corrupted_list.txt"
        try:
            sorted_stems = sorted(list(set(file_err_stems)), key=natural_sort_key)
            list_file.write_text("\n".join(sorted_stems), encoding="utf-8")
            summary_text.append(f"   • 🛑 損毀檔案 : {file_err_dir} ({corrupted_count} 個損毀檔)\n", style="bold red")
            summary_text.append(f"     └─ 📑 清單已儲存至: {list_file.name} (無副檔名)\n", style="dim")
        except Exception:
            summary_text.append(f"   • 🛑 損毀檔案 : {file_err_dir} ({corrupted_count} 個損毀檔)\n", style="bold red")

    if error_dir.exists() and fail_err_count > 0:
        summary_text.append(f"   • ⚠️ 執行異常 : {error_dir} ({fail_err_count} 個檔案)\n", style="bold yellow")

    card_title = "[bold red]🛑 任務中止結算報告 (Aborted)[/bold red]" if aborted else "[bold green]🎉 處理成果結算報告 (Summary Report)[/bold green]"
    border_style = "red" if aborted else "green"
    console.print(Panel(summary_text, title=card_title, border_style=border_style, expand=False))


def main():
    console = Console()

    if len(sys.argv) < 2:
        src_folder = console.input("[bold yellow]請輸入包含壓縮檔的資料夾路徑: [/bold yellow]").strip()
    else:
        src_folder = sys.argv[1].strip()

    source_dir = Path(src_folder).expanduser().resolve()
    if not source_dir.is_dir():
        console.print(f"[bold red]❌ 錯誤：路徑不存在：{source_dir}[/bold red]")
        sys.exit(1)

    today_str = datetime.now().strftime("%Y-%m-%d")
    comic_dir = source_dir / f"Comic-{today_str}"
    anim_dir = source_dir / f"Animated-{today_str}"
    media_dir = source_dir / f"Media-{today_str}"
    processed_dir = source_dir / f"Processed-{today_str}"
    error_dir = source_dir / f"Error-{today_str}"
    file_err_dir = source_dir / f"FileErr-{today_str}"

    output_dir_names = {
        comic_dir.name, anim_dir.name, media_dir.name,
        processed_dir.name, error_dir.name, file_err_dir.name
    }
    archive_files = [
        p for p in source_dir.rglob("*")
        if p.is_file() 
        and p.suffix.lower() in ARCHIVE_EXTENSIONS 
        and not p.name.startswith("._")
        and not any(part in output_dir_names for part in p.parts)
    ]

    if not archive_files:
        console.print("[yellow]未找到任何待處理的壓縮檔案（可能已全數歸檔）。[/yellow]")
        return

    num_workers = max(1, os.cpu_count() - 1)

    # 1. 激進型動態評估安全 RAM Disk 大小 (在 24GB 上配置 10~14GB)
    console.print("[cyan]🔍 正在評估系統可用記憶體（激進釋放模式）...[/cyan]")
    dynamic_ram_gb = calculate_dynamic_ram_disk_gb(num_workers)
    ram_path = setup_ram_disk(dynamic_ram_gb)
    ram_active = ram_path is not None

    if ram_active:
        console.print(f"[bold green]✔ 已配置高容量 {dynamic_ram_gb} GB RAM Disk，啟動激進型記憶體排程！[/bold green]")
    else:
        console.print("[yellow]⚠ 系統可用記憶體緊張，將全面使用系統 SSD 進行暫存。[/yellow]")

    # 2. 空間記帳員狀態
    manager = multiprocessing.Manager()
    worker_statuses = manager.dict()
    recent_logs = manager.list()
    file_err_stems = manager.list()
    for i in range(num_workers):
        worker_statuses[i] = {"tier": "[dim]-[/dim]", "stage": "閒置", "name": "-", "progress": 0.0, "detail": ""}

    # RAM 記帳員：保留 10% 空間餘量即可（極大化利用）
    ram_budget_mb = (dynamic_ram_gb * 1024 * 0.90) if ram_active else 0.0
    current_allocated_ram = manager.Value('d', 0.0)
    ram_lock = manager.Lock()
    ram_manager_tuple = (current_allocated_ram, ram_budget_mb, ram_lock)

    # 3. 檔案前置預檢
    console.print("[cyan]📑 正在進行檔案展開尺寸預檢...[/cyan]")
    pending_queue = []
    for arch in archive_files:
        uncompressed_mb = get_uncompressed_size_mb(arch)
        pending_queue.append({
            "path": arch,
            "uncompressed_mb": uncompressed_mb,
            "retries": 0
        })

    # 大小穿插交錯排序
    pending_queue.sort(key=lambda x: x["uncompressed_mb"], reverse=True)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
    )
    task_id = progress.add_task("壓縮檔排程 (可隨時輸入 qqq 中止)...", total=len(archive_files))

    # 啟動 qqq 鍵盤監聽器
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
            build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active, dynamic_ram_gb),
            refresh_per_second=4,
            console=console
        ) as live:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                while (pending_queue or active_futures) and not was_aborted:
                    # 檢查使用者是否連續輸入 qqq
                    if abort_listener.aborted:
                        was_aborted = True
                        recent_logs.append("[bold red]🛑 接收到 qqq 中止指令，正在強制停止工作核心...[/bold red]")
                        # 中止所有執行中 Worker
                        for p in executor._processes.values():
                            try:
                                p.terminate()
                            except Exception:
                                pass
                        break

                    # 收集已完成的任務
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

                    # 派發新任務
                    while available_workers and pending_queue and not was_aborted:
                        if abort_listener.aborted:
                            was_aborted = True
                            break

                        assigned = False
                        for idx, item in enumerate(pending_queue):
                            needed_mb = item["uncompressed_mb"]
                            
                            # 判定 1: 物理上超越整顆 RAM Disk 總額度
                            if not ram_active or needed_mb > ram_budget_mb:
                                target_tier = "SSD"
                                reserved_mb = 0.0
                                chosen_item = pending_queue.pop(idx)
                                assigned = True
                                break

                            # 判定 2: 向記帳員申請空間
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
                                str(comic_dir),
                                str(anim_dir),
                                str(media_dir),
                                str(processed_dir),
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
                        build_enhanced_dashboard(progress, worker_statuses, recent_logs, num_workers, ram_active, dynamic_ram_gb)
                    )
                    time.sleep(0.1)

    finally:
        abort_listener.stop()
        console.print("\n[cyan]🧹 正在安全卸載 RAM Disk...[/cyan]")
        cleanup_ram_disk()

    global_cost = time.time() - global_start_time

    # 印出成果結算報告卡片（含手動中止標記）
    print_summary_card(
        console,
        global_cost,
        len(archive_files),
        success_count,
        fail_err_count,
        corrupted_count,
        comic_dir,
        anim_dir,
        media_dir,
        processed_dir,
        error_dir,
        file_err_dir,
        file_err_stems,
        aborted=was_aborted
    )


if __name__ == "__main__":
    main()