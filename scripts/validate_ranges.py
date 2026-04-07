#!/usr/bin/env python3
"""
Structural validation for extracted poker ranges.
Checks hand strength monotonicity and position consistency.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"

RANKS = "AKQJT98765432"
RANK_VAL = {r: i for i, r in enumerate(RANKS)}

# All 169 hands
ALL_HANDS = []
for i in range(13):
    for j in range(13):
        r1, r2 = RANKS[i], RANKS[j]
        if i < j:
            ALL_HANDS.append(f"{r1}{r2}s")
        elif i > j:
            ALL_HANDS.append(f"{r2}{r1}o")
        else:
            ALL_HANDS.append(f"{r1}{r2}")

PAIRS = [f"{r}{r}" for r in RANKS]  # AA, KK, ..., 22

# Hand strength: lower = stronger
def hand_strength(hand):
    if len(hand) == 2:
        return RANK_VAL[hand[0]]
    hi, lo = RANK_VAL[hand[0]], RANK_VAL[hand[1]]
    suited = hand.endswith("s")
    base = 13 + hi * 12 + (lo - 1)
    return base if suited else base + 91


CORRECTIONS = {}
_corr_path = ROOT / "data" / "corrections.json"
if _corr_path.exists():
    with open(_corr_path, encoding="utf-8") as _f:
        _raw = json.load(_f)
    CORRECTIONS = {k: v for k, v in _raw.items() if not k.startswith("_")}


def load_range(path):
    """Load a range JSON file with corrections applied."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raise_h = set(data.get("raise", []))
    allin_h = set(data.get("allin", []))
    call_h  = set(data.get("call", []))
    raw_mixed = data.get("mixed", {})
    mixed_h = set(raw_mixed.keys()) if isinstance(raw_mixed, dict) else set(raw_mixed)

    # Apply corrections
    fmt = path.parent.parent.name
    pos = path.stem
    corr = CORRECTIONS.get(fmt, {}).get(pos, {})
    raise_h -= set(corr.get("raise_remove", []))
    raise_h |= set(corr.get("raise_add", []))
    allin_h -= set(corr.get("allin_remove", []))
    allin_h |= set(corr.get("allin_add", []))
    call_h -= set(corr.get("call_remove", []))
    call_h |= set(corr.get("call_add", []))
    mixed_h |= set(corr.get("mixed", []))
    mixed_h -= set(corr.get("mixed_remove", []))

    return raise_h, allin_h, call_h, mixed_h


def check_pair_monotonicity(action_set, mixed_set, label):
    """If pair X is in action_set, all stronger pairs must also be in action_set or mixed."""
    errors = []
    all_action = action_set | mixed_set
    for i, pair in enumerate(PAIRS):
        if pair in action_set:
            for j in range(i):
                stronger = PAIRS[j]
                if stronger not in all_action:
                    errors.append(f"  {label}: {pair} is raise but {stronger} is fold")
    return errors


def check_suited_monotonicity(action_set, mixed_set, label):
    """For suited hands with same high card: if weaker is raise, stronger must be too."""
    errors = []
    all_action = action_set | mixed_set
    for hi_idx in range(13):
        hi = RANKS[hi_idx]
        suited = [f"{hi}{RANKS[lo]}s" for lo in range(hi_idx + 1, 13)]
        for i, hand in enumerate(suited):
            if hand in action_set:
                for j in range(i):
                    stronger = suited[j]
                    if stronger not in all_action:
                        errors.append(f"  {label}: {hand} is raise but {stronger} is fold")
    return errors


def check_offsuit_monotonicity(action_set, mixed_set, label):
    """For offsuit hands with same high card: if weaker is raise, stronger must be too."""
    errors = []
    all_action = action_set | mixed_set
    for hi_idx in range(13):
        hi = RANKS[hi_idx]
        offsuit = [f"{hi}{RANKS[lo]}o" for lo in range(hi_idx + 1, 13)]
        for i, hand in enumerate(offsuit):
            if hand in action_set:
                for j in range(i):
                    stronger = offsuit[j]
                    if stronger not in all_action:
                        errors.append(f"  {label}: {hand} is raise but {stronger} is fold")
    return errors


def validate_format(fmt_dir, fmt_name):
    """Validate all positions in a format directory."""
    errors = []
    positions = sorted(fmt_dir.glob("*.json"))
    if not positions:
        return errors

    for path in positions:
        pos = path.stem
        label = f"{fmt_name}/{pos}"
        raise_h, allin_h, call_h, mixed_h = load_range(path)
        action = raise_h | allin_h | call_h  # all "play" hands

        # 1. Pair monotonicity
        errors.extend(check_pair_monotonicity(action, mixed_h, label))

        # 2. Suited monotonicity
        errors.extend(check_suited_monotonicity(action, mixed_h, label))

        # 3. Offsuit monotonicity
        errors.extend(check_offsuit_monotonicity(action, mixed_h, label))

        # 4. Basic sanity: AA should be in action or mixed for all but UTG in tight formats
        if "AA" not in action and "AA" not in mixed_h:
            pct = len(action | mixed_h) / 169 * 100
            if pct > 12:  # wide enough that AA should be included
                errors.append(f"  {label}: AA is fold but range is {pct:.1f}%")

    return errors


def main():
    total_errors = 0
    for fmt_dir in sorted(RANGES_DIR.iterdir()):
        rfi_dir = fmt_dir / "rfi"
        if not rfi_dir.exists():
            continue
        fmt_name = fmt_dir.name
        errors = validate_format(rfi_dir, fmt_name)
        if errors:
            print(f"\n[{fmt_name}] {len(errors)} error(s):")
            for e in errors:
                print(e)
            total_errors += len(errors)
        else:
            print(f"[{fmt_name}] OK")

    print(f"\nTotal: {total_errors} errors")
    return total_errors


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
