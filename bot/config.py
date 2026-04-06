import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"
EV_TABLES_DIR = DATA_DIR / "ev_tables"
DB_PATH = DATA_DIR / "bankroll.db"
PDF_RANGES_FILE = DATA_DIR / "pdf_ranges.json"

STARTING_BANKROLL = 100.0

# Hand selection weights
MARGINAL_EV_THRESHOLD = 0.5  # EV gap < this = marginal (high weight)
OBVIOUS_FOLD_EV_GAP = 3.0   # EV gap > this = obvious fold (low weight)

# Recent history dedup
RECENT_HISTORY_SIZE = 50

# 13x13 hand grid: rows = first card, cols = second card
# Upper triangle = suited, lower triangle = offsuit, diagonal = pairs
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

ALL_HANDS_169 = []
for i, r1 in enumerate(RANKS):
    for j, r2 in enumerate(RANKS):
        if i < j:
            ALL_HANDS_169.append(f"{r1}{r2}s")
        elif i > j:
            ALL_HANDS_169.append(f"{r2}{r1}o")
        else:
            ALL_HANDS_169.append(f"{r1}{r2}")
