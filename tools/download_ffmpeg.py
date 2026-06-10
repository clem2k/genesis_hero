#!/usr/bin/env python3
"""
download_ffmpeg.py - Downloads a portable version of FFmpeg for Windows
and extracts it to genesis_tools/ffmpeg.exe.
"""

import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
PROJECT_DIR = Path(__file__).parent.parent.resolve()
GENESIS_TOOLS = PROJECT_DIR / "genesis_tools"
ZIP_PATH = GENESIS_TOOLS / "ffmpeg.zip"
FFMPEG_EXE = GENESIS_TOOLS / "ffmpeg.exe"


def download_and_extract_ffmpeg():
    os.makedirs(GENESIS_TOOLS, exist_ok=True)
    if FFMPEG_EXE.exists():
        print(f"[INFO] FFmpeg already exists at: {FFMPEG_EXE}")
        return True

    print(f"[INFO] Downloading portable FFmpeg from: {FFMPEG_URL}")
    print("[INFO] This might take a minute...")

    req = urllib.request.Request(
        FFMPEG_URL,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )

    try:
        with urllib.request.urlopen(req) as response, open(ZIP_PATH, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        print(f"[INFO] Downloaded: {ZIP_PATH}")
    except Exception as e:
        print(f"[ERROR] Failed to download FFmpeg: {e}")
        return False

    print(f"[INFO] Extracting ffmpeg.exe...")
    try:
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            # We want to find the ffmpeg.exe inside the zip and extract it to GENESIS_TOOLS / ffmpeg.exe
            found = False
            for member in zip_ref.namelist():
                if member.endswith("ffmpeg.exe"):
                    with zip_ref.open(member) as source, open(FFMPEG_EXE, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    print(f"[INFO] Extracted: {member} -> {FFMPEG_EXE}")
                    found = True
                    break
            if not found:
                print("[ERROR] ffmpeg.exe not found in zip file!")
                return False

        if FFMPEG_EXE.exists():
            print(f"[INFO] FFmpeg successfully set up at: {FFMPEG_EXE}")
            return True
        else:
            print("[ERROR] ffmpeg.exe not found after extraction!")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to extract FFmpeg: {e}")
        return False
    finally:
        if ZIP_PATH.exists():
            os.remove(ZIP_PATH)


if __name__ == '__main__':
    success = download_and_extract_ffmpeg()
    sys.exit(0 if success else 1)
