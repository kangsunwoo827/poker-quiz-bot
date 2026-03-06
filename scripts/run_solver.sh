#!/bin/bash
# Run the solver for all scenarios
# Usage: ./scripts/run_solver.sh [n_flops]
# Default: 10 flops per branch

N_FLOPS=${1:-10}
SOLVER="$(dirname "$0")/../solver/target/release/preflop_solver"

if [ ! -f "$SOLVER" ]; then
    echo "Building solver..."
    cd "$(dirname "$0")/../solver" && ~/.cargo/bin/cargo build --release
    cd -
fi

SCENARIOS=(
    rfi_utg rfi_mp rfi_co rfi_btn rfi_sb
    bb_vs_utg bb_vs_mp bb_vs_co bb_vs_btn
    sb_vs_co sb_vs_btn btn_vs_co co_vs_utg
    utg_vs_3bet co_vs_btn_3bet btn_vs_bb_3bet btn_vs_sb_3bet
    bb_squeeze
    sb_vs_limp bb_vs_limp
)

echo "=== Solver run: ${N_FLOPS} flops per branch ==="
echo "Started: $(date)"
echo ""

for sc in "${SCENARIOS[@]}"; do
    echo "--- $sc ---"
    "$SOLVER" "$sc" "$N_FLOPS" 2>&1
    echo ""
done

echo "=== Completed: $(date) ==="
