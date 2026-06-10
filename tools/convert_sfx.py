#!/usr/bin/env python3
"""
convert_sfx.py - Convert sound effects from MP3 to Mega Drive compatible WAV.

Converts files in snd/ to res/snd/ downsampling them to mono, 8-bit unsigned PCM
at 14kHz.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def check_ffmpeg(project_dir):
    """Locate FFmpeg executable."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    local_ffmpeg = Path(project_dir) / "genesis_tools" / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    return None


def main():
    project_dir = Path(__file__).parent.parent.resolve()
    snd_dir = project_dir / "snd"
    res_snd_dir = project_dir / "res" / "snd"

    if not snd_dir.exists():
        print(f"[ERROR] Source sound directory not found: {snd_dir}")
        sys.exit(1)

    res_snd_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_bin = check_ffmpeg(project_dir)
    if not ffmpeg_bin:
        print("[ERROR] FFmpeg not found! Please make sure it is in PATH or genesis_tools/ffmpeg.exe")
        sys.exit(1)

    mp3_files = list(snd_dir.glob("*.mp3"))
    if not mp3_files:
        print(f"[WARNING] No MP3 files found in {snd_dir}")
        sys.exit(0)

    print("=" * 60)
    # Check if directory exists
    print(f"[INFO] Converting {len(mp3_files)} MP3 file(s) to Mega Drive WAV...")
    print("=" * 60)

    success_count = 0
    for mp3_path in mp3_files:
        wav_path = res_snd_dir / f"{mp3_path.stem}.wav"
        print(f"[INFO] Processing: {mp3_path.name}")

        # Convert to: PCM 8-bit unsigned, 14000Hz sample rate, mono
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(mp3_path),
            "-acodec", "pcm_u8",
            "-ar", "14000",
            "-ac", "1",
            str(wav_path)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"[INFO]   Saved to: {wav_path.relative_to(project_dir)}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"[ERROR]   Failed to convert {mp3_path.name}:")
            if e.stderr:
                print(e.stderr)

    print()
    print("=" * 60)
    print(f"[INFO] Conversion complete! ({success_count}/{len(mp3_files)} successful)")
    print("=" * 60)


if __name__ == "__main__":
    main()
