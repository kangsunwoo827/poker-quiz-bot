#!/usr/bin/env python3
"""
Generate range chart images for all scenarios.
Used for visual QA and pre-generation.
"""
import json
import sys
from pathlib import Path

# Add bot/ to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))

from chart import generate_range_chart

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EV_TABLES_DIR = DATA_DIR / "ev_tables"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"
OUTPUT_DIR = PROJECT_ROOT / "charts"


def main():
    with open(SCENARIOS_FILE, encoding="utf-8") as f:
        scenarios = json.load(f)
    scenarios_map = {s["id"]: s for s in scenarios}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated = 0

    for path in sorted(EV_TABLES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            ev_table = json.load(f)

        scenario_id = ev_table.get("scenario_id", path.stem)
        if scenario_id not in scenarios_map:
            print(f"  {scenario_id}: no scenario definition, skipping")
            continue

        scenario = scenarios_map[scenario_id]
        hands = ev_table.get("hands", {})

        if not hands:
            print(f"  {scenario_id}: no hands data, skipping")
            continue

        chart_bytes = generate_range_chart(
            scenario_hands=hands,
            actions=scenario["actions"],
            highlight_hand=None,
            title=scenario["name"],
        )

        out_path = OUTPUT_DIR / f"{scenario_id}.png"
        with open(out_path, "wb") as f:
            f.write(chart_bytes)

        print(f"  {scenario_id}: {out_path} ({len(chart_bytes)} bytes)")
        generated += 1

    print(f"\nGenerated {generated} charts in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
