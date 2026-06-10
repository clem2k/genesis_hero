#!/usr/bin/env python3
"""
midi_processor.py - Clean up MIDI files for Mega Drive constraints.

Processes MIDI files to fit within the YM2612/SN76489 hardware limitations:
- Quantize notes to 1/16th note grid
- Limit polyphony to 1 voice per channel (FM channels are monophonic)
- Map instruments to Mega Drive channels
- Clip note range to MIDI 24-96 (C1-C7)
- Remove very short notes
"""

import os
import sys
import argparse
import copy
from pathlib import Path

try:
    import pretty_midi
except ImportError:
    print("[ERROR] pretty_midi not installed. Install with: pip install pretty_midi")
    sys.exit(1)


# Mega Drive constraints
MIN_MIDI_NOTE = 24   # C1
MAX_MIDI_NOTE = 96   # C7
MIN_NOTE_DURATION = 0.03  # 30ms minimum note length
MAX_FM_CHANNELS = 5  # YM2612 has 6 FM channels, reserve one for DAC
MAX_PSG_CHANNELS = 3  # SN76489 has 3 tone + 1 noise

# General MIDI program ranges for instrument classification
BASS_PROGRAMS = list(range(32, 40))  # Electric Bass, Acoustic Bass, etc.
LEAD_PROGRAMS = list(range(80, 88))  # Square Lead, Sawtooth, etc.
PAD_PROGRAMS = list(range(88, 96))   # Pad sounds
KEYS_PROGRAMS = list(range(0, 8)) + list(range(8, 16))  # Piano + Chromatic Percussion


def quantize_time(time_sec, tempo, resolution=16):
    """
    Quantize a time value to the nearest 1/Nth note grid position.

    Args:
        time_sec: Time in seconds.
        tempo: Tempo in BPM.
        resolution: Grid resolution (16 = 1/16th note).

    Returns:
        Quantized time in seconds.
    """
    if tempo <= 0:
        return time_sec

    # Duration of one grid unit in seconds
    beat_duration = 60.0 / tempo
    grid_duration = beat_duration / (resolution / 4.0)

    if grid_duration <= 0:
        return time_sec

    # Snap to nearest grid point
    grid_index = round(time_sec / grid_duration)
    return grid_index * grid_duration


def clip_note_pitch(pitch, min_midi=MIN_MIDI_NOTE, max_midi=MAX_MIDI_NOTE):
    """
    Clip a MIDI pitch to the valid range.

    Args:
        pitch: MIDI note number.
        min_midi: Minimum MIDI note (default C1=24).
        max_midi: Maximum MIDI note (default C7=96).

    Returns:
        Clipped pitch, or None if note should be removed.
    """
    if pitch < min_midi or pitch > max_midi:
        # Transpose by octaves to fit
        while pitch < min_midi:
            pitch += 12
        while pitch > max_midi:
            pitch -= 12
        # If still out of range after transposition
        if pitch < min_midi or pitch > max_midi:
            return None
    return pitch


def limit_polyphony(notes, max_voices=1):
    """
    Limit polyphony to max_voices simultaneous notes.
    When notes overlap, keep the one with highest velocity.

    Args:
        notes: List of pretty_midi.Note objects.
        max_voices: Maximum simultaneous voices.

    Returns:
        Filtered list of notes with limited polyphony.
    """
    if not notes or max_voices < 1:
        return notes

    # Sort by start time, then by velocity (descending)
    sorted_notes = sorted(notes, key=lambda n: (n.start, -n.velocity))
    result = []
    active_ends = []  # Track end times of active notes

    for note in sorted_notes:
        # Remove expired notes from active list
        active_ends = [end for end in active_ends if end > note.start]

        if len(active_ends) < max_voices:
            result.append(note)
            active_ends.append(note.end)
            active_ends.sort()
        # else: skip this note (too much polyphony)

    return result


def classify_instrument(instrument):
    """
    Classify a MIDI instrument for Mega Drive channel assignment.

    Returns: 'bass', 'lead', 'pad', 'keys', 'drums', or 'other'
    """
    if instrument.is_drum:
        return 'drums'

    name = (instrument.name or '').lower()
    program = instrument.program

    # Check name first
    if 'bass' in name:
        return 'bass'
    if 'lead' in name or 'melody' in name:
        return 'lead'
    if 'pad' in name:
        return 'pad'
    if 'drum' in name or 'perc' in name:
        return 'drums'

    # Check program number
    if program in BASS_PROGRAMS:
        return 'bass'
    if program in LEAD_PROGRAMS:
        return 'lead'
    if program in PAD_PROGRAMS:
        return 'pad'
    if program in KEYS_PROGRAMS:
        return 'keys'

    return 'other'


def process_midi(input_path, output_path, max_fm_channels=MAX_FM_CHANNELS):
    """
    Process a MIDI file for Mega Drive compatibility.

    Args:
        input_path: Path to input MIDI file.
        output_path: Path for output MIDI file.
        max_fm_channels: Maximum FM channels to use (default 5).

    Returns:
        Path to output file on success, None on failure.
    """
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    if not input_path.exists():
        print(f"[ERROR] Input MIDI not found: {input_path}")
        return None

    print(f"[INFO] Processing MIDI: {input_path.name}")

    try:
        midi = pretty_midi.PrettyMIDI(str(input_path))
    except Exception as e:
        print(f"[ERROR] Failed to load MIDI: {e}")
        return None

    # Get tempo estimate
    tempo_changes = midi.get_tempo_changes()
    if len(tempo_changes[1]) > 0:
        tempo = tempo_changes[1][0]
    else:
        tempo = 120.0
    print(f"[INFO] Detected tempo: {tempo:.1f} BPM")

    total_notes_before = sum(len(inst.notes) for inst in midi.instruments)
    total_removed = 0

    # Process each instrument
    for inst in midi.instruments:
        if not inst.notes:
            continue

        notes_before = len(inst.notes)
        processed_notes = []

        for note in inst.notes:
            # Quantize timing
            note.start = quantize_time(note.start, tempo, 16)
            note.end = quantize_time(note.end, tempo, 16)

            # Ensure minimum duration
            if note.end - note.start < MIN_NOTE_DURATION:
                continue

            # Clip pitch
            clipped_pitch = clip_note_pitch(note.pitch)
            if clipped_pitch is None:
                continue
            note.pitch = clipped_pitch

            processed_notes.append(note)

        # Limit polyphony to 1 voice (monophonic for FM)
        if not inst.is_drum:
            processed_notes = limit_polyphony(processed_notes, max_voices=1)

        removed = notes_before - len(processed_notes)
        total_removed += removed
        inst.notes = processed_notes

        print(f"[INFO]   {inst.name or 'Track'}: {notes_before} -> {len(processed_notes)} notes ({removed} removed)")

    # Save processed MIDI
    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output_path))

    total_notes_after = sum(len(inst.notes) for inst in midi.instruments)
    print(f"[INFO] Processing complete: {total_notes_before} -> {total_notes_after} notes")
    print(f"[INFO] Output: {output_path}")
    return output_path


def merge_stems_midi(midi_paths_dict, output_path):
    """
    Merge separate stem MIDI files into one MIDI with proper channel assignments.

    Args:
        midi_paths_dict: Dict like {'bass': 'bass.mid', 'drums': 'drums.mid', 'other': 'other.mid'}
        output_path: Path for output merged MIDI file.

    Returns:
        Path to output file on success, None on failure.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Merging MIDI stems into: {output_path.name}")

    # Channel assignments for Mega Drive
    # FM Channel 0: Bass
    # FM Channel 1-3: Lead/Other
    # Channel 9: Drums (GM percussion)
    channel_map = {
        'bass':  {'channel': 0, 'program': 33, 'is_drum': False, 'name': 'Bass (FM Ch0)'},
        'other': {'channel': 1, 'program': 80, 'is_drum': False, 'name': 'Lead (FM Ch1)'},
        'drums': {'channel': 9, 'program': 0,  'is_drum': True,  'name': 'Drums (PSG)'},
    }

    # Create new MIDI
    merged = pretty_midi.PrettyMIDI(initial_tempo=120.0)

    for stem_name, midi_path in midi_paths_dict.items():
        midi_path = Path(midi_path).resolve()
        if not midi_path.exists():
            print(f"[INFO] Stem MIDI not found, skipping: {stem_name} ({midi_path})")
            continue

        print(f"[INFO]   Loading stem: {stem_name} <- {midi_path.name}")

        try:
            stem_midi = pretty_midi.PrettyMIDI(str(midi_path))
        except Exception as e:
            print(f"[ERROR]   Failed to load {midi_path.name}: {e}")
            continue

        # Get channel config
        config = channel_map.get(stem_name, {
            'channel': 2, 'program': 80, 'is_drum': False, 'name': f'{stem_name} (FM)'
        })

        # Create instrument for this stem
        instrument = pretty_midi.Instrument(
            program=config['program'],
            is_drum=config['is_drum'],
            name=config['name']
        )

        # Copy all notes from all tracks in the stem MIDI
        for inst in stem_midi.instruments:
            for note in inst.notes:
                instrument.notes.append(pretty_midi.Note(
                    velocity=note.velocity,
                    pitch=note.pitch,
                    start=note.start,
                    end=note.end
                ))

        note_count = len(instrument.notes)
        print(f"[INFO]   {stem_name}: {note_count} notes -> channel {config['channel']}")
        merged.instruments.append(instrument)

    # Save merged MIDI
    merged.write(str(output_path))
    total_notes = sum(len(inst.notes) for inst in merged.instruments)
    print(f"[INFO] Merged MIDI saved: {output_path} ({total_notes} total notes)")

    # Process the merged result for Mega Drive constraints
    processed_path = output_path.parent / f"{output_path.stem}_processed.mid"
    result = process_midi(output_path, processed_path)

    if result:
        # Replace merged with processed version
        import shutil
        shutil.move(str(processed_path), str(output_path))
        print(f"[INFO] Processed merged MIDI saved: {output_path}")
        return output_path
    else:
        print(f"[INFO] Using unprocessed merged MIDI: {output_path}")
        return output_path


def separate_midi_file(input_midi_path, output_dir):
    """
    Separate a multi-track MIDI file into stem MIDI files (drums, bass, other)
    based on instrument classifications.

    Args:
        input_midi_path: Path to input MIDI file.
        output_dir: Directory to save separate MIDI files.

    Returns:
        Dict with paths: {'drums': path, 'bass': path, 'other': path}
    """
    input_midi_path = Path(input_midi_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Separating MIDI tracks: {input_midi_path.name}")

    try:
        midi_data = pretty_midi.PrettyMIDI(str(input_midi_path))
    except Exception as e:
        print(f"[ERROR] Failed to load MIDI for separation: {e}")
        return None

    # Get tempo
    tempo_changes = midi_data.get_tempo_changes()
    tempo = tempo_changes[1][0] if len(tempo_changes[1]) > 0 else 120.0

    # Group instruments by classification
    grouped = {'drums': [], 'bass': [], 'other': []}

    for inst in midi_data.instruments:
        classification = classify_instrument(inst)
        if classification in ['lead', 'pad', 'keys', 'other']:
            grouped['other'].append(inst)
        elif classification == 'bass':
            grouped['bass'].append(inst)
        elif classification == 'drums':
            grouped['drums'].append(inst)

    results = {}
    
    # Save each group that has instruments
    for group_name, instruments in grouped.items():
        if not instruments:
            continue
            
        group_midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)
        for inst in instruments:
            # We copy the instrument to preserve program and notes
            new_inst = pretty_midi.Instrument(
                program=inst.program,
                is_drum=inst.is_drum,
                name=inst.name
            )
            new_inst.notes = copy.deepcopy(inst.notes)
            group_midi.instruments.append(new_inst)
            
        out_path = output_dir / f"{group_name}.mid"
        group_midi.write(str(out_path))
        results[group_name] = out_path
        print(f"[INFO]   Extracted stem: {group_name} ({len(instruments)} tracks) -> {out_path.name}")
        
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Process MIDI files for Mega Drive constraints"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Process single file
    process_parser = subparsers.add_parser("process", help="Process a single MIDI file")
    process_parser.add_argument("input", help="Input MIDI file")
    process_parser.add_argument("output", help="Output MIDI file")
    process_parser.add_argument(
        "--max-channels", type=int, default=MAX_FM_CHANNELS,
        help=f"Maximum FM channels (default: {MAX_FM_CHANNELS})"
    )

    # Merge stems
    merge_parser = subparsers.add_parser("merge", help="Merge stem MIDI files")
    merge_parser.add_argument("--bass", help="Bass MIDI file")
    merge_parser.add_argument("--drums", help="Drums MIDI file")
    merge_parser.add_argument("--other", help="Other/melody MIDI file")
    merge_parser.add_argument("-o", "--output", required=True, help="Output MIDI file")

    # Separate tracks
    separate_parser = subparsers.add_parser("separate", help="Separate a MIDI file into stems")
    separate_parser.add_argument("input", help="Input MIDI file")
    separate_parser.add_argument("output_dir", help="Output directory for stems")

    args = parser.parse_args()

    if args.command == "process":
        result = process_midi(args.input, args.output, args.max_channels)
        if not result:
            sys.exit(1)
    elif args.command == "merge":
        midi_paths = {}
        if args.bass:
            midi_paths['bass'] = args.bass
        if args.drums:
            midi_paths['drums'] = args.drums
        if args.other:
            midi_paths['other'] = args.other

        if not midi_paths:
            print("[ERROR] At least one stem MIDI file must be provided")
            sys.exit(1)

        result = merge_stems_midi(midi_paths, args.output)
        if not result:
            sys.exit(1)
    elif args.command == "separate":
        result = separate_midi_file(args.input, args.output_dir)
        if not result:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
