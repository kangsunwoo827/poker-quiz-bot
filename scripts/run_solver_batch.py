#!/usr/bin/env python3
"""
Batch run TexasSolver for all postflop questions.
Saves results to data/solver_results/
"""

import json
import subprocess
import os
import re
from pathlib import Path

SOLVER_PATH = "/tmp/TexasSolver-v0.2.0-Linux/console_solver"
RESULTS_DIR = Path("/home/ubuntu/AIde/projects/poker-quiz-bot/data/solver_results")
QUESTIONS_FILE = Path("/home/ubuntu/AIde/projects/poker-quiz-bot/data/questions.json")

# Standard ranges (simplified for solver)
RANGES = {
    "CO_open": "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,QJs,QTs,Q9s,Q8s,JTs,J9s,J8s,T9s,T8s,98s,97s,87s,86s,76s,75s,65s,64s,54s,53s,43s,AKo,AQo,AJo,ATo,A9o,KQo,KJo,KTo,QJo,QTo,JTo",
    "BB_defend_vs_CO": "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQs,KJs,KTs,K9s,K8s,K7s,K6s,QJs,QTs,Q9s,Q8s,Q7s,JTs,J9s,J8s,J7s,T9s,T8s,T7s,98s,97s,87s,86s,76s,75s,65s,64s,54s,53s,43s,AKo,AQo,AJo,ATo,A9o,A8o,KQo,KJo,KTo,K9o,QJo,QTo,JTo,J9o,T9o",
    "BTN_open": "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,K4s,K3s,K2s,QJs,QTs,Q9s,Q8s,Q7s,Q6s,Q5s,Q4s,JTs,J9s,J8s,J7s,J6s,T9s,T8s,T7s,98s,97s,96s,87s,86s,76s,75s,65s,64s,54s,53s,43s,32s,AKo,AQo,AJo,ATo,A9o,A8o,A7o,A6o,A5o,A4o,A3o,A2o,KQo,KJo,KTo,K9o,K8o,QJo,QTo,Q9o,JTo,J9o,T9o,98o",
    "BB_defend_vs_BTN": "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,K4s,QJs,QTs,Q9s,Q8s,Q7s,Q6s,JTs,J9s,J8s,J7s,J6s,T9s,T8s,T7s,T6s,98s,97s,96s,87s,86s,85s,76s,75s,74s,65s,64s,63s,54s,53s,52s,43s,42s,32s,AKo,AQo,AJo,ATo,A9o,A8o,A7o,A6o,A5o,A4o,A3o,KQo,KJo,KTo,K9o,K8o,K7o,QJo,QTo,Q9o,Q8o,JTo,J9o,J8o,T9o,T8o,98o,97o,87o,76o,65o",
}

def parse_board(situation: str) -> str:
    """Extract board from situation text."""
    # Find Flop/Turn/River pattern
    match = re.search(r'(?:Flop|Turn|River):\s*([^\(]+)', situation)
    if match:
        board_str = match.group(1).strip()
        # Convert ♥♦♣♠ to hdcs
        board_str = board_str.replace('♥', 'h').replace('♦', 'd').replace('♣', 'c').replace('♠', 's')
        # Remove spaces and split into cards
        board_str = board_str.replace(' ', '')
        # Insert commas between cards (every 2 chars)
        cards = ','.join([board_str[i:i+2] for i in range(0, len(board_str), 2)])
        return cards
    return ""

def get_pot_and_stacks(situation: str) -> tuple:
    """Parse pot size from situation. Returns (pot, effective_stack)."""
    # Look for (Pot: Xbb) pattern
    match = re.search(r'\(Pot:\s*([\d.]+)bb\)', situation)
    pot = float(match.group(1)) if match else 5.5
    
    # 100bb effective standard
    return pot, 100.0

def determine_ranges(situation: str) -> tuple:
    """Determine IP and OOP ranges based on situation."""
    # Default: CO vs BB
    ip_range = RANGES["CO_open"]
    oop_range = RANGES["BB_defend_vs_CO"]
    
    if "BTN raises" in situation or "BTN open" in situation:
        ip_range = RANGES["BTN_open"]
        oop_range = RANGES["BB_defend_vs_BTN"]
    
    return ip_range, oop_range

def create_solver_input(question: dict, output_path: Path) -> Path:
    """Create solver input file for a question."""
    board = parse_board(question['situation'])
    pot, eff_stack = get_pot_and_stacks(question['situation'])
    ip_range, oop_range = determine_ranges(question['situation'])
    
    # Figure out bet sizing from options
    bet_sizes = []
    for opt in question['options']:
        if 'bet' in opt.lower() or '%' in opt:
            # Extract percentage
            match = re.search(r'(\d+)%', opt)
            if match:
                pct = int(match.group(1))
                bet_sizes.append(pct)
    
    if not bet_sizes:
        bet_sizes = [33, 75]  # Default
    
    # Build solver input
    input_file = output_path / f"q{question['id']}_input.txt"
    
    config = f"""set_pot {pot}
set_effective_stack {eff_stack}
set_board {board}
set_range_ip {ip_range}
set_range_oop {oop_range}
set_bet_sizes oop,flop,bet,{','.join(str(s) for s in bet_sizes)}
set_bet_sizes ip,flop,bet,33,75
set_bet_sizes oop,flop,raise,100
set_bet_sizes ip,flop,raise,100
set_allin_threshold 0.67
set_accuracy 1
set_max_iteration 100
set_thread_num 1
set_print_interval 10
set_use_isomorphism 1
build_tree
start_solve
dump_result {output_path}/q{question['id']}_result.json
"""
    
    with open(input_file, 'w') as f:
        f.write(config)
    
    return input_file

def run_solver(input_file: Path) -> bool:
    """Run solver with nice priority."""
    try:
        result = subprocess.run(
            ['nice', '-n', '19', SOLVER_PATH, '-i', str(input_file)],
            capture_output=True,
            text=True,
            timeout=300  # 5 min max
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"Timeout for {input_file}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)
    
    postflop = [q for q in questions if q['type'] == 'postflop' and q['id'] != 1]  # Skip Q1 (done)
    
    print(f"Running solver for {len(postflop)} postflop questions...")
    
    for q in postflop:
        print(f"\n{'='*50}")
        print(f"Q{q['id']}: {q['hand']} on {parse_board(q['situation'])}")
        print(f"{'='*50}")
        
        result_file = RESULTS_DIR / f"q{q['id']}_result.json"
        if result_file.exists():
            print(f"  Already solved, skipping...")
            continue
        
        input_file = create_solver_input(q, RESULTS_DIR)
        print(f"  Input: {input_file}")
        
        success = run_solver(input_file)
        if success:
            print(f"  ✓ Solved!")
        else:
            print(f"  ✗ Failed")
    
    print("\n\nDone!")

if __name__ == "__main__":
    main()
