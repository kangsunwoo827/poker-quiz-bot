#!/usr/bin/env python3
"""Write AI-classified range data directly to JSON files."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"

RANKS = "AKQJT98765432"
ALL_169 = []
for i in range(13):
    for j in range(13):
        r1, r2 = RANKS[i], RANKS[j]
        if i < j: ALL_169.append(f"{r1}{r2}s")
        elif i > j: ALL_169.append(f"{r2}{r1}o")
        else: ALL_169.append(f"{r1}{r2}")

def call_from_fold(raise_h, mixed_h, fold_h, allin_h=None):
    """Compute call list = all 169 - raise - mixed - fold - allin."""
    exclude = set(raise_h) | set(mixed_h or []) | set(fold_h) | set(allin_h or [])
    return [h for h in ALL_169 if h not in exclude]

def write_range(fmt, pos, raise_h, allin_h=None, call_h=None, mixed_h=None):
    out_dir = RANGES_DIR / fmt / "rfi"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Deduplicate: mixed takes priority, then raise, then allin, then call
    mixed_set = set(mixed_h or [])
    raise_h = [h for h in raise_h if h not in mixed_set]
    if allin_h:
        allin_h = [h for h in allin_h if h not in mixed_set and h not in set(raise_h)]
    if call_h:
        exclude = mixed_set | set(raise_h) | set(allin_h or [])
        call_h = [h for h in call_h if h not in exclude]
    result = {"raise": raise_h, "pct_raise": round(len(raise_h)/169*100, 2)}
    if allin_h:
        result["allin"] = allin_h
        result["pct_allin"] = round(len(allin_h)/169*100, 2)
    if call_h:
        result["call"] = call_h
        result["pct_call"] = round(len(call_h)/169*100, 2)
    if mixed_h:
        # mixed as dict with 0.5 default
        result["mixed"] = {h: 0.5 for h in mixed_h}
    with open(out_dir / f"{pos}.json", "w") as f:
        json.dump(result, f)
    total = len(raise_h) + len(allin_h or []) + len(call_h or []) + len(mixed_h or [])
    print(f"  {fmt}/{pos}: {len(raise_h)}r", end="")
    if allin_h: print(f" + {len(allin_h)}a", end="")
    if call_h: print(f" + {len(call_h)}c", end="")
    if mixed_h: print(f" + {len(mixed_h)}m", end="")
    print(f" = {total} ({total/169*100:.1f}%)")


# ============================================================
# 9max_100bb — B-team (footer-calibrated) results
# ============================================================
print("\n[9max_100bb]")

write_range("9max_100bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","AKs","AQs","AJs","ATs","KQs","KJs","KTs","QJs","JTs","AKo","AQo"],
    mixed_h=["88","QTs","A5s","K9s","AJo"])

write_range("9max_100bb", "UTG+1",
    # Slightly wider than UTG. A-team/B-team consensus + interpolation
    raise_h=["AA","KK","QQ","JJ","TT","99","AKs","AQs","AJs","ATs","KQs","KJs","KTs","QJs","QTs","JTs","AKo","AQo","KQo"],
    mixed_h=["88","A5s","K9s","J9s","T9s","AJo"])

write_range("9max_100bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","AKs","AQs","AJs","ATs","A5s","KQs","KJs","KTs","QJs","QTs","JTs","J9s","T9s","AKo","AQo"],
    mixed_h=["77","A9s","A4s","A3s","K9s","Q9s","K5s","K6s","AJo","T9o","98o","87o"])

write_range("9max_100bb", "LJ",
    # Between MP and HJ. Interpolated from both teams.
    raise_h=["AA","KK","QQ","JJ","TT","99","88","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","Q9s","JTs","J9s","T9s","98s","AKo","AQo","KQo"],
    mixed_h=["77","A7s","A6s","K8s","KJo","J8s","87s"])

write_range("9max_100bb", "HJ",
    # Similar to LJ but slightly wider
    raise_h=["AA","KK","QQ","JJ","TT","99","88","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","Q8s","JTs","J9s","T9s","98s","87s","AKo","AQo","KQo","AJo"],
    mixed_h=["77","A7s","A6s","K7s","KJo","J8s","T8s","76s"])

write_range("9max_100bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K6s","K5s","QJs","QTs","Q9s","JTs","J9s","J8s","T9s","T8s","98s","97s","87s","AKo","AQo","AJo","KQo","KJo","QJo","ATo","KTo","QTo","JTo"],
    mixed_h=["K7s","K4s","Q8s","T7s","86s","76s","65s","55","54s","44","33","A9o"])

write_range("9max_100bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","JTs","J9s","J8s","J7s","J6s","J5s","T9s","T8s","T7s","T6s","98s","97s","96s","95s","87s","86s","85s","76s","65s","54s","AKo","AQo","AJo","KQo","KJo","QJo","ATo","KTo","QTo","JTo"],
    mixed_h=["44","33","K2s","Q4s","Q3s","J4s","T5s","73s","64s","53s","43s","32s","A9o","K9o","A8o","K8o","Q9o","J9o","87o"])

write_range("9max_100bb", "SB",
    # A-team: 79, B-team: 80. Consensus around 78-80.
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","JTs","J9s","J8s","J7s","J6s","J5s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","95s","87s","86s","85s","76s","75s","65s","54s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","KQo","KJo","KTo","K9o","K8o","K7o","QJo","QTo","JTo","T9o","98o","87o"],
    mixed_h=["94s","84s","74s","64s","43s","A6o","A5o","Q9o","J9o"])

# ============================================================
# 6max_100bb — B-team results (A-team as secondary)
# ============================================================
print("\n[6max_100bb]")

write_range("6max_100bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","JTs","T9s","98s","87s","76s","65s","AKo","AQo","AJo","KQo"],
    mixed_h=["A8s","Q9s","J9s"])

write_range("6max_100bb", "MP",
    # Slightly wider than UTG
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","Q9s","JTs","J9s","T9s","98s","87s","76s","AKo","AQo","AJo","KQo","KJo"],
    mixed_h=["55","A7s","K8s","QJo"])

write_range("6max_100bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","54s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","JTo"],
    mixed_h=["33","22","K7s","Q8s","J8s","86s","A9o"])

write_range("6max_100bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","T9s","T8s","T7s","T6s","T5s","98s","97s","87s","86s","76s","65s","54s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","KQo","KJo","KTo","K9o","QJo","QTo","JTo","J9o","T9o","98o","87o","76o"],
    mixed_h=["K2s","Q6s","Q5s","J7s","96s","85s","75s","64s","53s","43s"])

write_range("6max_100bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","JTs","T9s","98s","87s","76s","65s","54s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo","T9o","98o","87o"],
    call_h=["A7s","A6s","A4s","A3s","A2s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","Q9s","Q8s","Q7s","Q6s","Q5s","J9s","J8s","J7s","J6s","J5s","T8s","T7s","T6s","T5s","97s","96s","95s","86s","85s","84s","75s","74s","64s","63s","53s","52s","43s","42s","32s","A9o","A8o","A7o","A6o","A5o","K9o","K8o","Q9o","J9o","T8o"],
    mixed_h=[])


# ============================================================
# mtt_60bb — AI-classified from crop images
# ============================================================
print("\n[mtt_60bb]")

write_range("mtt_60bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","JTs","J9s","T9s","T8s","98s","87s","AKo","AQo","KQo"],
    mixed_h=["99","77","66","55","44","22","A7s","K7s","Q9s","J8s","76s","AJo","KJo","QJo"])

write_range("mtt_60bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","JTs","J9s","T9s","T8s","98s","87s","AKo","AQo","KQo"],
    mixed_h=["99","77","66","55","44","33","22","A7s","K7s","Q9s","J8s","76s","AJo","KJo","QJo"])

write_range("mtt_60bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","J8s","T9s","T8s","98s","87s","76s","AKo","AQo","AJo","KQo","KJo","QJo"],
    mixed_h=["99","88","77","66","55","44","22","A4s","A3s","A2s","K7s","K5s"])

write_range("mtt_60bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","T7s","98s","97s","87s","86s","76s","65s","54s","AKo","AQo","AJo","KQo","KJo","QJo"],
    mixed_h=["88","77","66","55","44","33","22","K6s","Q7s","J7s","T6s","96s","75s","64s"])

write_range("mtt_60bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","J7s","T9s","T8s","T7s","98s","97s","96s","87s","86s","85s","76s","75s","65s","64s","54s","43s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["88","77","66","K4s","Q6s","J6s","T6s","53s","A9o","K9o","Q9o","J9o"])

write_range("mtt_60bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","JTs","J9s","J8s","J7s","J6s","J5s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","95s","87s","86s","85s","84s","76s","75s","65s","64s","54s","53s","43s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","KQo","KJo","KTo","K9o","K8o","K7o","K6o","QJo","QTo","Q9o","Q8o","JTo","J9o","J8o","T9o","T8o","98o","97o","87o","86o","76o","65o"],
    mixed_h=["K2s","Q4s","Q3s","J4s","J3s","T4s","T3s","94s","93s","83s","73s","63s","52s","42s","32s","K5o","K4o","Q7o","Q6o","J7o","T7o","85o","75o","54o"])

write_range("mtt_60bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","99","AKs","AQs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","JTs","J9s","T9s","T8s","98s","87s","76s","AKo","AQo","AJo","ATo","KQo","KJo","QJo"],
    call_h=["88","77","66","55","44","33","22","AJs","A7s","A6s","A5s","A4s","A3s","A2s","K7s","K6s","K5s","K4s","K3s","K2s","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s","J8s","J7s","J6s","J5s","J4s","J3s","J2s","T7s","T6s","T5s","T4s","T3s","T2s","97s","96s","95s","94s","93s","92s","86s","85s","84s","83s","82s","75s","74s","73s","72s","65s","64s","63s","62s","54s","53s","52s","43s","42s","32s","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","KTo","K9o","K8o","K7o","K6o","K5o","K4o","K3o","K2o","QTo","Q9o","Q8o","Q7o","Q6o","Q5o","Q4o","Q3o","JTo","J9o","J8o","J7o","J6o","J5o","J4o","T9o","T8o","T7o","T6o","T5o","98o","97o","96o","95o","87o","86o","85o","84o","76o","75o","74o","65o","64o","54o","53o","43o"],
    mixed_h=["A3o","Q2o","J3o","T4o","94o","83o","73o","63o","52o","42o","32o"])

# ============================================================
# mtt_30bb — AI-classified from crop images
# ============================================================
print("\n[mtt_30bb]")

write_range("mtt_30bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","55","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo"],
    mixed_h=["A5s","A4s","KQo"])

write_range("mtt_30bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","99","55","AKs","AQs","AJs","ATs","A9s","A8s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo"],
    mixed_h=["KQo","54s"])

write_range("mtt_30bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","55","AKs","AQs","AJs","ATs","A9s","A8s","A5s","A2s","KQs","KJs","KTs","K9s","K8s","K5s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo"],
    mixed_h=["A4s","A3s","KQo","54s"])

write_range("mtt_30bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","A2s","KQs","KJs","KTs","K9s","K8s","K5s","QJs","QTs","Q9s","Q8s","Q5s","JTs","J9s","J8s","J6s","T9s","T8s","98s","97s","87s","86s","76s","75s","65s","AKo"],
    mixed_h=["A3s","KQo","K3s","J3s","54s","85s","96s","T5s"])

write_range("mtt_30bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q6s","Q5s","JTs","J9s","J8s","J6s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","87s","86s","85s","76s","75s","65s","64s","54s","AKo","AQo","KQo","KJo","QJo","JTo","65o","54o"],
    mixed_h=["K2s","Q4s","43s"])

write_range("mtt_30bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s","JTs","J9s","J8s","J7s","J6s","J5s","J4s","J3s","J2s","T9s","T8s","T7s","T6s","T5s","T4s","T3s","T2s","98s","97s","96s","95s","94s","93s","92s","87s","86s","85s","84s","83s","82s","76s","75s","74s","73s","72s","65s","64s","63s","62s","54s","53s","52s","43s","42s","32s","AKo","AQo","AJo","ATo","A9o","KQo","KJo","KTo","K9o","QJo","QTo","Q9o","JTo","J9o","T9o"],
    mixed_h=["A8o","A5o","A4o","A3o","85o"])

write_range("mtt_30bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","97s","87s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo"],
    call_h=["22","A4o","A3o","A2o","K4s","K3s","K2s","K7o","K6o","K5o","K4o","K3o","K2o","Q4s","Q3s","Q2s","Q7o","Q6o","Q5o","Q4o","Q3o","Q2o","J5s","J4s","J3s","J2s","J7o","J6o","J5o","J4o","J3o","J2o","T5s","T4s","T3s","T2s","T8o","T7o","T6o","T5o","T4o","T3o","T2o","95s","94s","93s","92s","97o","96o","95o","94o","93o","92o","85s","84s","83s","82s","86o","85o","84o","83o","82o","74s","73s","72s","76o","75o","74o","73o","72o","63s","62s","65o","64o","63o","62o","52s","42s","32s","54o","53o","52o","43o","42o","32o"],
    mixed_h=["A7s","A6s","A4s","A3s","A2s","A9o","A8o","A7o","A6o","A5o","K7s","K6s","K5s","K9o","K8o","Q8s","Q7s","Q6s","Q5s","Q9o","Q8o","J8s","J7s","J6s","J9o","J8o","T7s","T6s","T9o","96s","98o","86s","87o","76s","75s","65s","64s","54s","53s","44","33","43s"])

# ============================================================
# mtt_20bb — AI-classified from crop images
# ============================================================
print("\n[mtt_20bb]")

write_range("mtt_20bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","Q8s","JTs","J9s","T9s","T8s","98s","87s","76s","AKo","AQo","KQo","KJo","QJo"])

write_range("mtt_20bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","Q8s","JTs","J9s","T9s","T8s","98s","87s","76s","AKo","AQo","KQo","KJo","QJo"])

write_range("mtt_20bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","Q8s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","AJo","KQo","KJo","QJo","QTo","JTo"],
    mixed_h=["A7s","K6s","T9o"])

write_range("mtt_20bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","98s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["Q7s","97s","64s"])

write_range("mtt_20bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","T9s","T8s","T7s","98s","97s","87s","86s","76s","75s","65s","64s","54s","AKo","AQo","AJo","ATo","A9o","KQo","KJo","KTo","K9o","QJo","QTo","Q9o","JTo","J9o","T9o"],
    mixed_h=["A2s","K5s","Q6s","J7s","96s","85s","53s","A8o","K8o","Q9o","T8o"])

write_range("mtt_20bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","JTs","J9s","J8s","J7s","T9s","T8s","T7s","98s","97s","96s","87s","86s","76s","75s","65s","64s","54s","53s","AKo","AQo","AJo","ATo","A9o","A8o","KQo","KJo","KTo","K9o","K8o","QJo","QTo","Q9o","JTo","J9o","T9o","T8o","98o","87o"],
    allin_h=["44","33","22","43s","42s","32s","A5o","A4o","A3o","A2o","K7o","K6o","K5o","Q8o","J8o","T7o","97o","86o","76o","65o"],
    mixed_h=["Q4s","J6s","T6s","95s","85s","74s","63s","A7o","A6o","Q7o","J9o","87o","54o"])

write_range("mtt_20bb", "SB",
    raise_h=["AA","KK","QQ","AKs","AQs","AJs","AKo"],
    allin_h=["55","44","33","22","A5s","A4s","A3s","A2s","A5o","A4o","A3o","A2o","K7o","K6o","K5o","Q8o","Q7o","Q6o","Q5o","J8o","J7o","J6o","T7o","T6o","96o","85o","74o","64o","53o","43o"],
    call_h=["K6s","K5s","K4s","K3s","K2s","Q5s","Q4s","Q3s","Q2s","J7s","J6s","J5s","T6s","T5s","95s","85s","84s","74s","63s","52s","42s","32s","K4o","K3o","K2o","Q4o","Q3o","J5o","T5o","95o","84o","73o","63o","54o","52o","42o","32o"],
    mixed_h=["JJ","TT","99","88","77","66","ATs","A9s","A8s","A7s","A6s","KQs","KJs","KTs","K9s","K8s","K7s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","JTs","J9s","J8s","T9s","T8s","T7s","98s","97s","96s","87s","86s","76s","75s","65s","64s","54s","53s","43s","AQo","AJo","ATo","A9o","A8o","A7o","A6o","KQo","KJo","KTo","K9o","K8o","QJo","QTo","Q9o","JTo","J9o","T9o","T8o","98o","97o","87o","86o","76o","75o","65o"])

# ============================================================
# mtt_10bb — AI-classified from crop images (push/fold)
# ============================================================
print("\n[mtt_10bb]")

write_range("mtt_10bb", "UTG",
    raise_h=["A6s"],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","QJs","QTs","AKo","AQo","KQo"],
    mixed_h=["A5s","A4s","55","44","33","22","A7s","98s","87s","76s","65s","A5o","A4o"])

write_range("mtt_10bb", "UTG+1",
    raise_h=["A6s"],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","QJs","QTs","AKo","AQo","KQo"],
    mixed_h=["A5s","A4s","A3s","55","44","33","22","A7s","98s","87s","76s","65s","A5o","A4o"])

write_range("mtt_10bb", "MP",
    raise_h=["A6s","A5s"],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","QJs","QTs","AKo","AQo","KQo"],
    mixed_h=["A4s","A3s","A2s","44","33","22","A7s","98s","87s","76s","65s","A5o","A4o","KJo"])

write_range("mtt_10bb", "HJ",
    raise_h=["A6s","A5s","A4s"],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","QJs","QTs","Q9s","AKo","AQo","AJo","KQo"],
    mixed_h=["A3s","A2s","44","33","22","A7s","98s","87s","76s","65s","J9s","T9s","A5o","A4o","KJo"])

write_range("mtt_10bb", "CO",
    raise_h=[],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","98s","87s","76s","65s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo"],
    mixed_h=["A9o","A8o","A7o","A6o","A5o","A4o","K7s","Q8s","J8s","T8s","97s","86s","75s","54s","K9o"])

write_range("mtt_10bb", "BTN",
    raise_h=["K6s","K5s","K4s","Q5s","J7s","T7s","96s","85s","74s","64s","53s","43s"],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","98s","97s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo","ATo","A9o","KQo","KJo","KTo","K9o","QJo","QTo"],
    mixed_h=["K3s","K2s","Q7s","Q6s","Q4s","J6s","T6s","95s","84s","73s","63s","52s","42s","32s","A8o","A7o","A6o","A5o","A4o","A3o","A2o","K8o","K7o","Q9o","J9o","T9o","98o","87o"])

write_range("mtt_10bb", "SB",
    raise_h=[],
    allin_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","T9s","T8s","98s","97s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","KQo","KJo","KTo","K9o","QJo","QTo"],
    call_h=["K4s","K3s","K2s","Q6s","Q5s","Q4s","Q3s","J7s","J6s","J5s","T7s","T6s","T5s","96s","95s","85s","84s","74s","73s","64s","63s","53s","43s","A6o","A5o","A4o","A3o","A2o","K8o","K7o","K6o","K5o","Q9o","Q8o","J9o","J8o","T9o","T8o","98o","97o","87o","86o","76o","75o","65o","54o"],
    mixed_h=["Q2s","J4s","J3s","T4s","T3s","94s","93s","83s","72s","62s","52s","42s","32s","K4o","K3o","K2o","Q7o","Q6o","Q5o","J7o","T7o","96o","85o","74o","64o","53o","43o"])


# ============================================================
# mtt_100bb — AI-classified from crop images
# ============================================================
print("\n[mtt_100bb]")

write_range("mtt_100bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","Q9s","JTs","J9s","T9s","98s","87s","76s","65s","AKo"],
    mixed_h=["55","44","33","22","Q8s","J8s","AQo","AJo"])

write_range("mtt_100bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A5s","KQs","KJs","KTs","K9s","QJs","QTs","Q9s","Q8s","JTs","J9s","T9s","98s","87s","76s","65s","AKo"],
    mixed_h=["55","44","33","22","J8s","AQo","AJo","ATo"])

write_range("mtt_100bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","98s","97s","87s","86s","76s","75s","65s","54s","AKo","AQo"],
    mixed_h=["55","44","33","22","A3s","K7s","Q7s","J7s","T7s","AJo","KQo"])

write_range("mtt_100bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","A3s","KQs","KJs","KTs","K9s","K8s","K7s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","J7s","T9s","T8s","T7s","98s","97s","96s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo"],
    mixed_h=["44","33","22","A2s","K6s","Q6s","J6s","T6s","ATo","KQo"])

write_range("mtt_100bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","JTs","J9s","J8s","J7s","J6s","T9s","T8s","T7s","T6s","98s","97s","96s","87s","86s","85s","76s","75s","65s","64s","54s","53s","AKo","AQo","AJo","ATo","KQo"],
    mixed_h=["33","22","K5s","Q5s","J5s","T5s","95s","43s","A9o","KJo"])

write_range("mtt_100bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s","JTs","J9s","J8s","J7s","J6s","J5s","J4s","J3s","T9s","T8s","T7s","T6s","T5s","T4s","T3s","98s","97s","96s","95s","94s","93s","87s","86s","85s","84s","83s","82s","76s","75s","74s","73s","65s","64s","63s","54s","53s","52s","43s","42s","32s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","KQo","KJo","KTo","K9o","K8o","K7o","QJo","QTo","Q9o","Q8o","JTo","J9o","J8o","T9o","T8o","98o","87o","86o","76o"],
    mixed_h=["J2s","T2s","92s","62s","A4o","A3o","A2o","K6o","K5o","Q7o","Q6o","J7o","T7o"])

# mtt_100bb SB: raise + mixed + fold → call = rest
_mtt100_sb_raise = ["AA","KK","QQ","TT","88","AKs","AQs","AJs","ATs","KQs","KJs","KTs"]
_mtt100_sb_mixed = ["JJ","99","A9s","A8s","A7s","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","98s","87o","84o","73o","63s","83o","53o"]
_mtt100_sb_fold = ["T2s","92s","82s","72s","62s","42s","32s","J2s","Q2s","82o","72o","62o","52o","42o","32o"]
_mtt100_sb_call = call_from_fold(_mtt100_sb_raise, _mtt100_sb_mixed, _mtt100_sb_fold)
write_range("mtt_100bb", "SB",
    raise_h=_mtt100_sb_raise,
    call_h=_mtt100_sb_call,
    mixed_h=_mtt100_sb_mixed)

# ============================================================
# mtt_50bb — AI-classified from crop images
# ============================================================
print("\n[mtt_50bb]")

write_range("mtt_50bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A7s","A5s","K7s","K6s","Q8s","J8s","97s","86s","75s","55","44","33","22","AJo"])

write_range("mtt_50bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A7s","A5s","A4s","K7s","K6s","Q8s","J8s","97s","86s","75s","55","44","33","22","AJo"])

write_range("mtt_50bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","K5s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A6s","A3s","K7s","K6s","Q8s","J8s","97s","86s","75s","54s","44","33","22","AJo"])

write_range("mtt_50bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","K7s","K5s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","T7s","98s","97s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo","KQo","KJo"],
    mixed_h=["A6s","A3s","K6s","Q7s","J7s","T6s","96s","85s","44","33","22","ATo","KTo","QJo"])

write_range("mtt_50bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","J7s","T9s","T8s","T7s","T6s","98s","97s","96s","87s","86s","85s","76s","75s","65s","64s","54s","53s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo"],
    mixed_h=["A2s","K4s","Q6s","J6s","T5s","95s","84s","74s","63s","43s","33","22","A9o","K9o","Q9o","JTo"])

write_range("mtt_50bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","JTs","J9s","J8s","J7s","J6s","J5s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","95s","87s","86s","85s","76s","75s","65s","64s","54s","53s","43s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","KQo","KJo","KTo","K9o","K8o","QJo","QTo","Q9o","JTo","J9o","T9o","98o"],
    mixed_h=["Q4s","J4s","T4s","94s","84s","74s","63s","52s","42s","32s","A4o","A3o","A2o","K7o","K6o","K5o","K4o","Q8o","Q7o","J8o","J7o","T8o","97o","87o","76o"])

# mtt_50bb SB: skipped (no grid image, stats bar only)

# ============================================================
# mtt_40bb — AI-classified from crop images
# ============================================================
print("\n[mtt_40bb]")

write_range("mtt_40bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A7s","A5s","K7s","K6s","Q8s","J8s","97s","86s","75s","55","44","33","22","AJo"])

write_range("mtt_40bb", "UTG+1",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A7s","A5s","A4s","K7s","K6s","Q8s","J8s","97s","86s","75s","55","44","33","22","AJo"])

write_range("mtt_40bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","K5s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","98s","87s","76s","65s","AKo","AQo","KQo"],
    mixed_h=["A6s","A3s","K7s","K6s","Q8s","J8s","97s","86s","75s","54s","44","33","22","AJo"])

write_range("mtt_40bb", "HJ",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","K7s","K5s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","T7s","98s","97s","87s","86s","76s","75s","65s","54s","AKo","AQo","AJo","KQo","KJo"],
    mixed_h=["A6s","A3s","K6s","Q7s","J7s","T6s","96s","85s","44","33","22","ATo","KTo","QJo"])

write_range("mtt_40bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","JTs","J9s","J8s","J7s","J6s","T9s","T8s","T7s","T6s","98s","97s","96s","87s","86s","85s","76s","75s","65s","64s","54s","53s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo"],
    mixed_h=["A2s","K4s","Q5s","J5s","T5s","95s","84s","74s","63s","43s","33","22","A9o","K9o","Q9o","JTo","32s"])

write_range("mtt_40bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","JTs","J9s","J8s","J7s","J6s","J5s","J4s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","95s","94s","87s","86s","85s","84s","76s","75s","74s","65s","64s","54s","53s","43s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","KQo","KJo","KTo","K9o","K8o","QJo","QTo","Q9o","JTo","J9o","T9o","98o"],
    mixed_h=["Q3s","J3s","T4s","T3s","93s","83s","73s","63s","52s","42s","32s","A3o","A2o","K7o","K6o","K5o","K4o","Q8o","Q7o","J8o","T8o","97o","87o","76o"])

write_range("mtt_40bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","KQs","KJs","KTs","QJs","QTs","JTs","AKo","AQo"],
    call_h=["99","88","77","66","55","44","33","22","A8s","A7s","A6s","A4s","A3s","A2s","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s","J9s","J8s","J7s","J6s","J5s","J4s","J3s","J2s","T9s","T8s","T7s","T6s","T5s","T4s","T3s","T2s","98s","97s","96s","95s","94s","93s","92s","87s","86s","85s","84s","83s","82s","76s","75s","74s","73s","72s","65s","64s","63s","62s","54s","53s","52s","43s","42s","32s","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","KQo","KJo","KTo","K9o","K8o","K7o","K6o","K5o","K4o","K3o","K2o","QJo","QTo","Q9o","Q8o","Q7o","Q6o","Q5o","Q4o","Q3o","Q2o","JTo","J9o","J8o","J7o","J6o","J5o","J4o","J3o","J2o","T9o","T8o","T7o","T6o","T5o","T4o","T3o","T2o","98o","97o","96o","95o","94o","93o","92o","87o","86o","85o","84o","83o","82o","76o","75o","74o","73o","72o","65o","64o","63o","62o","54o","53o","52o","43o","42o","32o"],
    mixed_h=["A9s","A5s","K9s","T9s","98s","87s","76s","65s","54s","AJo","KQo"])


# ============================================================
# 6max_100bb_highRake — AI-classified from crop images
# ============================================================
print("\n[6max_100bb_highRake]")

write_range("6max_100bb_highRake", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K5s","QJs","QTs","Q9s","JTs","AKo","AQo","AJo","ATo","KQo","KJo","QJo"],
    mixed_h=["K7s","K6s","KTo","99","88","77","66","T9s","98s","87s","76s"])

write_range("6max_100bb_highRake", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","JTs","AKo","AQo","AJo","ATo","KQo","KJo","QJo","QTo"],
    mixed_h=["K4s","J9s","T9s","98s","87s","76s","65s","54s","A9o","99","88","77","66"])

write_range("6max_100bb_highRake", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","JTs","J9s","T9s","AKo","AQo","AJo","ATo","A9o","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["K3s","K2s","Q5s","Q4s","J8s","T8s","98s","87s","76s","65s","54s","K9o","A8o","A6o","A5o","88","77","66","55","87o","76o","65o","54o"])

write_range("6max_100bb_highRake", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","JTs","J9s","J8s","J7s","J6s","T9s","T8s","T7s","98s","97s","87s","76s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","KQo","KJo","KTo","K9o","QJo","QTo","Q9o","JTo","J9o","T9o"],
    mixed_h=["Q3s","J5s","T6s","96s","86s","65s","54s","43s","K8o","J8o","T8o","87o","76o","65o","54o","43o","32o","66","55","44","33","A3o","A2o"])

write_range("6max_100bb_highRake", "SB",
    raise_h=["AA","KK","QQ","TT","AKs","AQs","ATs","KQs","KTs","K4s","K3s","QJs","QTs","Q7s","Q6s","Q5s","JTs","J7s","J6s","T7s","97s","96s","86s","85s","75s","64s","AKo","AQo","A9o","A8o","A7o","A6o","A2o","K2o","Q2o","J2o"],
    mixed_h=["AJs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KJs","K9s","K8s","K7s","K6s","K5s","K2s","KQo","Q9s","Q8s","Q4s","Q3s","JJ","J9s","J8s","J5s","AJo","KJo","QJo","ATo","KTo","QTo","JTo","T9s","T8s","T6s","K9o","Q9o","J9o","T9o","99","98s","K8o","88","87s","77","76s","66","65s","A5o","55","A4o","54s","44","43s","A3o","33"])

# ============================================================
# 6max_40bb — AI-classified from crop images
# ============================================================
print("\n[6max_40bb]")

write_range("6max_40bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","J9s","T9s","T8s","AKo","AQo","AJo","ATo","KQo","KJo"],
    mixed_h=["66","55","A3s","QJo","JTo","65o","54o"])

write_range("6max_40bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","QJs","QTs","Q9s","Q8s","JTs","J9s","J8s","T9s","T8s","98s","AKo","AQo","AJo","ATo","KQo","KJo","QJo","JTo"],
    mixed_h=["55","44","A9o","K6s","87s","76o","65o","54o","43o"])

write_range("6max_40bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","T9s","T8s","98s","87s","76s","AKo","AQo","AJo","ATo","A9o","A8o","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["K9o","K4s","J7s","T7s","97s","86s","65s","76o","65o","54o","44","43o","33","32o"])

write_range("6max_40bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","JTs","J9s","J8s","J7s","J6s","J5s","T9s","T8s","T7s","T6s","98s","97s","96s","87s","86s","85s","76s","75s","65s","54s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","KQo","KJo","KTo","K9o","QJo","QTo","Q9o","JTo","J9o","T9o"],
    mixed_h=["A4o","J8o","Q8o","T8o","43o","33","32o","22","66","55","44"])

write_range("6max_40bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","QJs","QTs","Q9s","Q8s","Q7s","Q5s","Q2s","JTs","J9s","J8s","J7s","J4s","J3s","T9s","T8s","T7s","T6s","T5s","98s","97s","95s","87s","86s","76s","74s","65s","64s","54s","53s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A2o","KQo","KJo","KTo","K9o","K8o","K7o","K2o","QJo","QTo","Q9o","Q8o","Q7o","Q2o","JTo","J9o","J8o","J2o","T9o","T8o","T7o"],
    mixed_h=["A4o","A3o","A2o","K6o","K5o","K4s","K3s","K2s","Q7o","Q6s","Q4s","Q3s","J8o","J6s","J5s","J2s","T7o","T4s","T3s","97o","96s","87o","85s","77","75s","66","33","22"])


# ============================================================
# 6max_200bb — AI-classified from crop images
# ============================================================
print("\n[6max_200bb]")

write_range("6max_200bb", "UTG",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","AKs","AQs","AJs","ATs","A9s","A8s","A5s","KQs","KJs","KTs","K9s","K8s","QJs","QTs","Q9s","JTs","76s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["A7s","J9s","T9s","T8s","98s","87s","65s","33","22"])

write_range("6max_200bb", "MP",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K6s","K5s","QJs","QTs","Q9s","JTs","J9s","T9s","87s","76s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo"],
    mixed_h=["K7s","T8s","98s","75s","65s","54s"])

write_range("6max_200bb", "CO",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","JTs","J9s","J8s","J7s","T9s","T8s","T7s","98s","97s","87s","86s","76s","75s","65s","64s","54s","43s","AKo","AQo","AJo","ATo","KQo","KJo","KTo","QJo","QTo","JTo","T9o"],
    mixed_h=["A9o","K2s","Q6s"])

write_range("6max_200bb", "BTN",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","JTs","J9s","J8s","J7s","J6s","J5s","J4s","T9s","T8s","T7s","T6s","T5s","98s","97s","96s","95s","87s","86s","85s","76s","75s","74s","65s","64s","54s","53s","43s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","KQo","KJo","KTo","QJo","QTo","JTo","T9o","T8o","87o"],
    mixed_h=["K2s","Q2s","J3s","T4s","94s","84s","73s","63s","52s","42s","32s"])

write_range("6max_200bb", "SB",
    raise_h=["AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22","AKs","AQs","AJs","ATs","A9s","A6s","A5s","A4s","A3s","A2s","KQs","KJs","KTs","K9s","K5s","K4s","K3s","K2s","QJs","Q4s","Q3s","Q2s","JTs","J4s","J3s","J2s","T9s","T4s","T3s","T2s","98s","93s","92s","87s","83s","82s","76s","73s","72s","65s","63s","62s","54s","53s","52s","43s","42s","32s","AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","KQo","KJo","KTo","QJo","QTo","JTo","T9o","T8o","87o"],
    call_h=["A8s","A7s","K8s","K7s","K6s","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","J9s","J8s","J7s","J6s","J5s","T8s","T7s","T6s","T5s","97s","96s","95s"])


if __name__ == "__main__":
    print("Done.")
