#!/usr/bin/env python3
"""
note_chart_generator.py - Generate rhythm game note charts from audio stems.

Creates note charts at three difficulty levels (Easy/Normal/Hard) by detecting
onsets in separated audio stems and mapping them to game lanes.

Lane mapping (5 lanes max):
  0=LEFT, 1=UP, 2=DOWN, 3=A, 4=B

Output is JSON with frame-based timing at 60 FPS (NTSC).
"""

import os
import sys
import json
import argparse
import numpy as np
from pathlib import Path

# Lane constants (5 lanes max — matches game.h)
LANE_LEFT = 0
LANE_UP = 1
LANE_DOWN = 2
LANE_A = 3
LANE_B = 4
NUM_LANES = 5

LANE_NAMES = {0: "LEFT", 1: "UP", 2: "DOWN", 3: "A", 4: "B"}

FPS = 60  # NTSC frame rate

# Stem-to-lane mapping
DRUM_LANES = [LANE_LEFT, LANE_UP, LANE_DOWN]
BASS_LANES = [LANE_A]
OTHER_LANES = [LANE_B]

DIFFICULTY_SETTINGS = {
    'easy': {
        'active_lanes': [LANE_UP, LANE_DOWN, LANE_A],
        'min_gap': 0.5,       # Minimum gap between notes in seconds
        'onset_threshold': 0.8,  # Higher = fewer onsets detected
        'max_notes_per_beat': 1
    },
    'normal': {
        'active_lanes': [LANE_UP, LANE_DOWN, LANE_A, LANE_B],
        'min_gap': 0.3,
        'onset_threshold': 0.5,
        'max_notes_per_beat': 2
    },
    'hard': {
        'active_lanes': [LANE_LEFT, LANE_UP, LANE_DOWN, LANE_A, LANE_B],
        'min_gap': 0.15,
        'onset_threshold': 0.3,
        'max_notes_per_beat': 3
    }
}


def detect_onsets(audio_path, sr=22050, threshold=0.5):
    """
    Detect note onsets in an audio file using librosa.

    Args:
        audio_path: Path to audio file.
        sr: Sample rate for loading.
        threshold: Onset detection threshold (delta parameter).
                   Higher = fewer onsets.

    Returns:
        List of onset times in seconds.
    """
    try:
        import librosa
    except ImportError:
        print("[ERROR] librosa not installed. Install with: pip install librosa")
        return []

    audio_path = str(audio_path)
    print(f"[INFO]   Detecting onsets in: {Path(audio_path).name} (threshold={threshold})")

    try:
        y, sr = librosa.load(audio_path, sr=sr, mono=True)

        # Detect onsets
        onset_frames = librosa.onset.onset_detect(
            y=y, sr=sr,
            backtrack=True,
            units='frames',
            delta=threshold
        )

        # Convert frames to times
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        onset_times = onset_times.tolist()

        print(f"[INFO]   Found {len(onset_times)} onsets in {Path(audio_path).name}")
        return onset_times

    except Exception as e:
        print(f"[ERROR]   Onset detection failed for {Path(audio_path).name}: {e}")
        return []


def get_tempo_and_duration(audio_path, sr=22050):
    """
    Get tempo and duration from an audio file.

    Returns:
        Tuple (tempo_bpm, duration_seconds)
    """
    try:
        import librosa
    except ImportError:
        return 120.0, 0.0

    try:
        y, sr = librosa.load(str(audio_path), sr=sr, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        # librosa may return an array; extract scalar
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
        else:
            tempo = float(tempo)
        duration = float(len(y) / sr)
        return tempo, duration
    except Exception as e:
        print(f"[ERROR]   Failed to get tempo/duration: {e}")
        return 120.0, 0.0


def time_to_frame(time_sec):
    """
    Convert time in seconds to frame number at 60 FPS (NTSC).

    Args:
        time_sec: Time in seconds.

    Returns:
        Frame number (integer).
    """
    return int(round(time_sec * FPS))


def quantize_to_beat_grid(onset_times, tempo, tolerance=0.05):
    """
    Quantize onset times to nearest beat subdivision (1/4 beat).

    Args:
        onset_times: List of onset times in seconds.
        tempo: Tempo in BPM.
        tolerance: Maximum snap distance in seconds.

    Returns:
        List of quantized onset times.
    """
    if tempo <= 0 or not onset_times:
        return onset_times

    beat_duration = 60.0 / tempo
    subdivision = beat_duration / 4.0  # 1/4 beat (16th note)

    quantized = []
    for t in onset_times:
        # Find nearest grid point
        grid_index = round(t / subdivision)
        grid_time = grid_index * subdivision

        if abs(t - grid_time) <= tolerance:
            quantized.append(grid_time)
        else:
            quantized.append(t)  # Keep original if too far from grid

    return quantized


def filter_by_min_gap(notes, min_gap_seconds):
    """
    Remove notes that are too close together, per lane.

    Args:
        notes: List of (frame, lane) tuples.
        min_gap_seconds: Minimum gap between notes in the same lane.

    Returns:
        Filtered list of (frame, lane) tuples.
    """
    min_gap_frames = int(min_gap_seconds * FPS)

    # Group by lane
    lanes = {}
    for frame, lane in notes:
        if lane not in lanes:
            lanes[lane] = []
        lanes[lane].append(frame)

    # Filter each lane
    filtered_frames = {}
    for lane, frames in lanes.items():
        frames.sort()
        filtered = []
        last_frame = -999999
        for frame in frames:
            if frame - last_frame >= min_gap_frames:
                filtered.append(frame)
                last_frame = frame
        filtered_frames[lane] = filtered

    # Reconstruct sorted list
    result = []
    for lane, frames in filtered_frames.items():
        for frame in frames:
            result.append((frame, lane))

    result.sort(key=lambda x: x[0])
    return result


def detect_onsets_from_midi(midi_path):
    """
    Extract unique note start times (onsets) from a MIDI file.
    """
    try:
        import pretty_midi
    except ImportError:
        print("[ERROR] pretty_midi not installed. Install with: pip install pretty_midi")
        return []

    print(f"[INFO]   Extracting onsets from MIDI: {Path(midi_path).name}")
    try:
        midi_data = pretty_midi.PrettyMIDI(str(midi_path))
        onset_times = []
        for inst in midi_data.instruments:
            for note in inst.notes:
                onset_times.append(note.start)
        onset_times = sorted(list(set(onset_times)))
        print(f"[INFO]   Found {len(onset_times)} note events in MIDI: {Path(midi_path).name}")
        return onset_times
    except Exception as e:
        print(f"[ERROR]   Failed to parse MIDI onsets: {e}")
        return []


def get_tempo_and_duration_from_midi(midi_path):
    """
    Get tempo and duration from a MIDI file.
    """
    try:
        import pretty_midi
    except ImportError:
        return 120.0, 0.0

    try:
        midi_data = pretty_midi.PrettyMIDI(str(midi_path))
        tempo_changes = midi_data.get_tempo_changes()
        if len(tempo_changes[1]) > 0:
            tempo = tempo_changes[1][0]
        else:
            tempo = 120.0
        duration = midi_data.get_end_time()
        return float(tempo), float(duration)
    except Exception as e:
        print(f"[ERROR]   Failed to get MIDI tempo/duration: {e}")
        return 120.0, 0.0


def generate_chart(stems_dir, song_name, difficulty, output_path):
    """
    Generate a rhythm game note chart from audio or MIDI stems.

    Args:
        stems_dir: Directory containing WAV or MIDI stem files.
        song_name: Name of the song.
        difficulty: 'easy', 'normal', or 'hard'.
        output_path: Path for output JSON file.

    Returns:
        Path to output file on success, None on failure.
    """
    stems_dir = Path(stems_dir).resolve()
    output_path = Path(output_path).resolve()

    if difficulty not in DIFFICULTY_SETTINGS:
        print(f"[ERROR] Invalid difficulty: {difficulty}")
        return None

    settings = DIFFICULTY_SETTINGS[difficulty]
    active_lanes = settings['active_lanes']
    min_gap = settings['min_gap']
    threshold = settings['onset_threshold']

    print(f"[INFO] Generating {difficulty} chart for: {song_name}")
    print(f"[INFO]   Active lanes: {[LANE_NAMES[l] for l in active_lanes]}")
    print(f"[INFO]   Min gap: {min_gap}s, Threshold: {threshold}")

    # Find stem files (check WAV first, then MIDI)
    stems = {}
    is_midi_source = False
    for stem_name in ['drums', 'bass', 'other']:
        # Try WAV
        wav_path = stems_dir / f"{stem_name}.wav"
        if wav_path.exists():
            stems[stem_name] = wav_path
            continue

        # Try WAV recursively (demucs structure)
        found_wav = False
        for p in stems_dir.rglob(f"{stem_name}.wav"):
            stems[stem_name] = p
            found_wav = True
            break
        if found_wav:
            continue

        # Try MIDI
        mid_path = stems_dir / f"{stem_name}.mid"
        if mid_path.exists():
            stems[stem_name] = mid_path
            is_midi_source = True
            continue

        # Try MIDI recursively
        found_mid = False
        for p in stems_dir.rglob(f"{stem_name}.mid"):
            stems[stem_name] = p
            is_midi_source = True
            found_mid = True
            break
        if found_mid:
            continue

    if not stems:
        print(f"[ERROR] No stem WAV or MIDI files found in: {stems_dir}")
        return None

    print(f"[INFO]   Found stems: {list(stems.keys())} (MIDI source: {is_midi_source})")

    # Get tempo and duration from any available stem
    any_stem = next(iter(stems.values()))
    if is_midi_source:
        tempo, duration = get_tempo_and_duration_from_midi(any_stem)
    else:
        tempo, duration = get_tempo_and_duration(any_stem)
    print(f"[INFO]   Tempo: {tempo:.1f} BPM, Duration: {duration:.1f}s")

    # Detect onsets for each stem
    all_notes = []

    # Helper to detect based on source type
    def get_onsets_for_stem(path):
        if is_midi_source:
            return detect_onsets_from_midi(path)
        else:
            return detect_onsets(path, threshold=threshold)

    # Drum onsets -> directional lanes (UP, DOWN, LEFT)
    if 'drums' in stems:
        drum_onsets = get_onsets_for_stem(stems['drums'])
        drum_onsets = quantize_to_beat_grid(drum_onsets, tempo)
        drum_cycle = [l for l in DRUM_LANES if l in active_lanes]
        if drum_cycle:
            for i, onset_time in enumerate(drum_onsets):
                lane = drum_cycle[i % len(drum_cycle)]
                frame = time_to_frame(onset_time)
                all_notes.append((frame, lane))

    # Bass onsets -> lane A
    if 'bass' in stems:
        bass_onsets = get_onsets_for_stem(stems['bass'])
        bass_onsets = quantize_to_beat_grid(bass_onsets, tempo)
        bass_target = [l for l in BASS_LANES if l in active_lanes]
        if bass_target:
            for onset_time in bass_onsets:
                lane = bass_target[0]
                frame = time_to_frame(onset_time)
                all_notes.append((frame, lane))

    # Other/melody onsets -> lanes B, C
    if 'other' in stems:
        other_onsets = get_onsets_for_stem(stems['other'])
        other_onsets = quantize_to_beat_grid(other_onsets, tempo)
        other_cycle = [l for l in OTHER_LANES if l in active_lanes]
        if other_cycle:
            for i, onset_time in enumerate(other_onsets):
                lane = other_cycle[i % len(other_cycle)]
                frame = time_to_frame(onset_time)
                all_notes.append((frame, lane))

    # Filter to only active lanes (redundant but safe)
    all_notes = [(f, l) for f, l in all_notes if l in active_lanes]

    # Apply minimum gap filter
    all_notes = filter_by_min_gap(all_notes, min_gap)

    # Sort by frame
    all_notes.sort(key=lambda x: (x[0], x[1]))

    # Remove duplicate (same frame, same lane)
    seen = set()
    unique_notes = []
    for note in all_notes:
        if note not in seen:
            seen.add(note)
            unique_notes.append(note)
    all_notes = unique_notes

    print(f"[INFO]   Total notes generated: {len(all_notes)}")

    # Build output JSON
    chart_data = {
        "song_name": song_name,
        "tempo": round(tempo, 1),
        "duration": round(duration, 1),
        "difficulty": difficulty,
        "active_lanes": active_lanes,
        "total_notes": len(all_notes),
        "notes": [{"frame": f, "lane": l} for f, l in all_notes]
    }

    # Write JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as fp:
        json.dump(chart_data, fp, indent=2)

    print(f"[INFO]   Chart saved: {output_path}")
    return output_path


def generate_all_charts(stems_dir, song_name, output_dir):
    """
    Generate charts for all three difficulty levels.

    Args:
        stems_dir: Directory containing WAV stem files.
        song_name: Name of the song (used in filenames).
        output_dir: Directory for output JSON files.

    Returns:
        List of output file paths.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[INFO] === Generating all charts for: {song_name} ===")

    results = []
    for difficulty in ['easy', 'normal', 'hard']:
        filename = f"{song_name}_{difficulty}.json"
        output_path = output_dir / filename

        result = generate_chart(stems_dir, song_name, difficulty, output_path)
        if result:
            results.append(result)

    print(f"\n[INFO] Charts generated: {len(results)}/3")
    for path in results:
        print(f"[INFO]   {path.name}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate rhythm game note charts from audio stems"
    )
    parser.add_argument("stems_dir", help="Directory containing WAV stem files")
    parser.add_argument("song_name", help="Name of the song")
    parser.add_argument("output_dir", help="Output directory for chart JSON files")
    parser.add_argument(
        "--difficulty", choices=['easy', 'normal', 'hard', 'all'],
        default='all', help="Difficulty level (default: all)"
    )

    args = parser.parse_args()

    if args.difficulty == 'all':
        results = generate_all_charts(args.stems_dir, args.song_name, args.output_dir)
        if not results:
            print("[ERROR] No charts were generated")
            sys.exit(1)
    else:
        filename = f"{args.song_name}_{args.difficulty}.json"
        output_path = Path(args.output_dir) / filename
        result = generate_chart(
            args.stems_dir, args.song_name, args.difficulty, output_path
        )
        if not result:
            print("[ERROR] Chart generation failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
