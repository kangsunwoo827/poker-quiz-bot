#!/bin/bash
# Run solver for all 32 postflop questions
# Low priority: nice 19 (lowest), 1 thread

SOLVER="/tmp/TexasSolver-v0.2.0-Linux/console_solver"
JOB_DIR="data/solver_jobs"
LOG_FILE="data/solver_jobs/run.log"

echo "Starting solver runs at $(date)" > $LOG_FILE
echo "Using nice 19 for minimal CPU impact" >> $LOG_FILE

for input_file in $JOB_DIR/q*_input.txt; do
    qid=$(basename $input_file | sed 's/q\([0-9]*\)_input.txt/\1/')
    result_file="$JOB_DIR/q${qid}_result.json"
    
    echo "=== Q$qid starting at $(date) ===" >> $LOG_FILE
    
    # Run solver with lowest priority
    nice -n 19 $SOLVER < $input_file >> $LOG_FILE 2>&1
    
    if [ -f "$result_file" ]; then
        echo "Q$qid: SUCCESS - $(date)" >> $LOG_FILE
    else
        echo "Q$qid: FAILED - no result file" >> $LOG_FILE
    fi
    
    echo "" >> $LOG_FILE
done

echo "All solvers completed at $(date)" >> $LOG_FILE
touch data/solver_jobs/DONE
