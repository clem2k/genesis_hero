#!/usr/bin/env python3
"""
vgm_generator.py - Generate VGM files from processed MIDI for YM2612 + SN76489.

The most complex tool in the Genesis Hero pipeline. Converts processed MIDI
into VGM (Video Game Music) format that can be played on real Mega Drive
hardware via the YM2612 FM synth and SN76489 PSG chips.

VGM format reference: https://vgmrips.net/wiki/VGM_Specification
YM2612 register reference: https://www.smspower.org/maxim/Documents/YM2612

Port 0 (0x52): FM channels 1-3 (offsets 0,1,2)
Port 1 (0x53): FM channels 4-6 (offsets 0,1,2)
"""

import os
import sys
import struct
import argparse
from pathlib import Path

try:
    import pretty_midi
except ImportError:
    print("[ERROR] pretty_midi not installed. Install with: pip install pretty_midi")
    sys.exit(1)


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

YM2612_CLOCK = 7670453     # NTSC YM2612 master clock (Hz)
SN76489_CLOCK = 3579545    # SN76489 PSG clock (Hz)
VGM_SAMPLE_RATE = 44100    # VGM sample rate
SAMPLES_PER_FRAME = 735    # 44100 / 60 = 735 samples per NTSC frame

# Operator register offsets within YM2612
# Operator order: Op1=0x00, Op3=0x04, Op2=0x08, Op4=0x0C
OP_OFFSETS = [0x00, 0x08, 0x04, 0x0C]  # Op1, Op2, Op3, Op4 (logical order)

# Key on/off channel mapping for register 0x28
# ch_num: 0=Ch1, 1=Ch2, 2=Ch3, 4=Ch4, 5=Ch5, 6=Ch6
KEY_CH_MAP = [0, 1, 2, 4, 5, 6]


# ──────────────────────────────────────────────
# FM Patches
# ──────────────────────────────────────────────

FM_PATCHES = {
    'BASS_SYNTH': {
        'algo': 4, 'fb': 5,
        'operators': [
            {'dt': 0, 'mul': 1, 'tl': 30, 'rs': 1, 'ar': 31, 'am': 0, 'd1r': 10, 'd2r': 3, 'd1l': 5, 'rr': 6},
            {'dt': 0, 'mul': 2, 'tl': 0,  'rs': 1, 'ar': 31, 'am': 0, 'd1r': 8,  'd2r': 2, 'd1l': 3, 'rr': 6},
            {'dt': 0, 'mul': 1, 'tl': 35, 'rs': 1, 'ar': 28, 'am': 0, 'd1r': 12, 'd2r': 4, 'd1l': 6, 'rr': 7},
            {'dt': 0, 'mul': 1, 'tl': 0,  'rs': 1, 'ar': 31, 'am': 0, 'd1r': 6,  'd2r': 2, 'd1l': 2, 'rr': 5},
        ]
    },
    'LEAD_BRIGHT': {
        'algo': 5, 'fb': 6,
        'operators': [
            {'dt': 3, 'mul': 1, 'tl': 25, 'rs': 2, 'ar': 31, 'am': 0, 'd1r': 8,  'd2r': 2, 'd1l': 2, 'rr': 8},
            {'dt': 0, 'mul': 1, 'tl': 0,  'rs': 2, 'ar': 31, 'am': 0, 'd1r': 10, 'd2r': 3, 'd1l': 3, 'rr': 7},
            {'dt': 7, 'mul': 2, 'tl': 28, 'rs': 2, 'ar': 31, 'am': 0, 'd1r': 9,  'd2r': 3, 'd1l': 4, 'rr': 8},
            {'dt': 0, 'mul': 1, 'tl': 0,  'rs': 2, 'ar': 31, 'am': 0, 'd1r': 12, 'd2r': 4, 'd1l': 3, 'rr': 7},
        ]
    },
    'PAD_SOFT': {
        'algo': 7, 'fb': 3,
        'operators': [
            {'dt': 0, 'mul': 1, 'tl': 10, 'rs': 0, 'ar': 20, 'am': 0, 'd1r': 5, 'd2r': 1, 'd1l': 1, 'rr': 4},
            {'dt': 0, 'mul': 4, 'tl': 15, 'rs': 0, 'ar': 18, 'am': 0, 'd1r': 6, 'd2r': 2, 'd1l': 2, 'rr': 4},
            {'dt': 0, 'mul': 1, 'tl': 12, 'rs': 0, 'ar': 22, 'am': 0, 'd1r': 4, 'd2r': 1, 'd1l': 1, 'rr': 4},
            {'dt': 0, 'mul': 2, 'tl': 8,  'rs': 0, 'ar': 20, 'am': 0, 'd1r': 5, 'd2r': 2, 'd1l': 2, 'rr': 5},
        ]
    },
    'KEYS_PLUCK': {
        'algo': 0, 'fb': 7,
        'operators': [
            {'dt': 3, 'mul': 1, 'tl': 35, 'rs': 2, 'ar': 31, 'am': 0, 'd1r': 18, 'd2r': 8,  'd1l': 8,  'rr': 10},
            {'dt': 0, 'mul': 2, 'tl': 30, 'rs': 2, 'ar': 31, 'am': 0, 'd1r': 15, 'd2r': 6,  'd1l': 6,  'rr': 9},
            {'dt': 7, 'mul': 1, 'tl': 25, 'rs': 2, 'ar': 31, 'am': 0, 'd1r': 20, 'd2r': 10, 'd1l': 10, 'rr': 11},
            {'dt': 0, 'mul': 1, 'tl': 0,  'rs': 2, 'ar': 31, 'am': 0, 'd1r': 14, 'd2r': 5,  'd1l': 4,  'rr': 8},
        ]
    },
}


# ──────────────────────────────────────────────
# VGM Writer
# ──────────────────────────────────────────────

class VGMWriter:
    """Builds a VGM file by accumulating register writes and wait commands."""

    def __init__(self):
        self.data = bytearray()    # Command stream
        self.total_samples = 0
        self.loop_offset = None
        self.loop_samples = 0

    # ── YM2612 ──

    def ym2612_write_port0(self, register, value):
        """Write to YM2612 Port 0 (FM channels 1-3, ch offset 0,1,2)."""
        self.data.extend([0x52, register & 0xFF, value & 0xFF])

    def ym2612_write_port1(self, register, value):
        """Write to YM2612 Port 1 (FM channels 4-6, ch offset 0,1,2)."""
        self.data.extend([0x53, register & 0xFF, value & 0xFF])

    def ym2612_write(self, channel, register, value):
        """
        Write to the appropriate port based on channel index (0-5).

        Channels 0-2 use Port 0, channels 3-5 use Port 1.
        The register address is offset by (channel % 3).
        """
        ch_offset = channel % 3
        if channel < 3:
            self.ym2612_write_port0(register + ch_offset, value)
        else:
            self.ym2612_write_port1(register + ch_offset, value)

    # ── SN76489 (PSG) ──

    def sn76489_write(self, value):
        """Write a byte to the SN76489 PSG."""
        self.data.extend([0x50, value & 0xFF])

    def psg_set_tone(self, channel, frequency):
        """
        Set PSG tone channel frequency.

        Args:
            channel: PSG channel (0-2 for tone, 3 for noise).
            frequency: Frequency in Hz.
        """
        if frequency <= 0:
            return
        # PSG frequency divider: clock / (32 * freq)
        divider = int(round(SN76489_CLOCK / (32.0 * frequency)))
        divider = max(1, min(1023, divider))

        freq_low4 = divider & 0x0F
        freq_high6 = (divider >> 4) & 0x3F

        # Latch byte: 1 | (ch << 5) | (type << 4) | data
        # type=0 for tone
        self.sn76489_write(0x80 | (channel << 5) | freq_low4)
        self.sn76489_write(freq_high6)

    def psg_set_volume(self, channel, attenuation):
        """
        Set PSG channel volume.

        Args:
            channel: PSG channel (0-3).
            attenuation: 0=max volume, 15=silent.
        """
        attenuation = max(0, min(15, attenuation))
        self.sn76489_write(0x90 | (channel << 5) | attenuation)

    def psg_set_noise(self, mode, rate):
        """
        Set PSG noise channel.

        Args:
            mode: 0=periodic, 1=white noise.
            rate: 0-3 (shift rate).
        """
        self.sn76489_write(0xE0 | ((mode & 0x01) << 2) | (rate & 0x03))

    # ── Wait commands ──

    def wait_samples(self, samples):
        """Add wait command(s) for N samples."""
        if samples <= 0:
            return
        self.total_samples += samples

        while samples > 0:
            if samples == 735:
                self.data.append(0x62)  # Exactly 1 NTSC frame
                samples = 0
            elif samples == 882:
                self.data.append(0x63)  # Exactly 1 PAL frame
                samples = 0
            elif samples <= 16:
                # Short wait: 0x7n = wait n+1 samples (n=0..15 -> 1..16 samples)
                self.data.append(0x70 | ((samples - 1) & 0x0F))
                samples = 0
            elif samples >= 735:
                # Use NTSC frame waits for bulk
                num_frames = samples // 735
                for _ in range(num_frames):
                    self.data.append(0x62)
                samples -= num_frames * 735
            else:
                # Generic wait: 0x61 nn nn (16-bit LE)
                wait = min(samples, 65535)
                self.data.extend([0x61, wait & 0xFF, (wait >> 8) & 0xFF])
                samples -= wait

    def wait_frame(self):
        """Wait exactly one NTSC frame (735 samples)."""
        self.data.append(0x62)
        self.total_samples += 735

    # ── Control ──

    def end(self):
        """Write end-of-data command."""
        self.data.append(0x66)

    def set_loop_point(self):
        """Mark the current position as the loop start point."""
        self.loop_offset = len(self.data)
        self.loop_samples = self.total_samples

    # ── File output ──

    def save(self, output_path):
        """Save the complete VGM file with header."""
        self.end()
        header = self._build_header()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'wb') as f:
            f.write(header)
            f.write(self.data)

        print(f"[INFO] VGM file written: {output_path}")
        print(f"[INFO]   Data size: {len(self.data)} bytes")
        print(f"[INFO]   Total size: {len(header) + len(self.data)} bytes")

    def _build_header(self):
        """Build the 256-byte VGM header."""
        header = bytearray(256)

        # 0x00: "Vgm " magic
        header[0:4] = b'Vgm '

        # 0x04: End of file offset (relative to offset 0x04)
        eof_offset = 256 + len(self.data) - 4
        struct.pack_into('<I', header, 0x04, eof_offset)

        # 0x08: Version number (1.50 = 0x00000150)
        struct.pack_into('<I', header, 0x08, 0x00000150)

        # 0x0C: SN76489 clock
        struct.pack_into('<I', header, 0x0C, SN76489_CLOCK)

        # 0x10: YM2413 clock (0 = not used)
        struct.pack_into('<I', header, 0x10, 0)

        # 0x14: GD3 offset (0 = no GD3 tag)
        struct.pack_into('<I', header, 0x14, 0)

        # 0x18: Total # samples
        struct.pack_into('<I', header, 0x18, self.total_samples)

        # 0x1C: Loop offset (relative to 0x1C)
        if self.loop_offset is not None:
            loop_abs = 256 + self.loop_offset
            struct.pack_into('<I', header, 0x1C, loop_abs - 0x1C)
        else:
            struct.pack_into('<I', header, 0x1C, 0)

        # 0x20: Loop # samples
        if self.loop_offset is not None:
            struct.pack_into('<I', header, 0x20, self.total_samples - self.loop_samples)
        else:
            struct.pack_into('<I', header, 0x20, 0)

        # 0x24: Rate (0 for default)
        struct.pack_into('<I', header, 0x24, 0)

        # 0x28: SN76489 feedback (0x0009 for Sega)
        struct.pack_into('<H', header, 0x28, 0x0009)

        # 0x2A: SN76489 shift register width (16)
        header[0x2A] = 16

        # 0x2B: SN76489 flags
        header[0x2B] = 0

        # 0x2C: YM2612 clock
        struct.pack_into('<I', header, 0x2C, YM2612_CLOCK)

        # 0x34: VGM data offset (relative to 0x34)
        # Data starts at byte 256, so offset = 256 - 0x34 = 204
        struct.pack_into('<I', header, 0x34, 256 - 0x34)

        return bytes(header)


# ──────────────────────────────────────────────
# FM Synthesis helpers
# ──────────────────────────────────────────────

def midi_to_fnum_block(midi_note, clock=YM2612_CLOCK):
    """
    Convert a MIDI note number to YM2612 F-Number and Block.

    The YM2612 uses a frequency number (F-Number, 11 bits) and a block
    (octave, 3 bits) to set the output frequency.

    Formula: F-Number = (freq * 144 * 2^(21-block)) / clock

    Args:
        midi_note: MIDI note number (0-127).
        clock: YM2612 master clock in Hz.

    Returns:
        Tuple (fnum, block) where fnum is 0-2047 and block is 0-7.
    """
    freq = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    for block in range(8):
        fnum = int(round((freq * 144 * (2 ** (21 - block))) / clock))
        if 0 < fnum <= 2047:
            return fnum, block

    # Fallback: use highest block
    return 2047, 7


def load_fm_patch(patch_name):
    """
    Load an FM patch by name.

    Args:
        patch_name: Name of the patch (e.g., 'BASS_SYNTH').

    Returns:
        Patch dictionary with 'algo', 'fb', and 'operators' keys.
    """
    if patch_name in FM_PATCHES:
        return FM_PATCHES[patch_name]

    print(f"[ERROR] Unknown patch: {patch_name}, defaulting to BASS_SYNTH")
    return FM_PATCHES['BASS_SYNTH']


def program_fm_channel(vgm, channel, patch):
    """
    Program all registers for an FM channel with the given patch.

    Writes algorithm, feedback, stereo output, and all four operator
    parameters to the YM2612 via the VGM writer.

    Args:
        vgm: VGMWriter instance.
        channel: FM channel index (0-5).
        patch: Patch dictionary from FM_PATCHES.
    """
    # Algorithm and Feedback: register 0xB0+ch
    algo_fb = ((patch['fb'] & 0x07) << 3) | (patch['algo'] & 0x07)
    vgm.ym2612_write(channel, 0xB0, algo_fb)

    # Stereo output: L+R enabled, no LFO: register 0xB4+ch
    vgm.ym2612_write(channel, 0xB4, 0xC0)

    # Program each operator
    ch_offset = channel % 3
    port = 0 if channel < 3 else 1
    write_fn = vgm.ym2612_write_port0 if port == 0 else vgm.ym2612_write_port1

    for op_idx, op in enumerate(patch['operators']):
        op_off = OP_OFFSETS[op_idx]
        reg_base = op_off + ch_offset

        # 0x30: DT(3 bits) | MUL(4 bits)
        write_fn(0x30 + reg_base, ((op['dt'] & 0x07) << 4) | (op['mul'] & 0x0F))

        # 0x40: TL(7 bits) - Total Level (volume, 0=loudest, 127=silent)
        write_fn(0x40 + reg_base, op['tl'] & 0x7F)

        # 0x50: RS(2 bits) | AR(5 bits) - Rate Scaling | Attack Rate
        write_fn(0x50 + reg_base, ((op['rs'] & 0x03) << 6) | (op['ar'] & 0x1F))

        # 0x60: AM(1 bit) | D1R(5 bits) - AM Enable | First Decay Rate
        write_fn(0x60 + reg_base, ((op['am'] & 0x01) << 7) | (op['d1r'] & 0x1F))

        # 0x70: D2R(5 bits) - Second Decay Rate
        write_fn(0x70 + reg_base, op['d2r'] & 0x1F)

        # 0x80: D1L(4 bits) | RR(4 bits) - Sustain Level | Release Rate
        write_fn(0x80 + reg_base, ((op['d1l'] & 0x0F) << 4) | (op['rr'] & 0x0F))


def key_on(vgm, channel):
    """
    Send Key-On for an FM channel (all 4 operators).

    Register 0x28, value = 0xF0 | ch_num
    (Op4<<7 | Op3<<6 | Op2<<5 | Op1<<4) = 0xF0 = all operators on

    This register is always written to Port 0.
    """
    ch_num = KEY_CH_MAP[channel]
    vgm.ym2612_write_port0(0x28, 0xF0 | ch_num)


def key_off(vgm, channel):
    """
    Send Key-Off for an FM channel (all operators off).

    Register 0x28, value = 0x00 | ch_num
    """
    ch_num = KEY_CH_MAP[channel]
    vgm.ym2612_write_port0(0x28, 0x00 | ch_num)


def set_fm_frequency(vgm, channel, midi_note):
    """
    Set the frequency for an FM channel from a MIDI note number.

    Must write the high byte (0xA4) before the low byte (0xA0) because
    the high byte latches the complete frequency.

    Args:
        vgm: VGMWriter instance.
        channel: FM channel index (0-5).
        midi_note: MIDI note number.
    """
    fnum, block = midi_to_fnum_block(midi_note)

    freq_hi = ((block & 0x07) << 3) | ((fnum >> 8) & 0x07)
    freq_lo = fnum & 0xFF

    # High byte first (latches)
    vgm.ym2612_write(channel, 0xA4, freq_hi)
    vgm.ym2612_write(channel, 0xA0, freq_lo)


def silence_all(vgm):
    """
    Silence all FM and PSG channels.
    """
    # Key off all FM channels
    for ch in range(6):
        key_off(vgm, ch)

    # Silence all PSG channels
    for ch in range(4):
        vgm.psg_set_volume(ch, 15)  # 15 = silent


def assign_patch_for_instrument(inst, fm_channel):
    """
    Choose an FM patch based on MIDI instrument properties.

    Args:
        inst: pretty_midi.Instrument object.
        fm_channel: FM channel index being assigned.

    Returns:
        Patch name string.
    """
    name = (inst.name or '').lower()
    program = inst.program

    # Name-based matching
    if 'bass' in name:
        return 'BASS_SYNTH'
    if 'lead' in name or 'melody' in name:
        return 'LEAD_BRIGHT'
    if 'pad' in name:
        return 'PAD_SOFT'
    if 'key' in name or 'piano' in name or 'pluck' in name:
        return 'KEYS_PLUCK'

    # Program-based matching
    if program in range(32, 40):   # Bass
        return 'BASS_SYNTH'
    if program in range(80, 88):   # Lead
        return 'LEAD_BRIGHT'
    if program in range(88, 96):   # Pad
        return 'PAD_SOFT'
    if program in range(0, 16):    # Piano/Chromatic
        return 'KEYS_PLUCK'

    # Channel-based default
    defaults = ['BASS_SYNTH', 'LEAD_BRIGHT', 'PAD_SOFT', 'KEYS_PLUCK', 'LEAD_BRIGHT']
    return defaults[fm_channel % len(defaults)]


# ──────────────────────────────────────────────
# Main VGM generation
# ──────────────────────────────────────────────

def generate_vgm(midi_path, output_vgm_path):
    """
    Generate a VGM file from a processed MIDI file.

    The MIDI is read, instruments are assigned to FM channels with
    appropriate patches, and note events are converted to YM2612
    register writes with proper timing.

    Args:
        midi_path: Path to input MIDI file.
        output_vgm_path: Path for output VGM file.

    Returns:
        Path to output VGM file on success, None on failure.
    """
    midi_path = Path(midi_path).resolve()
    output_vgm_path = Path(output_vgm_path).resolve()

    if not midi_path.exists():
        print(f"[ERROR] MIDI file not found: {midi_path}")
        return None

    print(f"[INFO] Loading MIDI: {midi_path}")

    try:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    except Exception as e:
        print(f"[ERROR] Failed to load MIDI: {e}")
        return None

    vgm = VGMWriter()

    # Determine total duration
    total_time = midi.get_end_time()
    print(f"[INFO] MIDI duration: {total_time:.2f}s")

    # ── Assign instruments to FM channels ──
    channel_patches = {}
    channel_instruments = {}
    fm_channel = 0
    max_fm = 5  # Use channels 0-4, leave ch5 for DAC/spare

    for inst in midi.instruments:
        if inst.is_drum:
            print(f"[INFO] Skipping drum track: {inst.name or 'Unnamed'} (drums go to PSG)")
            continue
        if not inst.notes:
            continue
        if fm_channel >= max_fm:
            print(f"[INFO] Max FM channels reached, skipping: {inst.name or 'Unnamed'}")
            break

        patch_name = assign_patch_for_instrument(inst, fm_channel)
        channel_patches[fm_channel] = load_fm_patch(patch_name)
        channel_instruments[fm_channel] = inst
        print(f"[INFO] FM Channel {fm_channel}: '{inst.name or 'Unnamed'}' (prog={inst.program}) -> {patch_name}")
        fm_channel += 1

    if not channel_instruments:
        print("[ERROR] No melodic instruments found in MIDI")
        return None

    # ── Initialize: silence everything ──
    silence_all(vgm)

    # ── Program all channels with their patches ──
    for ch, patch in channel_patches.items():
        program_fm_channel(vgm, ch, patch)

    # ── Build sorted event list ──
    # Events: (time_sec, event_type, channel, pitch, velocity)
    events = []

    for ch, inst in channel_instruments.items():
        for note in inst.notes:
            # Clip pitch to valid range
            pitch = max(24, min(96, note.pitch))
            events.append((note.start, 'on', ch, pitch, note.velocity))
            events.append((note.end, 'off', ch, pitch, 0))

    # Sort: by time, then note-offs before note-ons at same time
    events.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))

    print(f"[INFO] Processing {len(events)} events across {len(channel_instruments)} channels")

    # ── Process events with sample-accurate timing ──
    current_sample = 0

    for time_sec, etype, ch, pitch, vel in events:
        target_sample = int(time_sec * VGM_SAMPLE_RATE)

        # Wait until the event time
        wait = target_sample - current_sample
        if wait > 0:
            vgm.wait_samples(wait)
            current_sample = target_sample

        if etype == 'on':
            set_fm_frequency(vgm, ch, pitch)
            key_on(vgm, ch)
        else:
            key_off(vgm, ch)

    # ── Finalize ──
    # Add a short silence at the end
    vgm.wait_samples(SAMPLES_PER_FRAME * 2)

    # Silence all channels
    silence_all(vgm)
    vgm.wait_samples(SAMPLES_PER_FRAME)

    # Save
    vgm.save(str(output_vgm_path))
    duration = vgm.total_samples / VGM_SAMPLE_RATE
    print(f"[INFO] VGM generation complete!")
    print(f"[INFO]   Total samples: {vgm.total_samples}")
    print(f"[INFO]   Duration: {duration:.2f}s")
    print(f"[INFO]   Output: {output_vgm_path}")

    return output_vgm_path


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate VGM files from MIDI for Mega Drive (YM2612 + SN76489)"
    )
    parser.add_argument("input", help="Input MIDI file (.mid)")
    parser.add_argument("output", help="Output VGM file (.vgm)")
    parser.add_argument(
        "--patch", choices=list(FM_PATCHES.keys()),
        help="Force a specific FM patch for all channels"
    )
    parser.add_argument(
        "--list-patches", action="store_true",
        help="List available FM patches and exit"
    )

    args = parser.parse_args()

    if args.list_patches:
        print("Available FM Patches:")
        for name, patch in FM_PATCHES.items():
            print(f"  {name}: algo={patch['algo']}, fb={patch['fb']}")
        sys.exit(0)

    result = generate_vgm(args.input, args.output)
    if not result:
        print("[ERROR] VGM generation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
