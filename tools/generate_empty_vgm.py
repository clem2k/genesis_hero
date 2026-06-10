import struct
from pathlib import Path

def create_empty_vgm(output_path):
    data = bytearray([0x66]) # Just the end command (0x66)
    header = bytearray(256)
    header[0:4] = b'Vgm '
    eof_offset = 256 + len(data) - 4
    struct.pack_into('<I', header, 0x04, eof_offset)
    struct.pack_into('<I', header, 0x08, 0x00000150) # Version 1.50
    struct.pack_into('<I', header, 0x0C, 3579545) # PSG Clock
    struct.pack_into('<I', header, 0x2C, 7670453) # YM2612 Clock
    struct.pack_into('<I', header, 0x34, 256 - 0x34) # Data offset
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(data)
    print(f"Created empty VGM at {output_path}")

if __name__ == '__main__':
    create_empty_vgm("res/music/song_0.vgm")
