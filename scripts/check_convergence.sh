#!/usr/bin/env bash
set -euo pipefail

TRAINER_DIR=".auto-trainer"
TREE="$TRAINER_DIR/experiment-tree.json"
CONFIG="$TRAINER_DIR/convergence-config.json"
SCRIPTS_DIR="$(dirname "$0")"

if [ ! -f "$TREE" ]; then
    echo '{"decision": "block", "reason": "No experiment tree found — initialization required"}'
    exit 0
fi

if [ ! -f "$CONFIG" ]; then
    echo '{"decision": "block", "reason": "No convergence config found — initialization required"}'
    exit 0
fi

MERKLE_RESULT=$(python3 "$SCRIPTS_DIR/verify_merkle_chain.py" "$TREE" 2>&1) || {
    echo "{\"decision\": \"block\", \"reason\": \"BLOCKED_TAMPER: Merkle chain verification failed\"}"
    exit 0
}

python3 "$SCRIPTS_DIR/compute_pareto.py" "$TREE" > /dev/null 2>&1

python3 "$SCRIPTS_DIR/check_class_exhaustion.py" "$TREE" > /dev/null 2>&1

COVERAGE_RESULT=$(python3 "$SCRIPTS_DIR/check_cross_class_coverage.py" "$TREE" "$CONFIG" 2>&1)
GLOBAL_STATUS=$(echo "$COVERAGE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['global_status'])")

if [ "$GLOBAL_STATUS" = "CONVERGED" ]; then
    if [ ! -d "$TRAINER_DIR/worktrees/exp_ensemble" ]; then
        PARETO_COUNT=$(python3 -c "import json; t=json.load(open('$TREE')); print(len(t.get('pareto_front',[])))")
        if [ "$PARETO_COUNT" -le 1 ]; then
            if [ -f "$TRAINER_DIR/final-report.md" ]; then
                exit 0
            else
                echo '{"decision": "block", "reason": "CONVERGED + ensemble skipped (single model) — produce final report"}'
                exit 0
            fi
        else
            echo '{"decision": "block", "reason": "CONVERGED — run ensemble on Pareto-front models before final report"}'
            exit 0
        fi
    fi
    if [ -f "$TRAINER_DIR/final-report.md" ]; then
        exit 0
    else
        echo '{"decision": "block", "reason": "CONVERGED + ensemble done — produce final report and Kaggle submission"}'
        exit 0
    fi
fi

REASON=$(echo "$COVERAGE_RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print('; '.join(r.get('reasons',[])))")
echo "{\"decision\": \"block\", \"reason\": \"EXPLORING: $REASON\"}"
exit 0
