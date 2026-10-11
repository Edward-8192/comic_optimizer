# Comic Optimizer (4K Comic & Image Archive Batch Converter)

A high-performance batch image conversion and archive repackaging tool tailored for macOS (Apple Silicon M-series optimized) and modern digital comic readers such as YACReader.
Features aggressive dynamic RAM Disk sizing, zero-I/O pre-flight uncompressed size inspection, token-based RAM admission control, smart re-queue scheduling, dynamic/static content separation, dual-tier error isolation, instant keyboard abort (qqq), and post-process savings analysis.

---

## Key Features

1. Aggressive Dynamic RAM Allocation (Aggressive RAM Sizing):
   - Analyzes real-time available system memory (including Free, Inactive, Speculative, and Purgeable) via sysctl and vm_stat upon startup.
   - Fully utilizes Apple Silicon unified memory by allocating 10GB–14GB RAM Disk on 24GB machines, significantly reducing SSD wear and unnecessary fallbacks.

2. Instant Keyboard Abort (Graceful Abort via qqq):
   - Actively monitors keyboard input in the background; pressing qqq consecutively triggers an immediate, safe abort.
   - Stops dispatching new jobs, terminates active worker processes, records processed file statistics, and cleanly unmounts the RAM Disk.

3. Zero-I/O Pre-flight Inspection:
   - Inspects archive headers prior to extraction (infolist for ZIP/CBZ; 7z l for 7z/RAR) to calculate total uncompressed payload size in milliseconds.
   - Eliminates wasted CPU cycles and I/O overhead caused by running out of disk space midway through extraction.

4. RAM Admission Controller:
   - Implements a cross-process shared allocation accounting lock. Workers must acquire a sufficient memory quota before writing to the RAM Disk.
   - Quotas are automatically reclaimed upon temporary resource cleanup, keeping RAM Disk utilization high without overflow.

5. Dynamic Re-queue Scheduling:
   - Automatically defers archives back to the task queue when temporary memory quotas are exhausted, prioritizing smaller archives to maintain CPU throughput.
   - Falls back to local SSD storage once an archive exceeds retry thresholds (default: 3) or when its uncompressed payload physically exceeds total RAM Disk capacity.

6. Dual-Tier Error Isolation & Corrupted File Export:
   - FileErr-YYYY-MM-DD/: Isolates corrupted archives, CRC check failures, password-protected files, or archives with no valid media content. Automatically exports corrupted_list.txt (plain filenames without extensions).
   - Error-YYYY-MM-DD/: Isolates runtime/system execution exceptions.
   - Successfully processed archives are moved to Processed-YYYY-MM-DD/, ensuring the source directory is completely cleared and providing native resume capabilities.

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
- System Tool: 7z (required for RAR, CBR, and 7Z archives)

---

## Installation

### Step 1: Install 7-Zip via Homebrew
Run the following command in Terminal:
brew install sevenzip

(Verify the installation path with: which 7z)

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

When prompted, drag and drop your target folder from Finder (local drive, external SSD, or a mounted SMB network share under /Volumes/...) into the Terminal window and press Enter.

### Aborting During Execution
Type qqq consecutively at any time in the terminal to safely stop the process and generate the summary report.

---

## Directory Output Structure

Upon completion, output subdirectories are generated within the source directory:

Source_Directory/
├── Comic-YYYY-MM-DD/        # Processed 4K .cbz comic library
│   └── OnePiece_105.cbz
├── Animated-YYYY-MM-DD/     # Extracted animated WebP / GIF files (on demand)
│   └── Title-Animated.zip
├── Media-YYYY-MM-DD/        # Extracted video and audio tracks (on demand)
│   └── Title-Media.zip
├── Processed-YYYY-MM-DD/    # Successfully processed original source archives
│   └── OnePiece_105.zip
├── FileErr-YYYY-MM-DD/      # Corrupted / CRC failed / password-protected archives
│   └── corrupted_list.txt  # Clean list of corrupted filenames without extensions
└── Error-YYYY-MM-DD/        # System / runtime execution errors

---

## Scheduling & Tiering Pipeline

Scan Archives ➔ Zero-I/O Header Size Inspection
    │
    ├── Payload Exceeds RAM Disk Capacity ─────────> Route to Local SSD
    │
    └── Payload Within RAM Disk Capacity
            │
            ├── Admission Controller Approves ──────> Execute in RAM Disk (Zero SSD Wear)
            │
            └── Admission Controller Exhausted
                    │
                    ├── Retries < 3 ───────────────> Re-queue (Yield to Smaller Archives)
                    └── Retries >= 3 ──────────────> Fallback to Local SSD

---

## FAQ

- Q: What happens if processing is interrupted (via qqq or closing the terminal)?
  - The script immediately catches the abort signal, saves the progress of files completed so far, and safely unmounts the RAM Disk.
  - Since unprocessed archives remain in the source folder, re-running the script will automatically resume remaining tasks.

- Q: When are files moved to FileErr instead of Error?
  - Broken archive headers, CRC mismatches, extraction corruptions, and password-protected files are routed directly to FileErr, and their filenames without extensions are logged into corrupted_list.txt.