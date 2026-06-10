#!/usr/bin/env python3
"""
chart_to_header.py - Convert JSON note charts to C header files for SGDK.

Takes a directory of chart JSON files (song_0_easy.json, song_0_normal.json,
song_0_hard.json, etc.) and generates a single C header file with note data
arrays, song metadata, and a lookup table for use in the Genesis Hero game.
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path


DIFFICULTY_ORDER = ['easy', 'normal', 'hard']
DIFFICULTY_NAMES = {
    'easy': 'EASY',
    'normal': 'NORMAL',
    'hard': 'HARD'
}


def _sanitize_c_identifier(name):
    """Sanitize a string for use as a C identifier."""
    # Replace non-alphanumeric with underscore
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Remove leading digits
    name = re.sub(r'^[0-9]+', '', name)
    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name)
    # Remove trailing underscores
    name = name.strip('_')
    return name or 'unnamed'


def _escape_c_string(s):
    """Escape a string for use in a C string literal."""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _load_chart(path):
    """Load a chart JSON file and return its data, or None on error."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[ERROR] Failed to load chart: {path}: {e}")
        return None


def _discover_songs(charts_dir):
    """
    Scan a directory for chart JSON files and group them by song.

    Expects filenames like: song_0_easy.json, song_0_normal.json, song_0_hard.json

    Returns:
        List of dicts, each with:
        {
            'identifier': 'song_0',
            'charts': {'easy': data, 'normal': data, 'hard': data}
        }
        Sorted by identifier.
    """
    charts_dir = Path(charts_dir)

    if not charts_dir.exists():
        print(f"[ERROR] Charts directory not found: {charts_dir}")
        return []

    # Find all JSON files
    json_files = sorted(charts_dir.glob("*.json"))

    if not json_files:
        print(f"[ERROR] No JSON files found in: {charts_dir}")
        return []

    print(f"[INFO] Found {len(json_files)} JSON files in {charts_dir}")

    # Group by song identifier
    songs = {}

    for json_path in json_files:
        filename = json_path.stem  # e.g., "song_0_easy"

        # Try to extract difficulty suffix
        matched = False
        for diff in DIFFICULTY_ORDER:
            suffix = f"_{diff}"
            if filename.endswith(suffix):
                identifier = filename[:-len(suffix)]
                chart_data = _load_chart(json_path)
                if chart_data is not None:
                    if identifier not in songs:
                        songs[identifier] = {'identifier': identifier, 'charts': {}}
                    songs[identifier]['charts'][diff] = chart_data
                    print(f"[INFO]   {json_path.name} -> song='{identifier}', difficulty='{diff}'")
                matched = True
                break

        if not matched:
            print(f"[INFO]   Skipping (no difficulty suffix): {json_path.name}")

    # Sort by identifier
    result = sorted(songs.values(), key=lambda s: s['identifier'])
    print(f"[INFO] Discovered {len(result)} songs")
    return result


def generate_header(charts_dir, output_path):
    """
    Generate a C header file from chart JSON files.

    Args:
        charts_dir: Directory containing chart JSON files.
        output_path: Path for output .h file.

    Returns:
        Path to output file on success, None on failure.
    """
    charts_dir = Path(charts_dir).resolve()
    output_path = Path(output_path).resolve()

    songs = _discover_songs(charts_dir)

    if not songs:
        print("[ERROR] No songs found to generate header")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # ── Header guard and includes ──
    lines.append("#ifndef _SONG_DATA_H_")
    lines.append("#define _SONG_DATA_H_")
    lines.append("")
    lines.append("#include <genesis.h>")
    lines.append("")

    # ── Global defines ──
    lines.append(f"#define SONG_COUNT {len(songs)}")
    lines.append("#define DIFFICULTY_EASY 0")
    lines.append("#define DIFFICULTY_NORMAL 1")
    lines.append("#define DIFFICULTY_HARD 2")
    lines.append("#define DIFFICULTY_COUNT 3")
    lines.append("")

    # ── Per-song data ──
    for song_idx, song in enumerate(songs):
        identifier = song['identifier']
        charts = song['charts']

        # Get song name from any available chart
        song_name = identifier
        tempo = 120
        duration = 0

        for diff in DIFFICULTY_ORDER:
            if diff in charts:
                chart = charts[diff]
                song_name = chart.get('song_name', identifier)
                tempo = int(chart.get('tempo', 120))
                duration = int(chart.get('duration', 0))
                break

        # Split into Title and Artist if " - " exists
        parts = song_name.split(" - ", 1)
        if len(parts) == 2:
            artist_val = parts[0]
            title_val = parts[1]
        else:
            artist_val = "Unknown"
            title_val = song_name

        safe_title = _escape_c_string(title_val)
        safe_artist = _escape_c_string(artist_val)

        lines.append(f"// Song {song_idx}: {song_name}")
        lines.append(f'#define SONG_{song_idx}_NAME "{safe_title}"')
        lines.append(f'#define SONG_{song_idx}_ARTIST "{safe_artist}"')
        lines.append(f"#define SONG_{song_idx}_TEMPO {tempo}")
        lines.append(f"#define SONG_{song_idx}_DURATION {duration}")
        lines.append("")

        # Generate data for each difficulty
        for diff in DIFFICULTY_ORDER:
            diff_upper = DIFFICULTY_NAMES[diff]

            if diff in charts:
                chart = charts[diff]
                notes = chart.get('notes', [])
                active_lanes = chart.get('active_lanes', [])
            else:
                # Missing difficulty — generate empty placeholder
                notes = []
                active_lanes = []
                print(f"[INFO]   Song {song_idx} missing {diff} chart, generating empty")

            # Note data array
            note_count = len(notes)
            if note_count == 0:
                # C doesn't allow empty arrays, use a dummy entry
                lines.append(f"const u16 song_{song_idx}_{diff}_notes[][2] = {{")
                lines.append("    {0, 0}")
                lines.append("};")
            else:
                lines.append(f"const u16 song_{song_idx}_{diff}_notes[][2] = {{")
                note_entries = []
                for note in notes:
                    frame = note.get('frame', 0)
                    lane = note.get('lane', 0)
                    note_entries.append(f"    {{{frame}, {lane}}}")
                lines.append(",\n".join(note_entries))
                lines.append("};")

            lines.append(f"#define SONG_{song_idx}_{diff_upper}_COUNT {note_count}")

            # Active lanes array
            if not active_lanes:
                lines.append(f"const u8 song_{song_idx}_{diff}_lanes[] = {{0}};")
                lines.append(f"#define SONG_{song_idx}_{diff_upper}_LANE_COUNT 0")
            else:
                lanes_csv = ", ".join(str(l) for l in active_lanes)
                lines.append(f"const u8 song_{song_idx}_{diff}_lanes[] = {{{lanes_csv}}};")
                lines.append(f"#define SONG_{song_idx}_{diff_upper}_LANE_COUNT {len(active_lanes)}")

            lines.append("")

    # ── SongData struct ──
    lines.append("// Song data structure")
    lines.append("typedef struct {")
    lines.append("    const char* name;")
    lines.append("    const char* artist;")
    lines.append("    u16 tempo;")
    lines.append("    u16 duration;")
    lines.append("    const u8* music;")
    lines.append("    const u16 (*notes[DIFFICULTY_COUNT])[][2];")
    lines.append("    const u16 note_counts[DIFFICULTY_COUNT];")
    lines.append("    const u8* active_lanes[DIFFICULTY_COUNT];")
    lines.append("    const u8 lane_counts[DIFFICULTY_COUNT];")
    lines.append("} SongData;")
    lines.append("")

    # ── Songs table ──
    lines.append(f"static const SongData songs[SONG_COUNT] = {{")

    for song_idx, song in enumerate(songs):
        identifier = song['identifier']
        # Note arrays
        notes_refs = []
        counts_refs = []
        lanes_refs = []
        lane_counts_refs = []

        for diff in DIFFICULTY_ORDER:
            diff_upper = DIFFICULTY_NAMES[diff]
            notes_refs.append(f"(const u16(*)[][2])song_{song_idx}_{diff}_notes")
            counts_refs.append(f"SONG_{song_idx}_{diff_upper}_COUNT")
            lanes_refs.append(f"song_{song_idx}_{diff}_lanes")
            lane_counts_refs.append(f"SONG_{song_idx}_{diff_upper}_LANE_COUNT")

        lines.append("    {")
        lines.append(f"        SONG_{song_idx}_NAME, SONG_{song_idx}_ARTIST, SONG_{song_idx}_TEMPO, SONG_{song_idx}_DURATION,")
        lines.append(f"        song_{song_idx},")
        lines.append(f"        {{{', '.join(notes_refs)}}},")
        lines.append(f"        {{{', '.join(counts_refs)}}},")
        lines.append(f"        {{{', '.join(lanes_refs)}}},")
        lines.append(f"        {{{', '.join(lane_counts_refs)}}}")

        if song_idx < len(songs) - 1:
            lines.append("    },")
        else:
            lines.append("    }")

    lines.append("};")
    lines.append("")
    lines.append("#endif // _SONG_DATA_H_")
    lines.append("")

    # ── Write output ──
    header_content = "\n".join(lines)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header_content)

    print(f"[INFO] Header generated: {output_path}")
    print(f"[INFO]   Songs: {len(songs)}")
    print(f"[INFO]   Size: {len(header_content)} bytes")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert JSON note charts to C header file for SGDK"
    )
    parser.add_argument("charts_dir", help="Directory containing chart JSON files")
    parser.add_argument("output", help="Output C header file (.h)")

    args = parser.parse_args()

    result = generate_header(args.charts_dir, args.output)
    if not result:
        print("[ERROR] Header generation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
