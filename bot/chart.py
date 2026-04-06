"""Range chart image generation using Pillow."""
from io import BytesIO
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config import RANKS

# Colors for each action type
ACTION_COLORS = {
    "fold":     (120, 120, 120),  # gray
    "check":    (120, 120, 120),  # gray
    "call":     ( 76, 175,  80),  # green
    "3bet":     (229,  57,  53),  # red
    "squeeze":  (229,  57,  53),  # red
    "4bet":     (255, 152,   0),  # orange
    "all-in":   (156,  39, 176),  # purple
    "raise":    ( 33, 150, 243),  # blue
    "limp":     (255, 235,  59),  # yellow
}

HIGHLIGHT_COLOR = (255, 255, 255)
BG_COLOR = (30, 30, 30)
TEXT_COLOR = (255, 255, 255)
TEXT_COLOR_DARK = (0, 0, 0)
GRID_COLOR = (60, 60, 60)

CELL_SIZE = 42
HEADER_SIZE = 22
PADDING = 8
FONT_SIZE = 12
HEADER_FONT_SIZE = 11


def _classify_action(action: str) -> str:
    """Classify an action string into a color category."""
    a = action.lower().strip()
    if a == "fold":
        return "fold"
    if a == "check":
        return "check"
    if a == "call":
        return "call"
    if a.startswith("3bet") or a.startswith("squeeze"):
        return "3bet"
    if a.startswith("4bet"):
        return "4bet"
    if a == "all-in":
        return "all-in"
    if a.startswith("raise"):
        return "raise"
    if a == "limp" or a == "limp behind":
        return "limp"
    return "fold"


def _get_action_color(action: str) -> tuple:
    return ACTION_COLORS.get(_classify_action(action), ACTION_COLORS["fold"])


def _hand_at_grid(row: int, col: int) -> str:
    """Get hand name at grid position. Row=first rank index, Col=second rank index."""
    r1, r2 = RANKS[row], RANKS[col]
    if row < col:
        return f"{r1}{r2}s"
    elif row > col:
        return f"{r2}{r1}o"
    else:
        return f"{r1}{r2}"


def _try_load_font(size: int):
    """Try to load a monospace font, fall back to default."""
    font_paths = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFMono-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_range_chart(
    scenario_hands: dict,
    actions: list[str],
    highlight_hand: Optional[str] = None,
    title: str = "",
) -> bytes:
    """Generate a 13x13 range chart PNG.

    Args:
        scenario_hands: dict of hand_name -> {"ev_vs_best": {...}, "strategy": {...}}
        actions: list of action names for this scenario
        highlight_hand: hand name to highlight (current quiz hand)
        title: chart title

    Returns:
        PNG image bytes
    """
    grid_size = 13
    total_w = PADDING * 2 + HEADER_SIZE + grid_size * CELL_SIZE
    title_height = 28 if title else 0
    legend_height = 28
    total_h = PADDING * 2 + HEADER_SIZE + grid_size * CELL_SIZE + title_height + legend_height

    img = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font = _try_load_font(FONT_SIZE)
    header_font = _try_load_font(HEADER_FONT_SIZE)
    title_font = _try_load_font(FONT_SIZE + 2)

    y_offset = PADDING
    if title:
        draw.text((PADDING, y_offset), title, fill=TEXT_COLOR, font=title_font)
        y_offset += title_height

    # Draw column headers
    for col in range(grid_size):
        x = PADDING + HEADER_SIZE + col * CELL_SIZE + CELL_SIZE // 2
        y = y_offset
        draw.text((x - 4, y), RANKS[col], fill=TEXT_COLOR, font=header_font)

    # Draw row headers and cells
    for row in range(grid_size):
        # Row header
        rx = PADDING
        ry = y_offset + HEADER_SIZE + row * CELL_SIZE + CELL_SIZE // 2 - 6
        draw.text((rx + 2, ry), RANKS[row], fill=TEXT_COLOR, font=header_font)

        for col in range(grid_size):
            hand = _hand_at_grid(row, col)
            x = PADDING + HEADER_SIZE + col * CELL_SIZE
            y = y_offset + HEADER_SIZE + row * CELL_SIZE

            # Determine best action color
            hand_data = scenario_hands.get(hand, {})
            ev_best = hand_data.get("ev_vs_best", {})

            if ev_best:
                best_action = max(ev_best, key=ev_best.get)
                color = _get_action_color(best_action)
            else:
                color = ACTION_COLORS["fold"]

            # Draw cell
            draw.rectangle(
                [x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1],
                fill=color
            )

            # Draw hand label
            label = hand
            # Choose text color based on background brightness
            brightness = color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114
            tc = TEXT_COLOR_DARK if brightness > 128 else TEXT_COLOR
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x + (CELL_SIZE - tw) // 2
            ty = y + (CELL_SIZE - th) // 2
            draw.text((tx, ty), label, fill=tc, font=font)

            # Highlight current hand
            if highlight_hand and hand == highlight_hand:
                draw.rectangle(
                    [x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1],
                    outline=HIGHLIGHT_COLOR,
                    width=3
                )

    # Draw grid lines
    for i in range(grid_size + 1):
        x = PADDING + HEADER_SIZE + i * CELL_SIZE
        y0 = y_offset + HEADER_SIZE
        y1 = y_offset + HEADER_SIZE + grid_size * CELL_SIZE
        draw.line([(x, y0), (x, y1)], fill=GRID_COLOR, width=1)

        y = y_offset + HEADER_SIZE + i * CELL_SIZE
        x0 = PADDING + HEADER_SIZE
        x1 = PADDING + HEADER_SIZE + grid_size * CELL_SIZE
        draw.line([(x0, y), (x1, y)], fill=GRID_COLOR, width=1)

    # Draw legend
    legend_y = y_offset + HEADER_SIZE + grid_size * CELL_SIZE + 6
    legend_x = PADDING + HEADER_SIZE

    # Collect unique action categories present in this scenario
    seen_categories = set()
    for action in actions:
        cat = _classify_action(action)
        if cat not in seen_categories:
            seen_categories.add(cat)
            c = ACTION_COLORS.get(cat, ACTION_COLORS["fold"])
            draw.rectangle(
                [legend_x, legend_y, legend_x + 14, legend_y + 14],
                fill=c
            )
            draw.text(
                (legend_x + 18, legend_y),
                action,
                fill=TEXT_COLOR,
                font=header_font
            )
            bbox = draw.textbbox((0, 0), action, font=header_font)
            legend_x += 18 + (bbox[2] - bbox[0]) + 12

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def combine_with_crop(chart_bytes: bytes, crop_path: str) -> bytes:
    """Combine range chart with original PDF crop side-by-side.

    Crops the PDF image to just the grid area (y=363..1455) for alignment
    with the generated chart grid.
    """
    import os
    if not os.path.exists(crop_path):
        return chart_bytes

    chart = Image.open(BytesIO(chart_bytes))
    crop  = Image.open(crop_path)

    # Crop to grid data area only (skip header/title/row-header column)
    # Original crop is 1025x1490. Grid data area:
    #   y: 363..1455 (skip title+col headers at top)
    #   x: 72..982   (skip row-header column on left, margin on right)
    cw, ch = crop.width, crop.height
    grid_top  = int(363  / 1490 * ch)
    grid_bot  = int(1455 / 1490 * ch)
    grid_left = int(72   / 1025 * cw)
    grid_right = int(982 / 1025 * cw)
    crop = crop.crop((grid_left, grid_top, grid_right, grid_bot))

    # Scale to match chart's grid area (below title+header)
    title_h = 28
    header_h = HEADER_SIZE
    grid_h = 13 * CELL_SIZE
    chart_grid_top = PADDING + title_h + header_h
    chart_grid_h = grid_h

    scale = chart_grid_h / crop.height
    new_w = int(crop.width * scale)
    crop = crop.resize((new_w, chart_grid_h), Image.LANCZOS)

    # Place crop aligned with chart grid
    combined_h = chart.height
    combined = Image.new("RGB", (chart.width + 4 + new_w, combined_h), (10, 10, 10))
    combined.paste(chart, (0, 0))
    combined.paste(crop, (chart.width + 4, chart_grid_top))

    buf = BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()


# Colors for open range chart (binary in/out)
OPEN_IN_COLOR  = ( 67, 160,  71)   # green
OPEN_OUT_COLOR = ( 55,  55,  55)   # dark gray (on black bg looks clearly distinct)
OPEN_BG_COLOR  = (  0,   0,   0)   # pure black background
OPEN_HIGHLIGHT = (255, 220,   0)   # yellow border for quiz hand


OPEN_CALL_COLOR = (255, 165,   0)   # orange (limp/call)


def generate_open_range_chart(
    in_range_hands: frozenset,
    call_hands: frozenset = None,
    highlight_hand: Optional[str] = None,
    title: str = "",
) -> bytes:
    """Generate a 13x13 open range chart.
      green = raise/open, orange = call/limp, gray = fold.

    Args:
        in_range_hands: set of raise hands
        call_hands: set of call/limp hands (SB)
        highlight_hand: hand to mark with a yellow border
        title: chart title
    """
    grid_size = 13
    total_w = PADDING * 2 + HEADER_SIZE + grid_size * CELL_SIZE
    title_height = 28 if title else 0
    total_h = PADDING * 2 + HEADER_SIZE + grid_size * CELL_SIZE + title_height

    img = Image.new("RGB", (total_w, total_h), OPEN_BG_COLOR)
    draw = ImageDraw.Draw(img)

    font = _try_load_font(FONT_SIZE)
    header_font = _try_load_font(HEADER_FONT_SIZE)
    title_font = _try_load_font(FONT_SIZE + 2)

    y_offset = PADDING
    if title:
        draw.text((PADDING, y_offset), title, fill=TEXT_COLOR, font=title_font)
        y_offset += title_height

    # Column headers
    for col in range(grid_size):
        x = PADDING + HEADER_SIZE + col * CELL_SIZE + CELL_SIZE // 2
        draw.text((x - 4, y_offset), RANKS[col], fill=TEXT_COLOR, font=header_font)

    # Cells
    for row in range(grid_size):
        rx = PADDING
        ry = y_offset + HEADER_SIZE + row * CELL_SIZE + CELL_SIZE // 2 - 6
        draw.text((rx + 2, ry), RANKS[row], fill=TEXT_COLOR, font=header_font)

        for col in range(grid_size):
            hand = _hand_at_grid(row, col)
            x = PADDING + HEADER_SIZE + col * CELL_SIZE
            y = y_offset + HEADER_SIZE + row * CELL_SIZE

            if hand in in_range_hands:
                color = OPEN_IN_COLOR
            elif call_hands and hand in call_hands:
                color = OPEN_CALL_COLOR
            else:
                color = OPEN_OUT_COLOR
            draw.rectangle(
                [x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1],
                fill=color,
            )

            label = hand
            brightness = color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114
            tc = TEXT_COLOR_DARK if brightness > 128 else TEXT_COLOR
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x + (CELL_SIZE - tw) // 2, y + (CELL_SIZE - th) // 2),
                      label, fill=tc, font=font)

            if highlight_hand and hand == highlight_hand:
                draw.rectangle(
                    [x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1],
                    outline=OPEN_HIGHLIGHT,
                    width=3,
                )

    # Grid lines
    for i in range(grid_size + 1):
        x = PADDING + HEADER_SIZE + i * CELL_SIZE
        y0 = y_offset + HEADER_SIZE
        y1 = y_offset + HEADER_SIZE + grid_size * CELL_SIZE
        draw.line([(x, y0), (x, y1)], fill=GRID_COLOR, width=1)

        y = y_offset + HEADER_SIZE + i * CELL_SIZE
        x0 = PADDING + HEADER_SIZE
        x1 = PADDING + HEADER_SIZE + grid_size * CELL_SIZE
        draw.line([(x0, y), (x1, y)], fill=GRID_COLOR, width=1)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
