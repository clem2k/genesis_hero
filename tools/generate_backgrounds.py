#!/usr/bin/env python3
"""
generate_backgrounds.py - Programmatically draw pixel-art gameplay backgrounds
for Genesis Hero with 3, 4, and 5 lanes, ensuring optimal contrast and color harmony.
"""

import os
import sys
from PIL import Image, ImageDraw

def create_gameplay_bg(num_lanes, output_path):
    # Dimensions (Genesis standard: 320x224)
    width, height = 320, 224
    
    # Dark purple/black stage ambiance
    img = Image.new('RGB', (width, height), color=(18, 8, 24))
    draw = ImageDraw.Draw(img)
    
    # Snapped Genesis colors
    BLACK = (0, 0, 0)
    DARK_GRAY = (36, 36, 36)
    MID_GRAY = (73, 73, 73)
    LIGHT_GRAY = (146, 146, 146)
    
    LANE_BG = (24, 24, 40) # Dark charcoal-indigo for lane board (high contrast with notes)
    LANE_DIVIDER = (73, 73, 109) # Dim gray-blue for dividers
    
    # Neon scheme depending on difficulty
    if num_lanes == 3:
        BORDER_COLOR = (0, 219, 219) # Cyan
        BEAM_COLOR = (0, 109, 146) # Dithered Cyan/Blue
    elif num_lanes == 4:
        BORDER_COLOR = (255, 0, 109) # Pink/Magenta
        BEAM_COLOR = (146, 0, 73) # Dithered Pink
    else: # 5 lanes
        BORDER_COLOR = (219, 182, 0) # Gold/Yellow
        BEAM_COLOR = (146, 109, 0) # Dithered Gold
        
    # ── 1. HUD Background (Top 16 pixels) ──
    # MUST be pure black to make white/cyan HUD text perfectly legible!
    draw.rectangle([0, 0, width, 15], fill=BLACK)
    
    # ── 2. Stage Trusses / Grid ──
    # horizontal metal beam dividing HUD and stage (Y=16-20)
    draw.rectangle([0, 16, width, 19], fill=DARK_GRAY)
    draw.line([0, 16, width, 16], fill=MID_GRAY)
    draw.line([0, 19, width, 19], fill=BLACK)
    
    # Stage floor grille at the bottom (Y=200 to 224)
    for y in range(200, height):
        for x in range(width):
            if (x // 8 + y // 4) % 2 == 0:
                img.putpixel((x, y), (36, 24, 36))
            else:
                img.putpixel((x, y), (18, 12, 18))
                
    # ── 3. Draw Track Board (Centered) ──
    track_width = num_lanes * 32
    start_x = (width - track_width) // 2
    end_x = start_x + track_width
    
    # Fill track board background (dark for high contrast)
    draw.rectangle([start_x, 20, end_x, 199], fill=LANE_BG)
    
    # Draw left and right neon rails (glow borders)
    draw.rectangle([start_x - 2, 20, start_x - 1, 199], fill=BORDER_COLOR)
    draw.rectangle([end_x + 1, 20, end_x + 2, 199], fill=BORDER_COLOR)
    
    # Draw lane dividers (vertical dashed lines)
    for i in range(1, num_lanes):
        x = start_x + i * 32
        for y in range(20, 200, 4):
            draw.line([x, y, x, y + 1], fill=LANE_DIVIDER)
            
    # ── 4. Stage Props (Concert Speakers) ──
    # Left speaker stack (only if there is enough space on sides)
    left_speaker_w = min(start_x - 8, 30)
    if left_speaker_w > 12:
        draw.rectangle([4, 80, left_speaker_w, 199], fill=DARK_GRAY, outline=BLACK)
        # Circular cones
        draw.ellipse([6, 90, left_speaker_w - 2, 120], fill=MID_GRAY, outline=BLACK)
        draw.ellipse([8, 92, left_speaker_w - 4, 118], fill=BLACK)
        draw.ellipse([6, 130, left_speaker_w - 2, 170], fill=MID_GRAY, outline=BLACK)
        draw.ellipse([8, 132, left_speaker_w - 4, 168], fill=BLACK)
        
    # Right speaker stack
    right_speaker_x = max(end_x + 8, width - 30)
    if right_speaker_x < width - 12:
        draw.rectangle([right_speaker_x, 80, width - 5, 199], fill=DARK_GRAY, outline=BLACK)
        # Circular cones
        draw.ellipse([right_speaker_x + 2, 90, width - 7, 120], fill=MID_GRAY, outline=BLACK)
        draw.ellipse([right_speaker_x + 4, 92, width - 9, 118], fill=BLACK)
        draw.ellipse([right_speaker_x + 2, 130, width - 7, 170], fill=MID_GRAY, outline=BLACK)
        draw.ellipse([right_speaker_x + 4, 132, width - 9, 168], fill=BLACK)
        
    # ── 5. Spotlight Beams ──
    # Left spotlight at (12, 20)
    for y in range(20, 160):
        beam_w = (y - 20) // 2
        lx_center = 12 + (y - 20) // 3
        for x in range(max(0, lx_center - beam_w), min(start_x - 2, lx_center + beam_w)):
            # Dithering checkerboard for Mega Drive composite blending simulation
            if (x + y) % 3 == 0:
                img.putpixel((x, y), BEAM_COLOR)
                
    # Right spotlight at (308, 20)
    for y in range(20, 160):
        beam_w = (y - 20) // 2
        rx_center = 308 - (y - 20) // 3
        for x in range(max(end_x + 3, rx_center - beam_w), min(width, rx_center + beam_w)):
            if (x - y) % 3 == 0:
                img.putpixel((x, y), BEAM_COLOR)
                
    # Draw physical light housings
    draw.polygon([(6, 20), (18, 20), (12, 25)], fill=MID_GRAY, outline=BLACK)
    draw.polygon([(302, 20), (314, 20), (308, 25)], fill=MID_GRAY, outline=BLACK)
    
    # Save image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    print(f"Generated raw background: {output_path} ({num_lanes} lanes)")

if __name__ == "__main__":
    out_dir = "tools/output/temp_gfx"
    os.makedirs(out_dir, exist_ok=True)
    create_gameplay_bg(3, os.path.join(out_dir, "raw_bg_gameplay_easy.png"))
    create_gameplay_bg(4, os.path.join(out_dir, "raw_bg_gameplay_normal.png"))
    create_gameplay_bg(5, os.path.join(out_dir, "raw_bg_gameplay_hard.png"))
