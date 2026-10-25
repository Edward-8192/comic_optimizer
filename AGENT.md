# Comic Optimizer & Fast Packer - Project Context & Rules

## 1. Project Overview
A high-performance comic/manga optimizer and folder packer built for macOS (Apple Silicon).
- Technologies: Python 3.11+, PyQt6, Pillow, 7zz (CLI binary), multiprocessing, concurrent.futures.

## 2. Core Architecture Rules (DO NOT BREAK)
1. **Multiprocessing Safety**:
   - macOS uses `spawn` start method. Always keep `multiprocessing.freeze_support()` in `__main__` for PyInstaller compatibility.
   - Heavy tasks must run in `QThread` via `ProcessPoolExecutor` to prevent freezing the GUI.
2. **CPU Token Pool (Atomic Token Management)**:
   - System cores must be managed atomically via `cpu_token_manager` to prevent over-subscription when multiple workers resize images simultaneously.
   - Dynamic micro-batching (`CHUNK_SIZE = 24`) borrows idle cores dynamically.
3. **Storage Tiering (RAM Disk Accountant)**:
   - Tracks allocations with `Manager.Value` and `Lock`. Strict RAM mode waits instead of spilling to SSD.
4. **Directory Isolation**:
   - Never scan or re-pack directories starting with `SYSTEM_DIR_PREFIXES` (`OriginalFiles-`, `Resized-`, `FileErr-`, etc.).
   - Archived original files must always stay in their original source folder under `OriginalFiles-YYYY-MM-DD`.
5. **Zero-I/O Pre-flight**:
   - Use Central Directory for ZIP/CBZ and `size * 1.2` estimation for RAR/7Z to prevent disk thrashing.

## 3. Active Goal
- Refine GUI experience, maintain cross-drive multi-source routing, and package into a standalone macOS `.app` bundle via PyInstaller.