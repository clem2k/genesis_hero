#!/usr/bin/env python3
"""
convert_all_assets.py - Convert all raw assets to Mega Drive compatible format.

Generates sprites programmatically, then converts all images to indexed PNG
with Genesis 9-bit palette constraints.
"""

import os
import shutil
from pathlib import Path
from image_converter import convert_image

# Directories
PROJECT_DIR = Path(__file__).parent.parent.resolve()
BRAIN_DIR = Path("C:/Users/cleme/.gemini/antigravity/brain/46b2caad-fb7a-48db-9213-282e52b22fb5")
GFX_DIR = PROJECT_DIR / "res" / "gfx"
TEMP_GFX = PROJECT_DIR / "tools" / "output" / "temp_gfx"

os.makedirs(GFX_DIR, exist_ok=True)
os.makedirs(TEMP_GFX, exist_ok=True)

# ── 1. Convert Backgrounds ──
print("=" * 50)
print("  Converting Backgrounds")
print("=" * 50)

# Title screen — use the newest metal title
title_candidates = sorted(BRAIN_DIR.glob("title_screen_metal_*.png"), reverse=True)
if not title_candidates:
    title_candidates = sorted(BRAIN_DIR.glob("title_screen_*.png"), reverse=True)

if title_candidates:
    title_src = title_candidates[0]
    title_dst = GFX_DIR / "bg_title.png"
    print(f"\n[INFO] Title source: {title_src.name}")
    convert_image(str(title_src), str(title_dst), width=320, height=224, max_colors=16)
else:
    print("[ERROR] No title screen source found!")

# Gameplay background — use the newest neon gameplay background
gameplay_candidates = sorted(BRAIN_DIR.glob("gameplay_background_neon_*.png"), reverse=True)
if not gameplay_candidates:
    gameplay_candidates = sorted(BRAIN_DIR.glob("gameplay_background_*.png"), reverse=True)

# Gameplay backgrounds — generate and convert for easy, normal, and hard difficulties
import generate_backgrounds

print("\n[INFO] Generating difficulty-specific gameplay backgrounds...")
generate_backgrounds.create_gameplay_bg(3, str(TEMP_GFX / "raw_bg_gameplay_easy.png"))
generate_backgrounds.create_gameplay_bg(4, str(TEMP_GFX / "raw_bg_gameplay_normal.png"))
generate_backgrounds.create_gameplay_bg(5, str(TEMP_GFX / "raw_bg_gameplay_hard.png"))

print("\n[INFO] Converting easy gameplay background...")
convert_image(str(TEMP_GFX / "raw_bg_gameplay_easy.png"), str(GFX_DIR / "bg_gameplay_easy.png"), max_colors=16)

print("\n[INFO] Converting normal gameplay background...")
convert_image(str(TEMP_GFX / "raw_bg_gameplay_normal.png"), str(GFX_DIR / "bg_gameplay_normal.png"), max_colors=16)

print("\n[INFO] Converting hard gameplay background...")
convert_image(str(TEMP_GFX / "raw_bg_gameplay_hard.png"), str(GFX_DIR / "bg_gameplay_hard.png"), max_colors=16)

# ── 2. Generate and Convert Sprites ──
print("\n" + "=" * 50)
print("  Generating and Converting Sprites (32x32px)")
print("=" * 50)

import generate_sprites

# Generate raw sprites
generate_sprites.create_note_sprites(str(TEMP_GFX / "raw_notes.png"))
generate_sprites.create_hitzone_sprites(str(TEMP_GFX / "raw_hitzone.png"))
generate_sprites.create_explosion_sprites(str(TEMP_GFX / "raw_explosion.png"))
generate_sprites.create_countdown_sprites(str(TEMP_GFX / "raw_countdown.png"))

# Convert sprites to Mega Drive indexed format
# Notes: 6 notes * 32x32 = 192x32
print("\n[INFO] Converting note sprites...")
convert_image(
    str(TEMP_GFX / "raw_notes.png"),
    str(GFX_DIR / "spr_notes.png"),
    max_colors=16
)

# Hitzone: 2 frames * 32x32 = 64x32
print("\n[INFO] Converting hitzone sprites...")
convert_image(
    str(TEMP_GFX / "raw_hitzone.png"),
    str(GFX_DIR / "spr_hitzone.png"),
    max_colors=16
)

# Explosion: 4 frames * 32x32 = 128x32
print("\n[INFO] Converting explosion sprites...")
convert_image(
    str(TEMP_GFX / "raw_explosion.png"),
    str(GFX_DIR / "spr_explosion.png"),
    max_colors=16
)

# Countdown: 4 frames * 64x64 = 256x64
print("\n[INFO] Converting countdown sprites...")
convert_image(
    str(TEMP_GFX / "raw_countdown.png"),
    str(GFX_DIR / "spr_countdown.png"),
    max_colors=16
)

print("\n" + "=" * 50)
print("  Asset conversion complete!")
print("=" * 50)
