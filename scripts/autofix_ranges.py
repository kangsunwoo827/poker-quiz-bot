#!/usr/bin/env python3
"""
Auto-fix monotonicity violations in extracted ranges.
- If a weak hand is raise but many stronger hands are fold → remove the weak hand (false positive)
- If a strong hand is fold but weaker hands are raise → add the strong hand (missing)
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"
CORRECTIONS_FILE = ROOT / "data" / "corrections.json"

RANKS = "AKQJT98765432"
PAIRS = [f"{r}{r}" for r in RANKS]


def load_range(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raise_h = set(data.get("raise", []))
    allin_h = set(data.get("allin", []))
    call_h  = set(data.get("call", []))
    raw_mixed = data.get("mixed", {})
    mixed_h = set(raw_mixed.keys()) if isinstance(raw_mixed, dict) else set(raw_mixed)
    return raise_h, allin_h, call_h, mixed_h


def fix_pair_monotonicity(action_set, mixed_set):
    """Fix pair sequence: if weaker pair is in action but stronger is not."""
    adds = set()
    removes = set()
    all_action = action_set | mixed_set

    for i, pair in enumerate(PAIRS):
        if pair not in all_action:
            continue
        # Count how many stronger pairs are missing
        missing_stronger = [PAIRS[j] for j in range(i) if PAIRS[j] not in all_action]
        if missing_stronger:
            # If this pair is weaker than 3+ missing pairs, it's a false positive
            if len(missing_stronger) >= 3:
                removes.add(pair)
            else:
                # Add the missing stronger pairs
                adds.update(missing_stronger)

    return adds, removes


def fix_suited_monotonicity(action_set, mixed_set):
    """Fix suited sequences per high card."""
    adds = set()
    removes = set()
    all_action = action_set | mixed_set

    for hi_idx in range(13):
        hi = RANKS[hi_idx]
        suited = [f"{hi}{RANKS[lo]}s" for lo in range(hi_idx + 1, 13)]
        in_range = [h for h in suited if h in all_action]
        if not in_range:
            continue

        for hand in in_range:
            idx = suited.index(hand)
            missing_stronger = [suited[j] for j in range(idx) if suited[j] not in all_action]
            if missing_stronger:
                if len(missing_stronger) >= 3:
                    removes.add(hand)
                else:
                    adds.update(missing_stronger)

    return adds, removes


def fix_offsuit_monotonicity(action_set, mixed_set):
    """Fix offsuit sequences per high card."""
    adds = set()
    removes = set()
    all_action = action_set | mixed_set

    for hi_idx in range(13):
        hi = RANKS[hi_idx]
        offsuit = [f"{hi}{RANKS[lo]}o" for lo in range(hi_idx + 1, 13)]
        in_range = [h for h in offsuit if h in all_action]
        if not in_range:
            continue

        for hand in in_range:
            idx = offsuit.index(hand)
            missing_stronger = [offsuit[j] for j in range(idx) if offsuit[j] not in all_action]
            if missing_stronger:
                if len(missing_stronger) >= 2:
                    removes.add(hand)
                else:
                    adds.update(missing_stronger)

    return adds, removes


def fix_aa(action_set, mixed_set):
    """AA should be raise/mixed for any range > 12%."""
    total = len(action_set | mixed_set)
    pct = total / 169 * 100
    if "AA" not in action_set and "AA" not in mixed_set and pct > 12:
        return {"AA"}, set()
    return set(), set()


def main():
    corrections = {"_comment": "Auto-generated corrections from monotonicity validation."}
    total_fixes = 0

    for fmt_dir in sorted(RANGES_DIR.iterdir()):
        rfi_dir = fmt_dir / "rfi"
        if not rfi_dir.exists():
            continue
        fmt = fmt_dir.name

        for path in sorted(rfi_dir.glob("*.json")):
            pos = path.stem
            raise_h, allin_h, call_h, mixed_h = load_range(path)
            action = raise_h | allin_h | call_h

            all_adds = set()
            all_removes = set()

            # Fix pairs
            a, r = fix_pair_monotonicity(action, mixed_h)
            all_adds |= a
            all_removes |= r

            # Fix suited
            a, r = fix_suited_monotonicity(action, mixed_h)
            all_adds |= a
            all_removes |= r

            # Fix offsuit
            a, r = fix_offsuit_monotonicity(action, mixed_h)
            all_adds |= a
            all_removes |= r

            # Fix AA
            a, r = fix_aa(action, mixed_h)
            all_adds |= a

            # Don't add hands that are already in range
            all_adds -= action
            all_adds -= mixed_h
            # Don't remove hands we're adding
            all_removes -= all_adds

            if all_adds or all_removes:
                if fmt not in corrections:
                    corrections[fmt] = {}
                corr = {}
                # Separate adds into raise_add and mixed (use mixed as default for adds)
                raise_adds = sorted(all_adds & set(PAIRS))  # pairs go to raise
                mixed_adds = sorted(all_adds - set(PAIRS))   # non-pairs go to mixed
                raise_removes = sorted(all_removes & raise_h)
                allin_removes = sorted(all_removes & allin_h)
                call_removes = sorted(all_removes & call_h)

                if raise_adds:
                    corr["raise_add"] = raise_adds
                if mixed_adds:
                    corr["mixed"] = mixed_adds
                if raise_removes:
                    corr["raise_remove"] = raise_removes
                if allin_removes:
                    corr["allin_remove"] = allin_removes
                if call_removes:
                    corr["call_remove"] = call_removes

                corrections[fmt][pos] = corr
                n = len(all_adds) + len(all_removes)
                total_fixes += n
                print(f"  {fmt}/{pos}: +{len(all_adds)} -{len(all_removes)}")

    with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(corrections, f, indent=2, ensure_ascii=False)

    print(f"\nTotal fixes: {total_fixes}")
    print(f"Saved to {CORRECTIONS_FILE}")


if __name__ == "__main__":
    main()
