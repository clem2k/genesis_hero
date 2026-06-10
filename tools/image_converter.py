#!/usr/bin/env python3
"""
image_converter.py - Convert PNG images to Mega Drive compatible indexed PNG.

Processes images for the Sega Genesis/Mega Drive:
- Resize to tile-aligned dimensions (multiples of 8)
- Quantize to 15 colors + 1 transparency (16 total)
- Map colors to Genesis 9-bit palette (each R/G/B is one of 8 values)
- Set index 0 to transparency color (magenta #FF00FF)
- Save as indexed (palette mode) PNG
"""

import os
import sys
import argparse
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("[ERROR] Pillow not installed. Install with: pip install Pillow")
    sys.exit(1)


# Genesis 9-bit color palette: each R/G/B component can be one of 8 values
# These map to the 3-bit per channel hardware palette
GENESIS_COLOR_VALUES = [0, 36, 73, 109, 146, 182, 219, 255]

# Default transparency color (magenta)
DEFAULT_TRANSPARENT = (255, 0, 255)


def snap_to_genesis_color(r, g, b):
    """
    Snap an RGB color to the nearest Genesis 9-bit palette color.

    Each component is mapped independently to the nearest of 8 possible values.

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).

    Returns:
        Tuple (nearest_r, nearest_g, nearest_b).
    """
    nearest_r = min(GENESIS_COLOR_VALUES, key=lambda v: abs(v - r))
    nearest_g = min(GENESIS_COLOR_VALUES, key=lambda v: abs(v - g))
    nearest_b = min(GENESIS_COLOR_VALUES, key=lambda v: abs(v - b))
    return (nearest_r, nearest_g, nearest_b)


def _align_to_tile(value, tile_size=8):
    """Round up a dimension to the nearest multiple of tile_size."""
    return ((value + tile_size - 1) // tile_size) * tile_size


def convert_image(input_path, output_path, width=None, height=None,
                  max_colors=16, transparent_color=DEFAULT_TRANSPARENT):
    """
    Convert an image to Mega Drive compatible indexed PNG.

    Steps:
    1. Load and optionally resize
    2. Align dimensions to 8-pixel tiles
    3. Map all colors to Genesis 9-bit palette
    4. Handle transparency
    5. Quantize to max_colors
    6. Save as indexed PNG

    Args:
        input_path: Path to input image.
        output_path: Path for output indexed PNG.
        width: Target width (None = keep original).
        height: Target height (None = keep original).
        max_colors: Maximum palette size (default 16).
        transparent_color: RGB tuple for transparent pixels.

    Returns:
        Path to output file on success, None on failure.
    """
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    if not input_path.exists():
        print(f"[ERROR] Input image not found: {input_path}")
        return None

    print(f"[INFO] Converting image: {input_path.name}")

    try:
        img = Image.open(input_path)
    except Exception as e:
        print(f"[ERROR] Failed to open image: {e}")
        return None

    original_size = img.size
    print(f"[INFO]   Original size: {original_size[0]}x{original_size[1]}, mode: {img.mode}")

    # Convert to RGBA for consistent processing
    img = img.convert('RGBA')

    # ── Resize if requested ──
    if width is not None or height is not None:
        orig_w, orig_h = img.size
        if width is not None and height is not None:
            new_w, new_h = width, height
        elif width is not None:
            # Maintain aspect ratio
            ratio = width / orig_w
            new_w = width
            new_h = int(orig_h * ratio)
        else:
            # height is not None
            ratio = height / orig_h
            new_w = int(orig_w * ratio)
            new_h = height

        img = img.resize((new_w, new_h), Image.LANCZOS)
        print(f"[INFO]   Resized to: {new_w}x{new_h}")

    # ── Align to tile boundaries (multiples of 8) ──
    w, h = img.size
    aligned_w = _align_to_tile(w)
    aligned_h = _align_to_tile(h)

    if aligned_w != w or aligned_h != h:
        # Create new image with aligned dimensions, fill with transparent
        aligned_img = Image.new('RGBA', (aligned_w, aligned_h),
                                transparent_color + (0,))
        aligned_img.paste(img, (0, 0))
        img = aligned_img
        print(f"[INFO]   Tile-aligned to: {aligned_w}x{aligned_h}")

    # ── Map colors to Genesis palette ──
    pixels = img.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]

            if a < 128:
                # Transparent pixel -> use transparency color
                pixels[x, y] = transparent_color + (255,)
            else:
                # Snap to nearest Genesis color
                gr, gg, gb = snap_to_genesis_color(r, g, b)
                pixels[x, y] = (gr, gg, gb, 255)

    print(f"[INFO]   Colors mapped to Genesis 9-bit palette")

    # ── Convert to RGB (drop alpha, transparency is now a specific color) ──
    img_rgb = img.convert('RGB')

    # ── Quantize to indexed palette ──
    # Reserve slot for transparency color
    num_colors = max(2, min(max_colors, 256))

    try:
        # Use median cut quantization
        img_quantized = img_rgb.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    except Exception:
        # Fallback quantization
        img_quantized = img_rgb.quantize(colors=num_colors)

    # ── Ensure index 0 is the transparency color ──
    palette_data = img_quantized.getpalette()

    if palette_data:
        # Find the transparency color in the palette
        trans_r, trans_g, trans_b = transparent_color
        trans_index = None

        for i in range(0, min(len(palette_data), num_colors * 3), 3):
            pr, pg, pb = palette_data[i], palette_data[i + 1], palette_data[i + 2]
            if pr == trans_r and pg == trans_g and pb == trans_b:
                trans_index = i // 3
                break

        if trans_index is not None and trans_index != 0:
            # Swap transparency color to index 0
            # Swap palette entries
            old_r, old_g, old_b = palette_data[0], palette_data[1], palette_data[2]
            palette_data[0] = trans_r
            palette_data[1] = trans_g
            palette_data[2] = trans_b
            palette_data[trans_index * 3] = old_r
            palette_data[trans_index * 3 + 1] = old_g
            palette_data[trans_index * 3 + 2] = old_b

            # Swap pixel indices
            px_data = list(img_quantized.getdata())
            swapped = []
            for p in px_data:
                if p == 0:
                    swapped.append(trans_index)
                elif p == trans_index:
                    swapped.append(0)
                else:
                    swapped.append(p)
            img_quantized.putdata(swapped)
            img_quantized.putpalette(palette_data)
            print(f"[INFO]   Transparency color swapped to index 0")

        elif trans_index is None:
            # Transparency color not in palette, force it into index 0
            palette_data[0] = trans_r
            palette_data[1] = trans_g
            palette_data[2] = trans_b
            img_quantized.putpalette(palette_data)
            print(f"[INFO]   Transparency color forced into index 0")

    # ── Count unique colors ──
    unique_colors = len(set(img_quantized.getdata()))
    print(f"[INFO]   Palette colors: {unique_colors} (max: {num_colors})")

    # ── Save ──
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img_quantized.save(str(output_path), format='PNG')

    print(f"[INFO]   Output: {output_path}")
    print(f"[INFO]   Output size: {img_quantized.size[0]}x{img_quantized.size[1]}")
    return output_path


def batch_convert(input_dir, output_dir, **kwargs):
    """
    Convert all PNG files in a directory to Mega Drive format.

    Args:
        input_dir: Directory containing input PNG files.
        output_dir: Directory for output indexed PNG files.
        **kwargs: Additional arguments passed to convert_image
                  (width, height, max_colors, transparent_color).

    Returns:
        List of output file paths.
    """
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}")
        return []

    # Find all PNG files
    png_files = sorted(input_dir.glob("*.png"))

    if not png_files:
        print(f"[ERROR] No PNG files found in: {input_dir}")
        return []

    print(f"[INFO] Batch converting {len(png_files)} PNG files")
    print(f"[INFO]   Input: {input_dir}")
    print(f"[INFO]   Output: {output_dir}")

    results = []
    success_count = 0
    fail_count = 0

    for png_path in png_files:
        output_path = output_dir / png_path.name
        print(f"\n[INFO] --- {png_path.name} ---")

        result = convert_image(png_path, output_path, **kwargs)
        if result:
            results.append(result)
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print(f"\n[INFO] === Batch Conversion Summary ===")
    print(f"[INFO]   Total: {len(png_files)}")
    print(f"[INFO]   Success: {success_count}")
    print(f"[INFO]   Failed: {fail_count}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Convert PNG images to Mega Drive compatible indexed PNG"
    )
    parser.add_argument("input", help="Input PNG file or directory (with --batch)")
    parser.add_argument("output", help="Output PNG file or directory (with --batch)")
    parser.add_argument(
        "--width", type=int, default=None,
        help="Target width in pixels (must be multiple of 8)"
    )
    parser.add_argument(
        "--height", type=int, default=None,
        help="Target height in pixels (must be multiple of 8)"
    )
    parser.add_argument(
        "--colors", type=int, default=16,
        help="Maximum palette colors (default: 16)"
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="Batch mode: convert all PNGs in input directory"
    )

    args = parser.parse_args()

    kwargs = {
        'width': args.width,
        'height': args.height,
        'max_colors': args.colors,
    }

    # Remove None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    if args.batch:
        results = batch_convert(args.input, args.output, **kwargs)
        if not results:
            print("[ERROR] No images were converted")
            sys.exit(1)
    else:
        result = convert_image(args.input, args.output, **kwargs)
        if not result:
            print("[ERROR] Image conversion failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
