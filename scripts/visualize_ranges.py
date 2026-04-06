#!/usr/bin/env python3
"""
Visualize extracted ranges side-by-side with the original PDF crop.

Usage:
  python3 scripts/visualize_ranges.py              # all formats
  python3 scripts/visualize_ranges.py 6max_40bb    # specific format
  python3 scripts/visualize_ranges.py 6max_40bb CO # specific format + position
"""
import sys, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT      = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"
CROP_DIR  = Path("/tmp/rc_crops")
OUT_DIR   = ROOT / "data" / "validation"

RANKS = "AKQJT98765432"

RAISE_COLOR = (255, 140, 0)    # orange
CALL_COLOR  = (100, 200, 100)  # green
FOLD_COLOR  = (60, 60, 60)     # dark gray
BG_COLOR    = (20, 20, 20)
TEXT_COLOR  = (255, 255, 255)
TEXT_DARK   = (0, 0, 0)
HIGHLIGHT   = (255, 50, 50)    # red border for hands removed by correction

CELL = 40
HEADER = 20
PAD = 6


def hand_at(row, col):
    r1, r2 = RANKS[row], RANKS[col]
    if row < col: return f"{r1}{r2}s"
    if row > col: return f"{r2}{r1}o"
    return f"{r1}{r2}"


def _load_font(size):
    for fp in ["/System/Library/Fonts/Menlo.ttc",
               "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_grid(raise_h: frozenset, call_h: frozenset, title: str) -> Image.Image:
    grid = 13
    w = PAD * 2 + HEADER + grid * CELL
    h = PAD * 2 + HEADER + grid * CELL + 20  # +20 for title
    img = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = _load_font(10)
    hdr  = _load_font(9)

    draw.text((PAD, PAD), title, fill=TEXT_COLOR, font=hdr)
    y0 = PAD + 16

    for col in range(grid):
        x = PAD + HEADER + col * CELL + CELL // 2 - 4
        draw.text((x, y0), RANKS[col], fill=TEXT_COLOR, font=hdr)

    for row in range(grid):
        ry = y0 + HEADER + row * CELL + CELL // 2 - 5
        draw.text((PAD + 2, ry), RANKS[row], fill=TEXT_COLOR, font=hdr)

        for col in range(grid):
            hand = hand_at(row, col)
            x = PAD + HEADER + col * CELL
            y = y0 + HEADER + row * CELL

            if hand in raise_h:
                color = RAISE_COLOR
            elif hand in call_h:
                color = CALL_COLOR
            else:
                color = FOLD_COLOR

            draw.rectangle([x+1, y+1, x+CELL-1, y+CELL-1], fill=color)

            brightness = color[0]*0.299 + color[1]*0.587 + color[2]*0.114
            tc = TEXT_DARK if brightness > 128 else TEXT_COLOR
            bbox = draw.textbbox((0,0), hand, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text((x + (CELL-tw)//2, y + (CELL-th)//2), hand, fill=tc, font=font)

    return img


def make_comparison(fmt: str, pos: str):
    range_path = RANGES_DIR / fmt / "rfi" / f"{pos}.json"
    if not range_path.exists():
        print(f"  {pos}: no range data, skipping")
        return

    with open(range_path) as f:
        data = json.load(f)
    raise_h = frozenset(data.get("raise", []))
    call_h  = frozenset(data.get("call", []))
    pct_r   = data.get("pct_raise", 0)
    pct_c   = data.get("pct_call", 0)

    grid_img = render_grid(raise_h, call_h,
                           f"{fmt} {pos} | raise={pct_r:.1f}%  call={pct_c:.1f}%")

    crop_path = CROP_DIR / f"{fmt}_rfi_{pos}.png"
    if crop_path.exists():
        crop = Image.open(str(crop_path))
        # Scale crop to same height as grid
        target_h = grid_img.height
        scale = target_h / crop.height
        crop = crop.resize((int(crop.width * scale), target_h), Image.LANCZOS)

        combined = Image.new("RGB", (grid_img.width + crop.width + 4, target_h), (10,10,10))
        combined.paste(grid_img, (0, 0))
        combined.paste(crop, (grid_img.width + 4, 0))
    else:
        combined = grid_img

    out_dir = OUT_DIR / fmt
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pos}.png"
    combined.save(str(out_path))
    pct_info = f" + call={pct_c:.1f}%" if pct_c else ""
    print(f"  {pos}: raise={pct_r:.1f}%{pct_info} → {out_path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) >= 2:
        fmt, pos = args[0], args[1].upper()
        print(f"[{fmt} {pos}]")
        make_comparison(fmt, pos)
    elif len(args) == 1:
        fmt = args[0]
        fmt_dir = RANGES_DIR / fmt / "rfi"
        if not fmt_dir.exists():
            print(f"No data for {fmt}")
            return
        positions = sorted(p.stem for p in fmt_dir.glob("*.json"))
        print(f"[{fmt}]")
        for pos in positions:
            make_comparison(fmt, pos)
    else:
        for fmt_dir in sorted(RANGES_DIR.iterdir()):
            rfi_dir = fmt_dir / "rfi"
            if not rfi_dir.exists():
                continue
            print(f"\n[{fmt_dir.name}]")
            for path in sorted(rfi_dir.glob("*.json")):
                make_comparison(fmt_dir.name, path.stem)

    print("\nDone. Images saved to data/validation/")


if __name__ == "__main__":
    main()
