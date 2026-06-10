#!/usr/bin/env python3
"""
midi_converter.py - Convert WAV audio stems to MIDI using basic-pitch.

Part of the Genesis Hero pipeline. Converts separated audio stems
into MIDI files for further processing.
"""

import os
import sys
import argparse
from pathlib import Path


def convert_stem_to_midi(wav_path, output_midi_path):
    """
    Convert a single WAV stem to MIDI using basic-pitch.

    Args:
        wav_path: Path to input WAV file.
        output_midi_path: Path for output MIDI file.

    Returns:
        Path to output MIDI file on success, None on failure.
    """
    wav_path = Path(wav_path).resolve()
    output_midi_path = Path(output_midi_path).resolve()

    if not wav_path.exists():
        print(f"[ERROR] Input WAV not found: {wav_path}")
        return None

    print(f"[INFO] Converting to MIDI: {wav_path.name} -> {output_midi_path.name}")

    try:
        from basic_pitch.inference import predict
    except ImportError:
        print("[ERROR] basic-pitch not installed. Install with: pip install basic-pitch")
        return None

    try:
        # Run basic-pitch prediction
        print(f"[INFO] Running basic-pitch inference on {wav_path.name}...")
        model_output, midi_data, note_events = predict(str(wav_path))

        # Create output directory if needed
        output_midi_path.parent.mkdir(parents=True, exist_ok=True)

        # Write MIDI file
        midi_data.write(str(output_midi_path))

        # Report stats
        num_notes = len(note_events)
        print(f"[INFO] Conversion complete: {output_midi_path.name}")
        print(f"[INFO]   Notes detected: {num_notes}")

        if num_notes == 0:
            print(f"[INFO]   Warning: No notes detected in {wav_path.name}")

        return output_midi_path

    except Exception as e:
        print(f"[ERROR] Failed to convert {wav_path.name}: {e}")
        return None


def convert_all_stems(stems_dir, output_dir):
    """
    Convert all WAV files in a directory to MIDI.

    Args:
        stems_dir: Directory containing WAV stem files.
        output_dir: Directory for output MIDI files.

    Returns:
        Dict mapping stem name to MIDI path (only successful conversions).
    """
    stems_dir = Path(stems_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not stems_dir.exists():
        print(f"[ERROR] Stems directory not found: {stems_dir}")
        return {}

    # Find all WAV files
    wav_files = sorted(stems_dir.glob("*.wav"))

    if not wav_files:
        print(f"[ERROR] No WAV files found in: {stems_dir}")
        return {}

    print(f"[INFO] Found {len(wav_files)} WAV files in {stems_dir}")
    print(f"[INFO] Output directory: {output_dir}")

    results = {}
    success_count = 0
    fail_count = 0

    for wav_path in wav_files:
        stem_name = wav_path.stem  # e.g., "drums", "bass", "other"
        midi_filename = f"{stem_name}.mid"
        output_path = output_dir / midi_filename

        print(f"\n[INFO] --- Processing: {wav_path.name} ---")
        result = convert_stem_to_midi(wav_path, output_path)

        if result:
            results[stem_name] = result
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print(f"\n[INFO] === MIDI Conversion Summary ===")
    print(f"[INFO]   Total WAV files: {len(wav_files)}")
    print(f"[INFO]   Successful: {success_count}")
    print(f"[INFO]   Failed: {fail_count}")

    for name, path in results.items():
        print(f"[INFO]   {name}: {path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Convert WAV audio stems to MIDI using basic-pitch"
    )
    parser.add_argument("input", help="Input WAV file or directory (with --batch)")
    parser.add_argument("output", help="Output MIDI file or directory (with --batch)")
    parser.add_argument(
        "--batch", action="store_true",
        help="Batch mode: treat input/output as directories"
    )

    args = parser.parse_args()

    if args.batch:
        results = convert_all_stems(args.input, args.output)
        if not results:
            print("[ERROR] No MIDI files were generated")
            sys.exit(1)
    else:
        result = convert_stem_to_midi(args.input, args.output)
        if not result:
            print("[ERROR] MIDI conversion failed")
            sys.exit(1)
        print(f"\n[INFO] MIDI saved to: {result}")


if __name__ == "__main__":
    main()
