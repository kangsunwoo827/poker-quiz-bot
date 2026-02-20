#!/bin/bash
SOLVER="/tmp/TexasSolver-v0.2.0-Linux/console_solver"
for qid in 18 25 42; do
  echo "=== Q$qid starting at $(date) ===" >> data/solver_jobs/retry.log
  nice -n 19 $SOLVER < data/solver_jobs/q${qid}_input.txt >> data/solver_jobs/retry.log 2>&1
  echo "Q$qid done at $(date)" >> data/solver_jobs/retry.log
done
touch data/solver_jobs/RETRY_DONE
