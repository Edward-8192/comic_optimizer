# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# 1. 確保 7zz 與 unar 正確打包至 App 根目錄
# 若有圖示圖檔 (如 app_icon.icns 或 app_icon.png)，也建議一併放入
datas = [
    ('7zz', '.'),
    ('unar', '.'),
]

# 若專案目錄下有圖示檔，一併納入內部資源
if os.path.exists('app_icon.png'):
    datas.append(('app_icon.png', '.'))
if os.path.exists('app_icon.icns'):
    datas.append(('app_icon.icns', '.'))

a = Analysis(
    ['comic_optimizer_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PIL._imaging',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ComicOptimizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ComicOptimizer',
)

# 判斷是否有 icns 圖示
app_icon_path = 'app_icon.icns' if os.path.exists('app_icon.icns') else None

app = BUNDLE(
    coll,
    name='ComicOptimizer.app',
    icon=app_icon_path,
    bundle_identifier='com.comicoptimizer.app',
    info_plist={
        'CFBundleDisplayName': 'Comic Optimizer',
        'CFBundleName': 'ComicOptimizer',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleIconFile': 'app_icon.icns' if app_icon_path else None,
        'NSHighResolutionCapable': 'True',
        'LSBackgroundOnly': 'False',
        'NSRequiresAquaSystemAppearance': 'False',
    },
)