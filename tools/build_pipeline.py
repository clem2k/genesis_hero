#!/usr/bin/env python3
"""
build_pipeline.py - Master orchestration script for the Genesis Hero pipeline.

Takes a project directory, finds all MP3 files, and runs the complete
processing pipeline:
  1. Audio stem separation (Demucs)
  2. MIDI conversion (basic-pitch)
  3. MIDI processing for Mega Drive
  4. Note chart generation (3 difficulties)
  5. VGM generation
  6. C header generation
  7. Resource file generation

Usage:
    python build_pipeline.py <project_dir> [--skip-audio] [--dry-run]
"""

import os
import sys
import argparse
import shutil
import time
import traceback
import json
from pathlib import Path

# Add tools directory to path for local imports
TOOLS_DIR = Path(__file__).parent.resolve()
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


# ──────────────────────────────────────────────
# Pipeline configuration
# ──────────────────────────────────────────────

# Directories to exclude when searching for MP3 files
EXCLUDE_DIRS = {
    'tools', 'genesis_tools', 'res', '.git', '.vscode',
    'node_modules', '__pycache__', 'build', 'out', 'inc'
}


def _sanitize_song_name(name):
    """Sanitize a filename for use as a song identifier."""
    # Remove extension, lowercase, replace spaces/special chars with underscore
    name = name.lower()
    name = name.replace(' ', '_').replace('-', '_')
    # Remove non-alphanumeric except underscore
    name = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
    # Collapse multiple underscores
    while '__' in name:
        name = name.replace('__', '_')
    return name.strip('_')


import re

def _find_song_files(project_dir):
    """
    Find all source song files in the project's music directory.
    Supported formats: .mp3, .flac, .mid, .midi

    Returns:
        List of Path objects.
    """
    project_dir = Path(project_dir)
    music_dir = project_dir / 'music'
    if not music_dir.exists() or not music_dir.is_dir():
        print(f"[WARNING] Music directory not found at: {music_dir}")
        return []

    supported_suffixes = {'.mp3', '.flac', '.mid', '.midi'}
    files = []
    for f in music_dir.iterdir():
        if f.is_file() and f.suffix.lower() in supported_suffixes:
            files.append(f)
    return sorted(files)


def get_song_metadata(file_path):
    """
    Extract song title and artist.
    Falls back to a cleaned filename if metadata is missing.

    Returns:
        tuple: (display_name, clean_id)
    """
    file_path = Path(file_path)
    display_name = None

    # 1. Try to use tinytag for audio formats (.mp3, .flac)
    if file_path.suffix.lower() in ['.mp3', '.flac']:
        try:
            from tinytag import TinyTag
            tag = TinyTag.get(str(file_path))
            title = tag.title
            artist = tag.artist

            if title and artist:
                display_name = f"{artist.strip()} - {title.strip()}"
            elif title:
                display_name = title.strip()
        except Exception as e:
            print(f"[INFO] TinyTag failed to read metadata for {file_path.name}: {e}")

    # 2. Fallback: Clean the filename
    if not display_name:
        stem = file_path.stem  # remove extension
        # Remove starting numbers, track numbers, e.g. "01-Human" -> "Human", "3_Fatality" -> "Fatality"
        clean_name = re.sub(r'^\d+[-_.\s]*', '', stem)
        # Replace dashes, underscores, multiple spaces with a single space
        clean_name = re.sub(r'[-_\s]+', ' ', clean_name).strip()
        # Capitalize words
        display_name = clean_name.title()

    # Standardize spaces
    display_name = " ".join(display_name.split())
    # Clean ID for C variable
    clean_id = _sanitize_song_name(file_path.stem)

    return display_name, clean_id


def check_ffmpeg(project_dir):
    """
    Check if FFmpeg is available. If not, try to download/use the portable one.
    """
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    local_ffmpeg = Path(project_dir) / "genesis_tools" / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    print("[INFO] FFmpeg not found. Attempting to download portable FFmpeg...")
    try:
        scripts_dir = Path(__file__).parent.resolve()
        downloader = scripts_dir / "download_ffmpeg.py"
        if downloader.exists():
            import subprocess
            subprocess.run([sys.executable, str(downloader)], check=True)
            if local_ffmpeg.exists():
                return str(local_ffmpeg)
    except Exception as e:
        print(f"[ERROR] Failed to run FFmpeg downloader: {e}")

    return None


def convert_flac_to_mp3(flac_path, output_mp3_path, ffmpeg_bin):
    """
    Convert FLAC to MP3 using ffmpeg.
    """
    if not ffmpeg_bin:
        print("[ERROR] FFmpeg binary not found. Cannot convert FLAC to MP3.")
        return None

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(flac_path),
        "-codec:a", "libmp3lame",
        "-qscale:a", "2",
        str(output_mp3_path)
    ]
    try:
        print(f"[INFO] Converting FLAC to MP3: {flac_path.name} -> {output_mp3_path.name}")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_mp3_path
    except Exception as e:
        print(f"[ERROR] FLAC to MP3 conversion failed: {e}")
        return None



def _find_stems(stems_dir):
    """
    Find WAV stem files in a directory, searching subdirectories
    (demucs creates nested output).

    Returns:
        Dict mapping stem name to path: {'drums': Path, 'bass': Path, 'other': Path}
    """
    stems_dir = Path(stems_dir)
    stems = {}

    for stem_name in ['drums', 'bass', 'other']:
        # Direct file
        direct = stems_dir / f"{stem_name}.wav"
        if direct.exists():
            stems[stem_name] = direct
            continue

        # Search recursively
        for p in stems_dir.rglob(f"{stem_name}.wav"):
            stems[stem_name] = p
            break

    return stems


def _find_midi_files(midi_dir):
    """
    Find MIDI files in a directory.

    Returns:
        Dict mapping stem name to path: {'drums': Path, 'bass': Path, 'other': Path}
    """
    midi_dir = Path(midi_dir)
    midis = {}

    for stem_name in ['drums', 'bass', 'other']:
        midi_path = midi_dir / f"{stem_name}.mid"
        if midi_path.exists():
            midis[stem_name] = midi_path

    return midis


def run_pipeline(project_dir, skip_audio=False, dry_run=False):
    """
    Run the complete Genesis Hero build pipeline.

    Args:
        project_dir: Root project directory.
        skip_audio: If True, skip Demucs/basic-pitch steps.
        dry_run: If True, print actions without executing.

    Returns:
        True if pipeline completed successfully, False otherwise.
    """
    project_dir = Path(project_dir).resolve()

    if not project_dir.exists():
        print(f"[ERROR] Project directory not found: {project_dir}")
        return False

    print("=" * 60)
    print("  Genesis Hero - Build Pipeline")
    print("=" * 60)
    print(f"[INFO] Project directory: {project_dir}")
    print(f"[INFO] Skip audio: {skip_audio}")
    print(f"[INFO] Dry run: {dry_run}")
    print()

    # ── Import tool modules ──
    try:
        from audio_splitter import split_two_stems, split_multi_stems
        from midi_converter import convert_all_stems as convert_stems_to_midi
        from midi_processor import process_midi, merge_stems_midi, separate_midi_file
        from note_chart_generator import generate_all_charts
        from vgm_generator import generate_vgm
        from chart_to_header import generate_header
    except ImportError as e:
        print(f"[ERROR] Failed to import tool modules: {e}")
        print(f"[ERROR] Make sure all tool scripts are in: {TOOLS_DIR}")
        return False

    # ── Setup directories ──
    tools_output = project_dir / 'tools' / 'output'
    stems_dir = tools_output / 'stems'
    midi_dir = tools_output / 'midi'
    charts_dir = tools_output / 'charts'
    vgm_dir = tools_output / 'vgm'
    res_music = project_dir / 'res' / 'music'
    inc_dir = project_dir / 'inc'

    if not dry_run:
        # Create music/ directory in project root if it doesn't exist
        (project_dir / 'music').mkdir(parents=True, exist_ok=True)
        for d in [tools_output, stems_dir, midi_dir, charts_dir, vgm_dir, res_music, inc_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Find Song files ──
    song_files = _find_song_files(project_dir)

    if not song_files:
        print("[ERROR] No supported music files found in music/ directory")
        print(f"[INFO] Searched: {project_dir / 'music'}")
        print("[INFO] Supported formats: .mp3, .flac, .mid, .midi")
        return False

    print(f"[INFO] Found {len(song_files)} music file(s):")
    for song_file in song_files:
        display_name, clean_id = get_song_metadata(song_file)
        print(f"[INFO]   {song_file.name} (Display: '{display_name}', ID: '{clean_id}')")
    print()

    # Check for FFmpeg (required if we have FLAC files)
    ffmpeg_bin = check_ffmpeg(project_dir)

    # ── Process each song ──
    start_time = time.time()
    song_results = []
    errors = []

    for song_idx, src_path in enumerate(song_files):
        display_name, clean_id = get_song_metadata(src_path)
        song_name = _sanitize_song_name(src_path.stem)
        song_id = f"song_{song_idx}"

        is_midi_input = src_path.suffix.lower() in ['.mid', '.midi']
        is_flac_input = src_path.suffix.lower() == '.flac'

        print()
        print("=" * 60)
        print(f"  Processing Song {song_idx}: {src_path.name}")
        print(f"  Display Name: {display_name}")
        print(f"  Identifier: {song_id} ({song_name})")
        print("=" * 60)

        song_stems_dir = stems_dir / song_name
        song_midi_dir = midi_dir / song_name
        merged_midi_path = song_midi_dir / 'merged.mid'
        vgm_path = vgm_dir / f'{song_id}.vgm'

        if dry_run:
            print(f"[DRY-RUN] Would process: {src_path}")
            print(f"[DRY-RUN]   Stems -> {song_stems_dir}")
            print(f"[DRY-RUN]   MIDI -> {song_midi_dir}")
            print(f"[DRY-RUN]   Charts -> {charts_dir}")
            print(f"[DRY-RUN]   VGM -> {vgm_path}")
            song_results.append({'index': song_idx, 'name': song_name, 'status': 'dry-run'})
            continue

        song_ok = True
        stem_paths = {}

        # Check if VGM and charts already exist to skip audio processing for this song
        song_skip_audio = skip_audio
        dest_vgm = res_music / f"{song_id}.vgm"
        song_charts_exist = all((charts_dir / f"{song_id}_{diff}.json").exists() for diff in ['easy', 'normal', 'hard'])
        if dest_vgm.exists() and song_charts_exist:
            print(f"[INFO] Existing VGM and charts found for {song_id}. Skipping audio processing for this song.")
            song_skip_audio = True

        # Handle FLAC conversion
        working_mp3_path = src_path
        if is_flac_input and not song_skip_audio:
            song_stems_dir.mkdir(parents=True, exist_ok=True)
            output_mp3 = song_stems_dir / 'converted.mp3'
            working_mp3_path = convert_flac_to_mp3(src_path, output_mp3, ffmpeg_bin)
            if not working_mp3_path:
                errors.append((song_idx, "FLAC to MP3 conversion failed"))
                song_ok = False

        # ──── Step 1: Audio Splitting / MIDI track separation ────
        if song_ok:
            if is_midi_input:
                if not song_skip_audio:
                    print(f"\n[STEP 1/6] MIDI track separation...")
                    try:
                        # Separate multi-track MIDI into stems
                        stems_dict = separate_midi_file(src_path, song_midi_dir)
                        if stems_dict:
                            # Copy MIDI stems to song_stems_dir for the note chart generator
                            song_stems_dir.mkdir(parents=True, exist_ok=True)
                            for stem_name, stem_path in stems_dict.items():
                                dest = song_stems_dir / f"{stem_name}.mid"
                                shutil.copy2(str(stem_path), str(dest))
                            print(f"[INFO] MIDI stems generated in: {song_stems_dir}")
                            stem_paths = stems_dict
                        else:
                            print("[ERROR] MIDI track separation failed")
                            errors.append((song_idx, "MIDI track separation failed"))
                            song_ok = False
                    except Exception as e:
                        print(f"[ERROR] MIDI track separation failed: {e}")
                        traceback.print_exc()
                        errors.append((song_idx, f"MIDI track separation: {e}"))
                        song_ok = False
                else:
                    print(f"\n[STEP 1/6] Skipping MIDI track separation (Existing files found)")
                    stem_paths = {}
                    for stem_name in ['drums', 'bass', 'other']:
                        for p in song_stems_dir.rglob(f"{stem_name}.mid"):
                            stem_paths[stem_name] = p
                            break
            elif not song_skip_audio:
                print(f"\n[STEP 1/6] Splitting audio stems...")
                try:
                    # Two-stem split: vocals vs instrumental
                    instrumental_path = split_two_stems(working_mp3_path, song_stems_dir)

                    if instrumental_path is None:
                        print("[ERROR] Two-stem separation failed")
                        errors.append((song_idx, "Two-stem separation failed"))
                        song_ok = False
                    else:
                        # Multi-stem split on instrumental
                        stem_result = split_multi_stems(instrumental_path, song_stems_dir)

                        if stem_result is None:
                            print("[ERROR] Multi-stem separation failed")
                            errors.append((song_idx, "Multi-stem separation failed"))
                            song_ok = False
                        else:
                            stem_paths = stem_result
                            print(f"[INFO] Stems: {list(stem_paths.keys())}")

                except Exception as e:
                    print(f"[ERROR] Audio splitting failed: {e}")
                    traceback.print_exc()
                    errors.append((song_idx, f"Audio splitting: {e}"))
                    song_ok = False
            else:
                print(f"\n[STEP 1/6] Skipping audio splitting (Existing files found or --skip-audio)")
                stem_paths = _find_stems(song_stems_dir)
                if stem_paths:
                    print(f"[INFO] Found existing stems: {list(stem_paths.keys())}")
                else:
                    # Try finding existing MIDI stems
                    mid_stems = {}
                    for stem_name in ['drums', 'bass', 'other']:
                        for p in song_stems_dir.rglob(f"{stem_name}.mid"):
                            mid_stems[stem_name] = p
                            break
                    if mid_stems:
                        stem_paths = mid_stems
                        print(f"[INFO] Found existing MIDI stems: {list(stem_paths.keys())}")
                    else:
                        print(f"[INFO] No existing stems found in {song_stems_dir}")

        # ──── Step 2: MIDI Conversion ────
        if not song_skip_audio and song_ok and not is_midi_input:
            print(f"\n[STEP 2/6] Converting stems to MIDI...")
            try:
                midi_results = convert_stems_to_midi(song_stems_dir, song_midi_dir)
                if not midi_results:
                    # Try with the stem paths directly
                    if stem_paths:
                        for stem_name, stem_path in stem_paths.items():
                            # Copy stems to a flat directory for conversion
                            flat_dir = song_stems_dir / '_flat'
                            flat_dir.mkdir(parents=True, exist_ok=True)
                            flat_path = flat_dir / f"{stem_name}.wav"
                            if not flat_path.exists():
                                shutil.copy2(str(stem_path), str(flat_path))
                        midi_results = convert_stems_to_midi(flat_dir, song_midi_dir)

                if midi_results:
                    print(f"[INFO] MIDI files: {list(midi_results.keys())}")
                else:
                    print("[ERROR] MIDI conversion produced no files")
                    errors.append((song_idx, "MIDI conversion failed"))
            except Exception as e:
                print(f"[ERROR] MIDI conversion failed: {e}")
                traceback.print_exc()
                errors.append((song_idx, f"MIDI conversion: {e}"))
        else:
            print(f"\n[STEP 2/6] Skipping MIDI conversion (MIDI input, existing files found, or --skip-audio)")

        # ──── Step 3: MIDI Processing ────
        if song_ok:
            if not song_skip_audio or not merged_midi_path.exists():
                print(f"\n[STEP 3/6] Processing MIDI for Mega Drive...")
                try:
                    midi_files = _find_midi_files(song_midi_dir)

                    if midi_files:
                        print(f"[INFO] Found MIDI files: {list(midi_files.keys())}")

                        # Convert Path objects to strings for merge function
                        midi_str_dict = {k: str(v) for k, v in midi_files.items()}
                        result = merge_stems_midi(midi_str_dict, str(merged_midi_path))

                        if result:
                            print(f"[INFO] Merged MIDI: {merged_midi_path}")
                        else:
                            print("[ERROR] MIDI merge/process failed")
                            errors.append((song_idx, "MIDI processing failed"))
                    else:
                        print(f"[INFO] No MIDI files found in {song_midi_dir}")
                        if not song_skip_audio:
                            errors.append((song_idx, "No MIDI files to process"))

                except Exception as e:
                    print(f"[ERROR] MIDI processing failed: {e}")
                    traceback.print_exc()
                    errors.append((song_idx, f"MIDI processing: {e}"))
            else:
                print(f"\n[STEP 3/6] Skipping MIDI processing (Existing merged MIDI found)")

        # ──── Step 4: Chart Generation ────
        if song_ok:
            if not song_skip_audio:
                print(f"\n[STEP 4/6] Generating note charts...")
                try:
                    # Find stems for onset detection (check WAV or MIDI)
                    chart_stems_dir = song_stems_dir
                    available_stems = {}
                    for stem_name in ['drums', 'bass', 'other']:
                        for p in song_stems_dir.rglob(f"{stem_name}.wav"):
                            available_stems[stem_name] = p
                            break
                        if stem_name not in available_stems:
                            for p in song_stems_dir.rglob(f"{stem_name}.mid"):
                                available_stems[stem_name] = p
                                break

                    if available_stems:
                        # Copy stems to a flat directory for the chart generator
                        flat_stems = song_stems_dir / '_chart_stems'
                        flat_stems.mkdir(parents=True, exist_ok=True)
                        for stem_name, stem_path in available_stems.items():
                            ext = Path(stem_path).suffix
                            dest = flat_stems / f"{stem_name}{ext}"
                            if not dest.exists():
                                shutil.copy2(str(stem_path), str(dest))
                        chart_stems_dir = flat_stems

                        chart_results = generate_all_charts(
                            str(chart_stems_dir), song_id, str(charts_dir)
                        )
                        
                        # Update song name in chart files since generate_all_charts writes song_id as song_name
                        # Let's fix that by rewriting the song_name in the JSON files!
                        if chart_results:
                            for chart_path in chart_results:
                                with open(chart_path, 'r', encoding='utf-8') as fp:
                                    data = json.load(fp)
                                data['song_name'] = display_name
                                with open(chart_path, 'w', encoding='utf-8') as fp:
                                    json.dump(data, fp, indent=2)
                            print(f"[INFO] Charts generated: {len(chart_results)}")
                        else:
                            print("[ERROR] Chart generation produced no files")
                            errors.append((song_idx, "Chart generation failed"))
                    else:
                        print(f"[INFO] No stems available for chart generation")
                        if not song_skip_audio:
                            errors.append((song_idx, "No stems for chart generation"))

                except Exception as e:
                    print(f"[ERROR] Chart generation failed: {e}")
                    traceback.print_exc()
                    errors.append((song_idx, f"Chart generation: {e}"))
            else:
                print(f"\n[STEP 4/6] Skipping note chart generation (Existing charts found)")

        # ──── Step 5: VGM Generation ────
        if song_ok:
            if not song_skip_audio or not dest_vgm.exists():
                print(f"\n[STEP 5/6] Generating VGM...")
                try:
                    if merged_midi_path.exists():
                        vgm_result = generate_vgm(str(merged_midi_path), str(vgm_path))

                        if vgm_result:
                            # Copy VGM to res/music/
                            shutil.copy2(str(vgm_path), str(dest_vgm))
                            print(f"[INFO] VGM copied to: {dest_vgm}")
                        else:
                            print("[ERROR] VGM generation failed")
                            errors.append((song_idx, "VGM generation failed"))
                    else:
                        print(f"[INFO] No merged MIDI found at {merged_midi_path}, skipping VGM")
                        if not song_skip_audio:
                            errors.append((song_idx, "No MIDI for VGM generation"))

                except Exception as e:
                    print(f"[ERROR] VGM generation failed: {e}")
                    traceback.print_exc()
                    errors.append((song_idx, f"VGM generation: {e}"))
            else:
                print(f"\n[STEP 5/6] Skipping VGM generation (Existing VGM found)")

        song_results.append({
            'index': song_idx,
            'name': song_name,
            'status': 'ok' if song_ok else 'errors'
        })

    # ──── Step 6: Generate header and resources ────
    if not dry_run:
        print(f"\n[STEP 6/6] Generating C header file and resources...")

        # Generate header from charts
        try:
            chart_files = list(charts_dir.glob("*.json"))
            if chart_files:
                header_path = inc_dir / 'song_data.h'
                result = generate_header(str(charts_dir), str(header_path))
                if result:
                    print(f"[INFO] Header generated: {header_path}")
                else:
                    print("[ERROR] Header generation failed")
                    errors.append((-1, "Header generation failed"))
            else:
                print("[INFO] No chart files found, skipping header generation")
        except Exception as e:
            print(f"[ERROR] Header generation failed: {e}")
            traceback.print_exc()
            errors.append((-1, f"Header generation: {e}"))

        # Generate resources.res
        try:
            vgm_files = sorted(res_music.glob("*.vgm"))
            if vgm_files:
                res_path = project_dir / 'res' / 'resources.res'
                res_lines = []

                # Read existing resources.res if it exists (preserve non-music entries)
                existing_lines = []
                if res_path.exists():
                    with open(res_path, 'r') as f:
                        for line in f:
                            stripped = line.strip()
                            # Keep non-XGM lines
                            if stripped and not stripped.startswith('XGM '):
                                existing_lines.append(line.rstrip())

                if existing_lines:
                    res_lines.extend(existing_lines)
                    res_lines.append("")

                res_lines.append("// Music (auto-generated by build_pipeline.py)")
                for vgm_file in vgm_files:
                    song_id = vgm_file.stem
                    res_lines.append(f'XGM {song_id} "music/{vgm_file.name}"')

                res_lines.append("")

                with open(res_path, 'w') as f:
                    f.write('\n'.join(res_lines))

                print(f"[INFO] Resources file updated: {res_path}")
                print(f"[INFO]   VGM entries: {len(vgm_files)}")
            else:
                print("[INFO] No VGM files found in res/music/, skipping resources.res")
        except Exception as e:
            print(f"[ERROR] Resource file generation failed: {e}")
            traceback.print_exc()
            errors.append((-1, f"Resource generation: {e}"))

    # ── Summary ──
    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("  Pipeline Complete!")
    print("=" * 60)
    print(f"[INFO] Songs processed: {len(song_results)}")
    print(f"[INFO] Time elapsed: {elapsed:.1f}s")

    # Count outputs
    chart_count = len(list(charts_dir.glob("*.json"))) if charts_dir.exists() else 0
    vgm_count = len(list(res_music.glob("*.vgm"))) if res_music.exists() else 0
    header_exists = (inc_dir / 'song_data.h').exists()

    print(f"[INFO] Charts generated: {chart_count}")
    print(f"[INFO] VGM files: {vgm_count}")
    print(f"[INFO] Header: {'inc/song_data.h' if header_exists else 'Not generated'}")

    if errors:
        print()
        print(f"[WARNING] {len(errors)} error(s) occurred:")
        for song_idx, msg in errors:
            if song_idx >= 0:
                print(f"  Song {song_idx}: {msg}")
            else:
                print(f"  Global: {msg}")
    else:
        print(f"[INFO] No errors!")

    print("=" * 60)

    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Genesis Hero - Master Build Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_pipeline.py d:\\dev\\Game
  python build_pipeline.py d:\\dev\\Game --skip-audio
  python build_pipeline.py d:\\dev\\Game --dry-run

The pipeline will:
  1. Find all MP3 files in the project directory
  2. Split audio into stems (drums, bass, other)
  3. Convert stems to MIDI
  4. Process MIDI for Mega Drive constraints
  5. Generate note charts (easy/normal/hard)
  6. Generate VGM music files
  7. Generate C header and resource files
        """
    )
    parser.add_argument(
        "project_dir",
        help="Root project directory containing MP3 files"
    )
    parser.add_argument(
        "--skip-audio", action="store_true",
        help="Skip Demucs/basic-pitch steps, reuse existing stems/MIDI"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without executing"
    )

    args = parser.parse_args()

    success = run_pipeline(
        args.project_dir,
        skip_audio=args.skip_audio,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
