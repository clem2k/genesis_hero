#!/usr/bin/env python3
"""
audio_splitter.py - Audio stem separation using Demucs for Genesis Hero pipeline.

Splits audio files into stems (vocals/instrumental, or drums/bass/other)
using the Demucs CLI for reliable separation.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def split_two_stems(mp3_path, output_dir):
    """
    Run Demucs 2-stem separation (vocals vs instrumental).

    Args:
        mp3_path: Path to input MP3 file.
        output_dir: Directory where Demucs will write output.

    Returns:
        Path to the no_vocals.wav file (instrumental).
    """
    mp3_path = Path(mp3_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not mp3_path.exists():
        print(f"[ERROR] Input file not found: {mp3_path}")
        return None

    print(f"[INFO] Running 2-stem separation on: {mp3_path.name}")
    print(f"[INFO] Output directory: {output_dir}")

    code_str = (
        "import soundfile; import torchaudio; "
        "torchaudio.save = lambda uri, src, sample_rate, channels_first=True, **kwargs: "
        "soundfile.write(uri, src.cpu().t().numpy() if channels_first else src.cpu().numpy(), sample_rate); "
        "from demucs.separate import main; main()"
    )
    cmd = [
        sys.executable,
        "-c",
        code_str,
        "--two-stems=vocals",
        "-n", "htdemucs",
        "-o", str(output_dir),
        str(mp3_path)
    ]

    try:
        print(f"[INFO] Command: {' '.join(cmd)}")
        env = os.environ.copy()
        scripts_dir = os.path.dirname(sys.executable)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env
        )
        if result.stdout:
            print(f"[INFO] Demucs output:\n{result.stdout}")
    except FileNotFoundError:
        print("[ERROR] Demucs CLI not found. Install with: pip install demucs")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Demucs failed with return code {e.returncode}")
        if e.stderr:
            print(f"[ERROR] stderr: {e.stderr}")
        return None

    # Demucs creates: output_dir/htdemucs/<track_name>/no_vocals.wav
    track_name = mp3_path.stem
    no_vocals_path = output_dir / "htdemucs" / track_name / "no_vocals.wav"

    if not no_vocals_path.exists():
        # Try to find it with a search
        print(f"[INFO] Expected path not found: {no_vocals_path}")
        print("[INFO] Searching for no_vocals.wav in output directory...")
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f == "no_vocals.wav":
                    no_vocals_path = Path(root) / f
                    print(f"[INFO] Found: {no_vocals_path}")
                    break

    if no_vocals_path.exists():
        print(f"[INFO] 2-stem separation complete: {no_vocals_path}")
        return no_vocals_path
    else:
        print("[ERROR] no_vocals.wav not found after Demucs separation")
        return None


def split_multi_stems(wav_path, output_dir):
    """
    Run Demucs multi-stem separation on an instrumental WAV.

    Args:
        wav_path: Path to input WAV file (typically the instrumental/no_vocals).
        output_dir: Directory where Demucs will write output.

    Returns:
        Dict with paths: {'drums': path, 'bass': path, 'other': path}
        or None on failure.
    """
    wav_path = Path(wav_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not wav_path.exists():
        print(f"[ERROR] Input file not found: {wav_path}")
        return None

    print(f"[INFO] Running multi-stem separation on: {wav_path.name}")
    print(f"[INFO] Output directory: {output_dir}")

    code_str = (
        "import soundfile; import torchaudio; "
        "torchaudio.save = lambda uri, src, sample_rate, channels_first=True, **kwargs: "
        "soundfile.write(uri, src.cpu().t().numpy() if channels_first else src.cpu().numpy(), sample_rate); "
        "from demucs.separate import main; main()"
    )
    cmd = [
        sys.executable,
        "-c",
        code_str,
        "-n", "htdemucs",
        "-o", str(output_dir),
        str(wav_path)
    ]

    try:
        print(f"[INFO] Command: {' '.join(cmd)}")
        env = os.environ.copy()
        scripts_dir = os.path.dirname(sys.executable)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env
        )
        if result.stdout:
            print(f"[INFO] Demucs output:\n{result.stdout}")
    except FileNotFoundError:
        print("[ERROR] Demucs CLI not found. Install with: pip install demucs")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Demucs failed with return code {e.returncode}")
        if e.stderr:
            print(f"[ERROR] stderr: {e.stderr}")
        return None

    # Demucs creates: output_dir/htdemucs/<track_name>/{drums,bass,other,vocals}.wav
    track_name = wav_path.stem
    stems_base = output_dir / "htdemucs" / track_name

    stem_names = ["drums", "bass", "other"]
    stems = {}

    for stem in stem_names:
        stem_path = stems_base / f"{stem}.wav"
        if not stem_path.exists():
            # Search for it
            print(f"[INFO] Expected stem not found: {stem_path}")
            found = False
            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    if f == f"{stem}.wav":
                        stem_path = Path(root) / f
                        found = True
                        break
                if found:
                    break

        if stem_path.exists():
            stems[stem] = stem_path
            print(f"[INFO] Found stem: {stem} -> {stem_path}")
        else:
            print(f"[ERROR] Stem not found: {stem}.wav")

    if len(stems) == 0:
        print("[ERROR] No stems found after Demucs multi-stem separation")
        return None

    print(f"[INFO] Multi-stem separation complete. Found {len(stems)} stems.")
    return stems


def main():
    parser = argparse.ArgumentParser(
        description="Audio stem separation using Demucs for Genesis Hero"
    )
    parser.add_argument("input_file", help="Input audio file (MP3 or WAV)")
    parser.add_argument("output_dir", help="Output directory for stems")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--two-stems", action="store_true", default=True,
        help="Split into vocals and instrumental (default)"
    )
    mode_group.add_argument(
        "--multi-stems", action="store_true",
        help="Split into drums, bass, other, vocals"
    )

    args = parser.parse_args()

    if args.multi_stems:
        result = split_multi_stems(args.input_file, args.output_dir)
        if result:
            print("\n[INFO] Multi-stem results:")
            for stem, path in result.items():
                print(f"  {stem}: {path}")
        else:
            print("\n[ERROR] Multi-stem separation failed")
            sys.exit(1)
    else:
        result = split_two_stems(args.input_file, args.output_dir)
        if result:
            print(f"\n[INFO] Instrumental saved to: {result}")
        else:
            print("\n[ERROR] Two-stem separation failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
