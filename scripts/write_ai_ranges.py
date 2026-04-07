#!/usr/bin/env python3
"""Write AI-classified range data directly to JSON files."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"

def write_range(fmt, pos, raise_h, allin_h=None, call_h=None, mixed_h=None):
    out_dir = RANGES_DIR / fmt / "rfi"
    out_dir.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    print("Done.")
