#!/usr/bin/env python3
"""
Pixel-based poker range extractor for rangeconverter.com PNG crops.

Grid geometry (5x zoom, single-position crops ~1020-1034 x 1490px):
  - Background: dark navy
  - Grid starts at x=85 (left border + row header)
  - Cell width: 73px, Cell separator: 3px, Stride: 76px
  - Grid starts at y=368 (title + header row)
  - Row height: 81px, Row separator: 2px, Stride: 83px
  - 13 columns (A K Q J T 9 8 7 6 5 4 3 2 left→right)
  - 13 rows    (A K Q J T 9 8 7 6 5 4 3 2 top→bottom)

Color encoding:
  - Orange (227,130,20): Raise / Open
  - Blue   (39,125,161): Fold
  - Lime   (127,180,50): Call / Limp (SB only)
"""
import json, sys
from pathlib import Path
from PIL import Image
import numpy as np

RANKS = "AKQJT98765432"
COL_CENTERS = [85 + 34 + i * 76 for i in range(13)]  # [119, 195, 271, ...]
ROW_CENTERS = [368 + 40 + i * 83 for i in range(13)]  # [408, 491, 574, ...]


def hand_at(row, col):
    r1, r2 = RANKS[row], RANKS[col]
    if row < col: return f"{r1}{r2}s"
    if row > col: return f"{r2}{r1}o"
    return f"{r1}{r2}"


def classify_cell(arr, y_c, x_c):
    """
    Classify cell by sampling 4 corners (away from text labels).
    Returns (orange_count, teal_count, blue_count).
    Corner offsets: ±25px horizontal, ±28px vertical from center.
    Each corner is a 5×5 sample region.
    """
    h, w = arr.shape[:2]
    orange = teal = blue = 0
    for dx in (-25, 25):
        for dy in (-28, 28):
            cx, cy = x_c + dx, y_c + dy
            region = arr[max(0,cy-2):cy+3, max(0,cx-2):cx+3]
            for row_p in region:
                for p in row_p:
                    r, g, b = int(p[0]), int(p[1]), int(p[2])
                    # Orange (raise): warm orange, very low blue
                    if r > 150 and g > 80 and b < 80 and r > g * 1.2 and g > b * 2.5:
                        orange += 1
                    # Blue (fold): clearly blue-dominant
                    elif b > 130 and b > r + 60:
                        blue += 1
                    # Teal/lime (call): green and blue balanced, moderate red
                    elif g > 100 and b > 80 and abs(int(g)-int(b)) < 60 and r < 180:
                        teal += 1
    return orange, teal, blue


def extract_single_grid(arr, y_offset=0, show_grid=False):
    """
    Extract raise/call hands from a 13×13 grid.
    y_offset: vertical offset in pixels (0 for top crops, used for SB in full page).
    """
    raise_hands, call_hands = [], []
    grid_debug = []

    for row in range(13):
        y_c = ROW_CENTERS[row] + y_offset
        row_data = []
        for col in range(13):
            x_c = COL_CENTERS[col]
            if x_c >= arr.shape[1] or y_c >= arr.shape[0]:
                row_data.append("X")
                continue
            o, t, b = classify_cell(arr, y_c, x_c)
            if o >= t and o > b:
                action = "raise"   # orange dominant OR tied orange/teal (mixed = treat as raise)
            elif t > o and t > b:
                action = "call"    # teal dominant
            else:
                action = "fold"    # blue dominant or all zero
            row_data.append(action)
            hand = hand_at(row, col)
            if action == "raise":
                raise_hands.append(hand)
            elif action == "call":
                call_hands.append(hand)
        grid_debug.append(row_data)

    if show_grid:
        sym = {"raise": "R", "call": "C", "fold": "F", "?": "?", "X": "X"}
        print("     " + "  ".join(RANKS))
        for r in range(13):
            print(f"  {RANKS[r]}: " + "  ".join(sym.get(grid_debug[r][c], "?") for c in range(13)))

    return raise_hands, call_hands


def extract_rfi_crop(img_path, has_call=False):
    """Extract RFI range from a single-position crop PNG."""
    img = Image.open(str(img_path))
    arr = np.array(img)
    raise_hands, call_hands = extract_single_grid(arr)
    pct_raise = len(raise_hands) / 169 * 100
    pct_call = len(call_hands) / 169 * 100
    result = {
        "raise": raise_hands,
        "pct_raise": round(pct_raise, 2),
    }
    if has_call or call_hands:
        result["call"] = call_hands
        result["pct_call"] = round(pct_call, 2)
    return result


def extract_all_rfi(pdf_key, crop_dir=Path("/tmp/rc_crops")):
    """Extract all 5 RFI positions for a PDF."""
    results = {}
    for pos in ["UTG", "MP", "CO", "BTN", "SB"]:
        path = crop_dir / f"{pdf_key}_rfi_{pos}.png"
        if not path.exists():
            print(f"  Missing: {path.name}")
            continue
        has_call = (pos == "SB")
        result = extract_rfi_crop(path, has_call=has_call)
        results[pos] = result
        call_info = f" + {len(result.get('call',[]))} call ({result.get('pct_call',0):.1f}%)" if has_call else ""
        print(f"  {pos}: {len(result['raise'])} raise ({result['pct_raise']:.1f}%){call_info}")
    return results


if __name__ == "__main__":
    import os
    crop_dir = Path("/tmp/rc_crops")

    pdf_keys = [
        "6max_100bb_highRake",
        "6max_100bb",
        "6max_40bb",
        "6max_200bb",
    ]

    for pdf_key in pdf_keys:
        path = crop_dir / f"{pdf_key}_rfi_UTG.png"
        if not path.exists():
            continue
        print(f"\n{pdf_key}:")
        results = extract_all_rfi(pdf_key, crop_dir)
        print(f"  Summary: " + ", ".join(f"{p}={len(v['raise'])}" for p, v in results.items()))
