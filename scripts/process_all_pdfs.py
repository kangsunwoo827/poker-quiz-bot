#!/usr/bin/env python3
"""
Process all rangeconverter.com PDFs → extract ranges → save JSON.

Usage:
  python3 scripts/process_all_pdfs.py           # all PDFs
  python3 scripts/process_all_pdfs.py 9max_100bb # specific PDF
  python3 scripts/process_all_pdfs.py --force    # reprocess all
"""
import sys, json
from pathlib import Path
from PIL import Image
import numpy as np
import fitz  # PyMuPDF

ROOT    = Path(__file__).parent.parent
PDF_DIR = ROOT / "data" / "rangeconverter_pdfs"
OUT_DIR = ROOT / "data" / "ranges"
CROP_DIR = Path("/tmp/rc_crops")
CROP_DIR.mkdir(exist_ok=True)

# ── PDF configs ───────────────────────────────────────────────────────────────
PDF_CONFIGS = {
    "6max_100bb_highRake": {
        "label": "6-max 100bb High Rake",
        "positions": ["UTG", "MP", "CO", "BTN", "SB"],
    },
    "6max_100bb": {
        "label": "6-max 100bb",
        "positions": ["UTG", "MP", "CO", "BTN", "SB"],
    },
    "6max_40bb": {
        "label": "6-max 40bb",
        "positions": ["UTG", "MP", "CO", "BTN", "SB"],
    },
    "6max_200bb": {
        "label": "6-max 200bb",
        "positions": ["UTG", "MP", "CO", "BTN", "SB"],
    },
    "9max_100bb": {
        "label": "9-max 100bb",
        "positions": ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_100bb": {
        "label": "MTT 100bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_60bb": {
        "label": "MTT 60bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_50bb": {
        "label": "MTT 50bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_40bb": {
        "label": "MTT 40bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_30bb": {
        "label": "MTT 30bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_20bb": {
        "label": "MTT 20bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
    "mtt_10bb": {
        "label": "MTT 10bb",
        "positions": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    },
}

# Grid crop geometry: 4 grids per top row, N-4 grids in bottom row
# At 5x zoom, full page ≈ 4210×2980
GRID_STARTS_X = [83, 1108, 2130, 3153]
GRID_W        = 1025
TOP_ROW_Y     = 0
BOT_ROW_Y     = 1490
GRID_H        = 1490

RANKS = "AKQJT98765432"


# ── Color classifiers ─────────────────────────────────────────────────────────
def is_red(r, g, b):
    """Red = all-in/push (dark red, r dominant, low g and b)."""
    return r > 160 and g < 100 and b < 100 and r > g + 80

def is_orange(r, g, b):
    """Strict orange = standard raise (exclude yellow headers and red)."""
    if is_red(r, g, b):
        return False
    return r > 150 and g > 80 and b < 80 and r > g * 1.4

def is_blue(r, g, b):
    return b > 120 and b > r + 50

def is_teal(r, g, b):
    return g > 100 and b > 80 and abs(int(g)-int(b)) < 60 and r < 180


# ── Grid parameter auto-detection ─────────────────────────────────────────────
def find_grid_row_centers(arr):
    """
    Detect grid row centers by finding the large contiguous block of 'data rows'.
    A data row has: some colored pixels (>25%) AND some background (>5%).
    Uses gap_tolerance=35 to bridge cell-text gaps within each grid row.
    Returns (centers_list, stride_px).
    """
    H, W = arr.shape[:2]
    x_start, x_end = 100, min(900, W-10)

    data_rows = np.zeros(H, dtype=bool)
    for y in range(H):
        o = b = t = bg = 0
        for x in range(x_start, x_end, 20):
            p = arr[y, x]
            r, g, b_ = int(p[0]), int(p[1]), int(p[2])
            if is_red(r, g, b_): o += 1
            elif is_orange(r, g, b_): o += 1
            elif is_blue(r, g, b_): b += 1
            elif is_teal(r, g, b_): t += 1
            else: bg += 1
        colored = o + b + t
        data_rows[y] = (colored / 40 > 0.25 and bg / 40 > 0.05)

    GAP = 35
    regions = []
    in_region = False
    region_start = 0
    last_data = -GAP - 1

    for y in range(H):
        if data_rows[y]:
            if not in_region or y - last_data > GAP:
                if in_region:
                    regions.append((region_start, last_data))
                region_start = y
                in_region = True
            last_data = y
    if in_region:
        regions.append((region_start, last_data))

    large = [(s, e) for s, e in regions if e - s >= 500]
    if not large:
        large = sorted(regions, key=lambda r: r[1]-r[0], reverse=True)[:1]
    if not large:
        return None, None

    # If multiple large regions, pick the LAST one (most likely to be the actual grid)
    y_start, y_end = large[-1]

    section_h = (y_end - y_start) / 13
    centers = [int(y_start + (i + 0.5) * section_h) for i in range(13)]
    stride  = int(section_h)
    return centers, stride


# ── Auto-detect grid by finding borders and dividing evenly ──────────────────
def detect_grid(arr):
    """Auto-detect 13x13 grid cell centers.

    Strategy: find colored bounding box (top/bottom/left/right), skip column
    header row, then divide data area into 13 equal rows and 13 equal columns.

    Returns (row_centers[13], col_centers[13], corner_dy, corner_dx) or None.
    """
    H, W = arr.shape[:2]

    def is_cell_color(y, x):
        r, g, b = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2])
        return is_orange(r, g, b) or is_blue(r, g, b) or is_teal(r, g, b) or is_red(r, g, b)

    # 1. Find vertical bounds: data_top and data_bottom
    data_top = None
    for y in range(H):
        colored = sum(1 for x in range(0, W, 5) if is_cell_color(y, x))
        if colored / (W // 5) > 0.5:
            data_top = y
            break
    if data_top is None:
        return None

    data_bottom = data_top
    for y in range(H - 1, data_top, -1):
        colored = sum(1 for x in range(0, W, 5) if is_cell_color(y, x))
        if colored / (W // 5) > 0.3:
            data_bottom = y
            break

    # Skip column header row (1/14 of total grid height)
    total_grid_h = data_bottom - data_top
    col_header_h = total_grid_h / 14
    first_data_y = int(data_top + col_header_h)

    # Row stride and centers
    data_h = data_bottom - first_data_y
    row_stride = data_h / 13
    row_centers = [int(first_data_y + (i + 0.5) * row_stride) for i in range(13)]

    # 2. Find horizontal bounds: data_left and data_right
    # The grid has a row header column on the left (~80px) followed by 13 data columns.
    # Detect data_left by finding the gap after the row header.
    data_right = 0
    for y_test in row_centers:
        for x in range(W - 1, W // 2, -1):
            if is_cell_color(y_test, x):
                data_right = max(data_right, x)
                break
    if data_right == 0:
        return None

    # Find data_left and stride from column header row transitions.
    # The column header row has evenly-spaced colored cells: [row_hdr, col_A, col_K, ...]
    # Detect rising edges (background→colored) to find cell boundaries.
    header_y = data_top + 5
    transitions = []
    prev = is_cell_color(header_y, 0)
    for x in range(1, W):
        cur = is_cell_color(header_y, x)
        if cur and not prev:
            transitions.append(x)
        prev = cur

    # First transition = row header start. Second = first data column start.
    # Compute stride from early transitions (most reliable).
    # Valid stride range at 5x zoom: 60-80px for 1025px crops
    min_stride, max_stride = int(W * 0.058), int(W * 0.078)
    col_stride = None
    data_left = None

    if len(transitions) >= 4:
        # Try transitions[1] as data_left (skipping row header)
        strides = [transitions[i+1] - transitions[i] for i in range(1, min(6, len(transitions)-1))]
        med = sorted(strides)[len(strides) // 2]
        if min_stride <= med <= max_stride:
            data_left = transitions[1]
            col_stride = med

    if col_stride is None and len(transitions) >= 3:
        # Try transitions[0] as data_left (no row header, or header = first transition)
        strides = [transitions[i+1] - transitions[i] for i in range(0, min(5, len(transitions)-1))]
        med = sorted(strides)[len(strides) // 2]
        if min_stride <= med <= max_stride:
            data_left = transitions[0]
            col_stride = med

    if col_stride is None:
        # Fallback: anchor from data_right with estimated stride
        col_stride = int(W * 0.068)  # ~70px for 1025px crop
        data_left = data_right - 13 * col_stride + col_stride // 2
    if data_left is None or data_right <= data_left:
        return None

    # Column centers from data_left and stride (detected from header transitions)
    col_centers = [int(data_left + (i + 0.5) * col_stride) for i in range(13)]

    corner_dy = max(10, int(row_stride * 0.30))
    corner_dx = max(10, int(col_stride * 0.30))

    return row_centers, col_centers, corner_dy, corner_dx


def classify_cell_v2(arr, y_c, x_c, corner_dy=28, corner_dx=25):
    """Corner-based classification with 4-action support.
    Returns (action, raise_pct) where raise_pct is the non-fold ratio for mixed cells.
    """
    h, w = arr.shape[:2]
    red = orange = teal = blue = 0
    for ddx in (-corner_dx, corner_dx):
        for ddy in (-corner_dy, corner_dy):
            cx, cy = x_c + ddx, y_c + ddy
            region = arr[max(0,cy-2):cy+3, max(0,cx-2):cx+3]
            for row_p in region:
                for p in row_p:
                    r, g, b = int(p[0]), int(p[1]), int(p[2])
                    if is_red(r, g, b):    red += 1
                    elif is_orange(r, g, b): orange += 1
                    elif is_blue(r, g, b): blue += 1
                    elif is_teal(r, g, b): teal += 1
    counts = {"allin": red, "raise": orange, "call": teal, "fold": blue}
    total = sum(counts.values())
    best = max(counts, key=counts.get)
    if total == 0 or counts[best] == 0:
        return "fold", 0.0
    # Mixed: dominant color is 50% or less of total → split cell
    if counts[best] <= total * 0.5:
        action_px = red + orange + teal  # non-fold pixels
        raise_pct = round(action_px / total, 2) if total > 0 else 0.5
        return "mixed", raise_pct
    return best, 0.0


def hand_at(row, col):
    r1, r2 = RANKS[row], RANKS[col]
    if row < col: return f"{r1}{r2}s"
    if row > col: return f"{r2}{r1}o"
    return f"{r1}{r2}"


def extract_from_crop(arr, row_centers, col_centers, corner_dy, corner_dx):
    """Extract hands by action from a crop array using given row/col centers."""
    raise_h, allin_h, call_h = [], [], []
    mixed_h = {}  # hand -> raise_pct
    for row in range(13):
        y_c = row_centers[row]
        for col in range(13):
            x_c = col_centers[col]
            if x_c >= arr.shape[1] or y_c >= arr.shape[0]:
                continue
            action, raise_pct = classify_cell_v2(arr, y_c, x_c, corner_dy, corner_dx)
            hand = hand_at(row, col)
            if action == "raise":
                raise_h.append(hand)
            elif action == "allin":
                allin_h.append(hand)
            elif action == "call":
                call_h.append(hand)
            elif action == "mixed":
                mixed_h[hand] = raise_pct
    return raise_h, allin_h, call_h, mixed_h


# ── Main processing ───────────────────────────────────────────────────────────
def render_rfi_page(pdf_key, zoom=5.0):
    """Render page index 2 (RFI page) at given zoom."""
    doc = fitz.open(str(PDF_DIR / f"{pdf_key}.pdf"))
    if len(doc) < 3:
        return None
    page = doc[2]
    pix  = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def get_crop_coords(cfg):
    """Return (x_start, y_start) for each position crop."""
    positions = cfg["positions"]
    n = len(positions)
    top_n   = 4 if n > 4 else n
    bot_n   = n - top_n
    coords  = [(GRID_STARTS_X[i], TOP_ROW_Y) for i in range(top_n)]
    coords += [(GRID_STARTS_X[i], BOT_ROW_Y) for i in range(bot_n)]
    return coords


def process_pdf(pdf_key, force=False):
    cfg = PDF_CONFIGS.get(pdf_key)
    if not cfg:
        print(f"  Unknown key: {pdf_key}")
        return

    positions = cfg["positions"]
    is_6max   = pdf_key.startswith("6max")
    out_dir   = OUT_DIR / pdf_key / "rfi"
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [p for p in positions if not (out_dir / f"{p}.json").exists()]
    if not missing and not force:
        print(f"  {pdf_key}: already complete, skipping")
        return

    # Create crops if needed
    crops_needed = force or not all(
        (CROP_DIR / f"{pdf_key}_rfi_{pos}.png").exists() for pos in positions
    )
    if crops_needed:
        print(f"  Rendering {pdf_key}...")
        full_img = render_rfi_page(pdf_key)
        if full_img is None:
            print(f"  ERROR: could not render {pdf_key}")
            return
        for pos, (x0, y0) in zip(positions, get_crop_coords(cfg)):
            crop = full_img.crop((x0, y0, x0 + GRID_W, y0 + GRID_H))
            crop.save(str(CROP_DIR / f"{pdf_key}_rfi_{pos}.png"))

    # Extract each position
    print(f"  Extracting {cfg['label']}:")
    for pos in positions:
        if (out_dir / f"{pos}.json").exists() and not force:
            continue
        crop_path = CROP_DIR / f"{pdf_key}_rfi_{pos}.png"
        if not crop_path.exists():
            print(f"    {pos}: crop missing, skipping")
            continue

        arr = np.array(Image.open(str(crop_path)))

        grid = detect_grid(arr)
        if grid is None:
            print(f"    {pos}: could not detect grid")
            continue
        row_centers, col_centers, c_dy, c_dx = grid

        raise_h, allin_h, call_h, mixed_h = extract_from_crop(arr, row_centers, col_centers, c_dy, c_dx)

        result = {"raise": raise_h, "pct_raise": round(len(raise_h)/169*100, 2)}
        if allin_h:
            result["allin"]     = allin_h
            result["pct_allin"] = round(len(allin_h)/169*100, 2)
        if call_h:
            result["call"]     = call_h
            result["pct_call"] = round(len(call_h)/169*100, 2)
        if mixed_h:
            result["mixed"] = mixed_h  # dict: hand -> raise_pct

        with open(out_dir / f"{pos}.json", "w") as f:
            json.dump(result, f)

        parts = [f"{len(raise_h)} raise ({result['pct_raise']:.1f}%)"]
        if allin_h: parts.append(f"{len(allin_h)} allin ({result['pct_allin']:.1f}%)")
        if call_h:  parts.append(f"{len(call_h)} call ({result['pct_call']:.1f}%)")
        if mixed_h: parts.append(f"{len(mixed_h)} mixed")
        print(f"    {pos}: {' + '.join(parts)}")


def main():
    force = "--force" in sys.argv
    keys  = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not keys:
        keys = list(PDF_CONFIGS.keys())
    for key in keys:
        print(f"\n[{key}]")
        process_pdf(key, force=force)
    print("\nDone.")


if __name__ == "__main__":
    main()
