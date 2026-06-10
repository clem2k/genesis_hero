#!/usr/bin/env python3
"""
generate_sprites.py - Generate all game sprites for Genesis Hero.

Creates 32x32px sprites with pixel-art volume, shading and highlights,
designed to look great on Mega Drive hardware (9-bit palette).

Sprites generated:
  - spr_notes.png:     5 note buttons (160x32), one per lane
  - spr_hitzone.png:   2 hitzone frames (64x32), idle + glow
  - spr_explosion.png: 4 explosion frames (128x32), hit feedback animation
"""

import os
import math
from PIL import Image, ImageDraw


# ── Mega Drive safe colors (snapped to 9-bit: 8 levels per channel) ──
# Each R/G/B can be: 0, 36, 73, 109, 146, 182, 219, 255

MAGENTA = (255, 0, 255)  # Transparency key

# Lane color palettes: (dark, mid, bright, highlight)
LANE_PALETTES = {
    'green':  ((0, 73, 0),    (0, 146, 0),   (0, 219, 0),   (109, 255, 109)),
    'blue':   ((0, 0, 109),   (0, 73, 219),  (0, 109, 255),  (109, 182, 255)),
    'yellow': ((146, 109, 0), (219, 182, 0),  (255, 219, 0),  (255, 255, 146)),
    'red':    ((109, 0, 0),   (219, 0, 0),    (255, 36, 36),  (255, 146, 109)),
    'purple': ((73, 0, 109),  (146, 0, 219),  (182, 36, 255), (219, 146, 255)),
}

LANE_ORDER = ['green', 'blue', 'yellow', 'red', 'purple']
NUM_LANES = 5
SPRITE_SIZE = 32


def _distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _draw_shaded_circle(draw, cx, cy, radius, dark, mid, bright, highlight, outline=(0, 0, 0)):
    """Draw a circle with 3D shading: dark bottom-right, bright top-left, highlight spot."""
    # Light source from top-left
    light_x, light_y = cx - radius * 0.35, cy - radius * 0.35

    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            dist = _distance(x, y, cx, cy)
            if dist > radius:
                continue

            # Normalized distance from center (0=center, 1=edge)
            norm_dist = dist / radius

            # Distance from light source for shading
            light_dist = _distance(x, y, light_x, light_y)
            light_norm = min(1.0, light_dist / (radius * 1.8))

            if norm_dist > 0.92:
                # Edge / outline
                draw.point((x, y), fill=outline)
            elif norm_dist > 0.82:
                # Dark rim
                draw.point((x, y), fill=dark)
            elif light_norm < 0.3:
                # Bright highlight zone near light source
                draw.point((x, y), fill=highlight)
            elif light_norm < 0.55:
                # Bright zone
                draw.point((x, y), fill=bright)
            elif light_norm < 0.75:
                # Mid zone
                draw.point((x, y), fill=mid)
            else:
                # Shadow zone (away from light)
                draw.point((x, y), fill=dark)


def _draw_ring(draw, cx, cy, outer_r, inner_r, color, outline=(0, 0, 0)):
    """Draw a ring (donut shape)."""
    for y in range(cy - outer_r, cy + outer_r + 1):
        for x in range(cx - outer_r, cx + outer_r + 1):
            dist = _distance(x, y, cx, cy)
            if inner_r <= dist <= outer_r:
                if dist > outer_r - 1 or dist < inner_r + 1:
                    draw.point((x, y), fill=outline)
                else:
                    draw.point((x, y), fill=color)


def _draw_glow_ring(draw, cx, cy, outer_r, inner_r, core_color, glow_color, bright_color):
    """Draw a glowing ring with radiant effect."""
    for y in range(cy - outer_r - 2, cy + outer_r + 3):
        for x in range(cx - outer_r - 2, cx + outer_r + 3):
            dist = _distance(x, y, cx, cy)
            # Outer glow halo
            if outer_r < dist <= outer_r + 2:
                draw.point((x, y), fill=glow_color)
            elif inner_r <= dist <= outer_r:
                if dist > outer_r - 2:
                    draw.point((x, y), fill=bright_color)
                elif dist < inner_r + 2:
                    draw.point((x, y), fill=bright_color)
                else:
                    draw.point((x, y), fill=core_color)


def _draw_letter(draw, cx, cy, letter, color):
    """Draw a simple pixel-art letter centered at (cx, cy)."""
    # Simple 5x5 pixel font for button labels
    fonts = {
        'L': [
            "X....",
            "X....",
            "X....",
            "X....",
            "XXXXX",
        ],
        'U': [
            "X...X",
            "X...X",
            "X...X",
            "X...X",
            ".XXX.",
        ],
        'D': [
            "XXXX.",
            "X...X",
            "X...X",
            "X...X",
            "XXXX.",
        ],
        'A': [
            ".XXX.",
            "X...X",
            "XXXXX",
            "X...X",
            "X...X",
        ],
        'B': [
            "XXXX.",
            "X...X",
            "XXXX.",
            "X...X",
            "XXXX.",
        ],
        'G': [
            ".XXX.",
            "X....",
            "X.XXX",
            "X...X",
            ".XXX.",
        ],
    }
    if letter not in fonts:
        return
    pattern = fonts[letter]
    ox = cx - 2
    oy = cy - 2
    for row_idx, row in enumerate(pattern):
        for col_idx, ch in enumerate(row):
            if ch == 'X':
                draw.point((ox + col_idx, oy + row_idx), fill=color)


def create_note_sprites(output_path):
    """Generate 6 note sprites in a 192x32 sheet (5 color lanes + 1 gold bonus note), each 32x32px with 3D shading."""
    width = (NUM_LANES + 1) * SPRITE_SIZE
    img = Image.new('RGB', (width, SPRITE_SIZE), color=MAGENTA)
    draw = ImageDraw.Draw(img)

    labels = ['L', 'U', 'D', 'A', 'B']

    for i, lane_name in enumerate(LANE_ORDER):
        palette = LANE_PALETTES[lane_name]
        dark, mid, bright, highlight = palette
        cx = i * SPRITE_SIZE + SPRITE_SIZE // 2
        cy = SPRITE_SIZE // 2

        # Main shaded button body
        _draw_shaded_circle(draw, cx, cy, 13, dark, mid, bright, highlight)

        # Inner darker ring for depth
        for y in range(cy - 14, cy + 15):
            for x in range(cx - 14, cx + 15):
                dist = _distance(x, y, cx, cy)
                if 13 < dist <= 14:
                    draw.point((x, y), fill=(36, 36, 36))

        # Outer chrome bezel
        for y in range(cy - 15, cy + 16):
            for x in range(cx - 15, cx + 16):
                dist = _distance(x, y, cx, cy)
                if 14 < dist <= 15:
                    # Gradient bezel: bright top-left, dark bottom-right
                    if x < cx and y < cy:
                        draw.point((x, y), fill=(182, 182, 182))
                    elif x > cx and y > cy:
                        draw.point((x, y), fill=(36, 36, 36))
                    else:
                        draw.point((x, y), fill=(109, 109, 109))

        # Draw letter label (dark on bright surface, positioned center)
        label_color = (0, 0, 0) if lane_name in ('yellow',) else (255, 255, 255)
        _draw_letter(draw, cx, cy + 1, labels[i], label_color)

    # Gold note frame (index 5)
    gold_palette = ((130, 95, 0), (210, 160, 0), (255, 215, 0), (255, 255, 150))
    dark, mid, bright, highlight = gold_palette
    cx = 5 * SPRITE_SIZE + SPRITE_SIZE // 2
    cy = SPRITE_SIZE // 2

    # Main shaded button body
    _draw_shaded_circle(draw, cx, cy, 13, dark, mid, bright, highlight)

    # Inner darker ring for depth
    for y in range(cy - 14, cy + 15):
        for x in range(cx - 14, cx + 15):
            dist = _distance(x, y, cx, cy)
            if 13 < dist <= 14:
                draw.point((x, y), fill=(36, 36, 36))

    # Outer gold bezel
    for y in range(cy - 15, cy + 16):
        for x in range(cx - 15, cx + 16):
            dist = _distance(x, y, cx, cy)
            if 14 < dist <= 15:
                if x < cx and y < cy:
                    draw.point((x, y), fill=(255, 235, 180))
                elif x > cx and y > cy:
                    draw.point((x, y), fill=(36, 36, 36))
                else:
                    draw.point((x, y), fill=(182, 140, 0))

    # Draw 'G' label (dark on bright surface, positioned center)
    _draw_letter(draw, cx, cy + 1, 'G', (0, 0, 0))

    img.save(output_path)
    print(f"Generated 32x32 note sprites ({NUM_LANES + 1} frames): {output_path}")


def create_hitzone_sprites(output_path):
    """Generate 2 hitzone frames in a 64x32 sheet: idle ring + glowing ring."""
    img = Image.new('RGB', (64, SPRITE_SIZE), color=MAGENTA)
    draw = ImageDraw.Draw(img)

    # Frame 0: Idle ring (dark metallic)
    cx0, cy0 = 16, 16
    _draw_ring(draw, cx0, cy0, 14, 9,
               color=(109, 109, 109),
               outline=(36, 36, 36))
    # Add subtle inner highlight on top
    for x in range(cx0 - 6, cx0 + 7):
        draw.point((x, cy0 - 12), fill=(146, 146, 146))
        draw.point((x, cy0 - 11), fill=(146, 146, 146))

    # Frame 1: Glowing ring (bright yellow/white flash)
    cx1, cy1 = 48, 16
    _draw_glow_ring(draw, cx1, cy1, 14, 9,
                    core_color=(255, 255, 0),
                    glow_color=(255, 219, 0),
                    bright_color=(255, 255, 219))
    # Extra bright center sparkle
    for y in range(cy1 - 2, cy1 + 3):
        for x in range(cx1 - 2, cx1 + 3):
            dist = _distance(x, y, cx1, cy1)
            if dist <= 2:
                pass  # Center stays transparent (magenta)

    img.save(output_path)
    print(f"Generated 32x32 hitzone sprites (2 frames): {output_path}")


def create_explosion_sprites(output_path):
    """Generate 4-frame explosion animation in a 128x32 sheet."""
    img = Image.new('RGB', (128, SPRITE_SIZE), color=MAGENTA)
    draw = ImageDraw.Draw(img)

    # Explosion colors
    white = (255, 255, 255)
    yellow_bright = (255, 255, 0)
    yellow = (255, 219, 0)
    orange = (255, 146, 0)
    red_bright = (255, 73, 0)
    red = (219, 36, 0)

    cx_base, cy = 16, 16

    for frame in range(4):
        cx = cx_base + frame * SPRITE_SIZE

        if frame == 0:
            # Frame 0: Small bright flash
            for y in range(cy - 5, cy + 6):
                for x in range(cx - 5, cx + 6):
                    dist = _distance(x, y, cx, cy)
                    if dist <= 2:
                        draw.point((x, y), fill=white)
                    elif dist <= 4:
                        draw.point((x, y), fill=yellow_bright)
                    elif dist <= 5:
                        draw.point((x, y), fill=yellow)

        elif frame == 1:
            # Frame 1: Expanding starburst
            for y in range(cy - 10, cy + 11):
                for x in range(cx - 10, cx + 11):
                    dist = _distance(x, y, cx, cy)
                    if dist <= 3:
                        draw.point((x, y), fill=white)
                    elif dist <= 5:
                        draw.point((x, y), fill=yellow_bright)
                    elif dist <= 7:
                        draw.point((x, y), fill=orange)
                    elif dist <= 9:
                        # Rays/sparks: only draw on diagonals and axes
                        angle = math.atan2(y - cy, x - cx)
                        ray = abs(math.sin(angle * 4))
                        if ray > 0.7:
                            draw.point((x, y), fill=yellow)
                    elif dist <= 10:
                        angle = math.atan2(y - cy, x - cx)
                        ray = abs(math.sin(angle * 4))
                        if ray > 0.85:
                            draw.point((x, y), fill=orange)

        elif frame == 2:
            # Frame 2: Peak explosion with sparks flying out
            for y in range(cy - 14, cy + 15):
                for x in range(cx - 14, cx + 15):
                    dist = _distance(x, y, cx, cy)
                    if dist <= 2:
                        draw.point((x, y), fill=white)
                    elif dist <= 4:
                        draw.point((x, y), fill=yellow_bright)
                    elif dist <= 6:
                        draw.point((x, y), fill=orange)
                    elif dist <= 8:
                        draw.point((x, y), fill=red_bright)
                    else:
                        # Scattered spark particles
                        angle = math.atan2(y - cy, x - cx)
                        ray = abs(math.sin(angle * 6))
                        if dist <= 12 and ray > 0.8:
                            draw.point((x, y), fill=yellow)
                        elif dist <= 14 and ray > 0.92:
                            draw.point((x, y), fill=orange)

        elif frame == 3:
            # Frame 3: Fading embers / dissipating
            for y in range(cy - 14, cy + 15):
                for x in range(cx - 14, cx + 15):
                    dist = _distance(x, y, cx, cy)
                    angle = math.atan2(y - cy, x - cx)
                    ray = abs(math.sin(angle * 5))
                    if dist <= 2:
                        draw.point((x, y), fill=yellow)
                    elif dist <= 5 and ray > 0.6:
                        draw.point((x, y), fill=orange)
                    elif dist <= 9 and ray > 0.8:
                        draw.point((x, y), fill=red_bright)
                    elif dist <= 13 and ray > 0.93:
                        draw.point((x, y), fill=red)

    img.save(output_path)
    print(f"Generated 32x32 explosion sprites (4 frames): {output_path}")


def create_countdown_sprites(output_path):
    """Generate 4-frame countdown animation in a 256x64 sheet (64x64px per frame)."""
    img = Image.new('RGB', (256, 64), color=MAGENTA)
    draw = ImageDraw.Draw(img)

    def draw_thick_lines(points, color, width):
        for start, end in points:
            draw.line([start, end], fill=color, width=width, joint='round')

    yellow = (255, 219, 0)
    white = (255, 255, 255)
    black = (0, 0, 0)

    for frame in range(4):
        cx = frame * 64 + 32
        cy = 32

        lines_list = []
        if frame == 0:  # "3"
            lines_list = [
                ((cx - 14, cy - 18), (cx + 14, cy - 18)),
                ((cx + 14, cy - 18), (cx + 14, cy + 18)),
                ((cx - 8,  cy),      (cx + 14, cy)),
                ((cx - 14, cy + 18), (cx + 14, cy + 18))
            ]
            draw_color = yellow
        elif frame == 1:  # "2"
            lines_list = [
                ((cx - 14, cy - 18), (cx + 14, cy - 18)),
                ((cx + 14, cy - 18), (cx + 14, cy)),
                ((cx - 14, cy),      (cx + 14, cy)),
                ((cx - 14, cy),      (cx - 14, cy + 18)),
                ((cx - 14, cy + 18), (cx + 14, cy + 18))
            ]
            draw_color = yellow
        elif frame == 2:  # "1"
            lines_list = [
                ((cx - 4,  cy - 18), (cx + 4,  cy - 18)),
                ((cx + 4,  cy - 18), (cx + 4,  cy + 18)),
                ((cx - 12, cy + 18), (cx + 20, cy + 18))
            ]
            draw_color = yellow
        elif frame == 3:  # "GO"
            lines_list = [
                # G
                ((cx - 24, cy - 18), (cx - 6,  cy - 18)),
                ((cx - 24, cy - 18), (cx - 24, cy + 18)),
                ((cx - 24, cy + 18), (cx - 6,  cy + 18)),
                ((cx - 6,  cy),      (cx - 6,  cy + 18)),
                ((cx - 14, cy),      (cx - 6,  cy)),
                # O
                ((cx + 6,  cy - 18), (cx + 24, cy - 18)),
                ((cx + 6,  cy - 18), (cx + 6,  cy + 18)),
                ((cx + 24, cy - 18), (cx + 24, cy + 18)),
                ((cx + 6,  cy + 18), (cx + 24, cy + 18))
            ]
            draw_color = white

        # Draw outline
        draw_thick_lines(lines_list, black, width=12)
        # Draw core
        draw_thick_lines(lines_list, draw_color, width=6)

    img.save(output_path)
    print(f"Generated 64x64 countdown sprites (4 frames): {output_path}")


if __name__ == '__main__':
    out_dir = 'tools/output/temp_gfx'
    os.makedirs(out_dir, exist_ok=True)
    create_note_sprites(os.path.join(out_dir, 'raw_notes.png'))
    create_hitzone_sprites(os.path.join(out_dir, 'raw_hitzone.png'))
    create_explosion_sprites(os.path.join(out_dir, 'raw_explosion.png'))
    create_countdown_sprites(os.path.join(out_dir, 'raw_countdown.png'))
