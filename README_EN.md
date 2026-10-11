# Comic Optimizer (4K Comic & Image Archive Batch Converter)

A high-performance batch image conversion and archive repackaging tool tailored for macOS (Apple Silicon M-series optimized) and modern digital comic readers such as YACReader.
Features interactive RAM Disk setup, strict RAM mode scheduling, parallel pre-flight uncompressed size inspection, dynamic 7zz/7z binary detection, dynamic/static content separation, dual-tier error isolation, instant keyboard abort (qqq), post-process savings analysis, and automated E-Hentai search navigation generation.

---

## Key Features

1. Interactive RAM Disk Setup & Strict RAM Mode:
   - Evaluates system memory and suggests an optimal RAM Disk allocation upon launch, with full manual override support (enter 0 to use local SSD only).
   - Introduces "Strict RAM Mode" (enabled by default): tasks yield and wait for active workers to return memory quota instead of falling back to SSD, minimizing storage wear.

2. Parallel Pre-flight Size Inspection:
   - Uses multi-threaded ThreadPool scanning to inspect archive headers concurrently (native memory inspection for ZIP/CBZ; compact command output for RAR/7Z).
   - Features real-time Rich progress tracking with active file display, processing hundreds of archives in seconds.

3. Dynamic 7-Zip Binary Detection (7zz / 7z):
   - Automatically probes for the standalone `7zz` binary (Homebrew default) or `7z`, injecting `-p-` flags to bypass password prompts and prevent RAR/CBR files from falsely landing in FileErr.

4. Instant Keyboard Abort (Graceful Abort via qqq):
   - Listens for terminal keyboard input in the background; typing qqq consecutively triggers an immediate, safe abort.
   - Stops dispatching new jobs, terminates active worker processes, records processed file statistics, and cleanly unmounts the RAM Disk.

5. Dual-Tier Error Isolation & E-Hentai Navigation Export:
   - FileErr-YYYY-MM-DD/: Isolates corrupted archives, CRC check failures, password-protected files, or archives with no valid media content.
   - Automatically exports corrupted_list.txt (clean filenames without extensions).
   - Generates corrupted_search.html: sanitizes titles (removes page counts, AI tags, brackets) and builds a dark-mode interactive navigation table for one-click E-Hentai searching.
   - Error-YYYY-MM-DD/: Isolates runtime/system execution exceptions.

6. Historical Directory Skipping:
   - Automatically excludes output folders from previous runs (e.g., Resized-*, FileErr-*, Processed-*) to prevent duplicate recursive processing.

7. 4K Optimization & YACReader Compatibility:
   - Re-encodes static images into high-compatibility JPEG (Quality 85, Lanczos resampling) capped at 4K resolution (3840 x 2160).
   - Packs images using natural alphanumeric filename ordering with ZIP_STORED (uncompressed store mode) into .cbz files, enabling zero-latency page flips and rapid thumbnail caching.

8. Summary & Savings Report:
   - Generates a post-process breakdown comparing original archive volume against converted output volume, detailing exact storage saved (GB) and compression percentage.
   - Reports total execution time, processed file count, and average turnaround time per archive.

---

## System Requirements

- Operating System: macOS (Apple Silicon M-series recommended)
- Python Version: Python 3.9+ (pre-installed macOS Python is fully compatible)
- System Tool: 7-Zip (required for RAR, CBR, and 7Z archives)

---

## Installation

### Step 1: Install 7-Zip via Homebrew
Run the following command in Terminal:
brew install sevenzip

(Verify the installation with: which 7zz or which 7z)

### Step 2: Install Python Dependencies
Install via requirements.txt:
pip3 install --user -r requirements.txt

Or install directly:
pip3 install --user Pillow rich tqdm

---

## Usage

### Option 1: Pass Directory via CLI Argument
python3 comic_optimizer.py "/Users/your_name/Downloads/Comics"

### Option 2: Interactive Prompt (Drag & Drop Supported)
Run the script directly:
python3 comic_optimizer.py

1. Drag and drop the target directory into the terminal.
2. Confirm or adjust the RAM Disk capacity (press Enter for the default recommended size).
3. Choose whether to enable Strict RAM Mode (press Enter to accept default: Y).

### Aborting During Execution
Type qqq consecutively at any time in the terminal to safely stop the process and generate the summary report.

---

## Directory Output Structure

Upon completion, output subdirectories are generated within the source directory:

Source_Directory/
├── Resized-YYYY-MM-DD/      # Processed 4K .cbz comic library
│   └── OnePiece_105.cbz
├── Animated-YYYY-MM-DD/     # Extracted animated WebP / GIF files (on demand)
│   └── Title-Animated.zip
├── Media-YYYY-MM-DD/        # Extracted video and audio tracks (on demand)
│   └── Title-Media.zip
├── Processed-YYYY-MM-DD/    # Successfully processed original source archives
│   └── OnePiece_105.zip
├── FileErr-YYYY-MM-DD/      # Corrupted / CRC failed / password-protected archives
│   ├── corrupted_list.txt   # Plain list of corrupted filenames without extensions
│   └── corrupted_search.html# Interactive E-Hentai search table for recovery
└── Error-YYYY-MM-DD/        # System / runtime execution errors

---

## FAQ

- Q: What happens if processing is interrupted (via qqq or closing the terminal)?
  - The script immediately catches the abort signal, saves the progress of files completed so far, and safely unmounts the RAM Disk.
  - Since unprocessed archives remain in the source folder, re-running the script will automatically resume remaining tasks.

- Q: When are files moved to FileErr instead of Error?
  - Broken archive headers, CRC mismatches, extraction corruptions, and password-protected files are routed directly to FileErr, generating corrupted_list.txt and corrupted_search.html.