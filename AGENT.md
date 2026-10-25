# Comic Optimizer & Fast Packer - Project Context & Rules

## 1. Project Overview
A high-performance comic/manga archive optimizer and folder packer built for macOS (Apple Silicon).
- **Technologies**: Python 3.11+ (`.venv`), PyQt6, Pillow, `7zz` (CLI binary from Homebrew `sevenzip`), `sqlite3`, `multiprocessing`, `concurrent.futures`.
- **Entry Point**: `comic_optimizer_gui.py`
- **Assets**: `7zz` (bundled CLI binary), `app_icon.png` & `app_icon.icns` (macOS Apple-style squircle icons).

## 2. Core Architecture Rules (DO NOT BREAK)
1. **Multiprocessing & System Stability**:
   - macOS uses the `spawn` start method. Always keep `multiprocessing.freeze_support()` and `multiprocessing.set_start_method("spawn", force=True)` in `__main__` for PyInstaller compatibility.
   - Reserve 1 physical/logical CPU core for macOS, the GUI main thread, and the Multiprocessing Manager (`num_workers = max(1, os.cpu_count() - 1)`).
   - Heavy tasks must run in `QThread` (`OptimizerThread`, `FolderPackerThread`) via `ProcessPoolExecutor` to prevent freezing the GUI.
2. **CPU Token Pool (Atomic Token Management)**:
   - System cores are managed atomically via `cpu_token_manager = (allocated_cpu_tokens, cpu_token_lock)` to prevent CPU over-subscription when multiple workers resize images simultaneously.
   - Dynamic micro-batching (`CHUNK_SIZE = 24`) borrows cores from both `"Idle"` and `"Queued I/O"` workers dynamically.
3. **Write-Priority Disk I/O Gatekeeper & Just-In-Time Stream Dispatch**:
   - External drives / RAID arrays (e.g., QNAP TR-002) suffer severe seek thrashing if all workers read/write simultaneously. Concurrent disk streams are controlled by `io_controller = (active_io_streams, waiting_writers, io_lock, io_limit)`.
   - **Write-Priority (`waiting_writers`)**: Tasks that have finished assembling `.cbz`/`.zip` in `RAM Disk` (`Priority Flush` / `Archiving`) always take priority over new `Extracting` tasks so finished files immediately leave the RAM Disk and free space.
   - **Just-In-Time Stream Dispatch**: The dispatcher in `OptimizerThread.run` caps concurrent initial readers (`active_readers < self.io_limit`) and pauses new dispatches when `waiting_writers.value > 0`, preventing idle queued tasks from pre-locking RAM Disk budget.
4. **Zero-Inflation RAM Disk Pipeline & Strict RAM Enforcement**:
   - **Rolling Unlink (In-place Consumption)**:
     - `_process_single_page_task` unlinks the source image in `extracted/` immediately after saving the resized JPEG to `processed/`.
     - `create_zip_store(..., consume_source=True)` unlinks each file in `processed/` or `extracted/` immediately after writing it to the staged `.cbz`/`.zip` in `staged_out/`, then removes `extracted/` and `processed/`.
     - Single-task peak footprint on RAM Disk never exceeds `~1.0x` uncompressed size.
   - **Dual-Check Strict RAM**:
     - Checks both `current_allocated_ram` budget and real physical free space (`get_ram_disk_free_mb()`).
     - When `strict_ram=True`, `NO_SPACE` must **never** silently fall back to SSD; instead it cleans up the temp directory, releases reserved RAM, and returns `"RETRY_RAM"` to re-queue at the head of `pending_queue` (falling back to SSD only if a single archive fails 3 times because its individual size exceeds the entire RAM Disk).
5. **Directory Isolation & Wrapper Folder Rules**:
   - Never scan or re-pack directories starting with `SYSTEM_DIR_PREFIXES` (`Resized-`, `Comic-`, `Animated-`, `Media-`, `OriginalFiles-`, `Processed-`, `FileErr-`, `Error-`).
   - Archived original files must always stay in their original source folder under `OriginalFiles-YYYY-MM-DD`.
   - `create_zip_store` must wrap files under `root_folder_name` whenever `root_folder_name` is specified (unless all files already share a single top-level directory named `root_folder_name`).
6. **Zero-I/O Pre-flight & CJK Log Safety**:
   - Use Central Directory for `.zip`/`.cbz` (`* 1.08` safety buffer) and `size * 1.30` estimation for `.rar`/`.cbr`/`.7z`.
   - `sanitize_log_text` must only strip supplementary-plane colorful emojis (`U+1F1E0..U+1FAFF`) and must preserve all CJK characters, Kana, and full-width punctuation.
7. **Persistence & UI/UX**:
   - Settings (`config.json`) and all-time history (`history.db` via `HistoryDatabase`) are stored in `~/Library/Application Support/ComicOptimizer/` (with automatic fallback to `tempfile.gettempdir() / "ComicOptimizer"` in restricted sandboxes).
   - `on_log_update` uses incremental row insertion (`_rendered_log_count`) with scroll-position preservation so all files processed in a session remain scrollable without UI stutter.
