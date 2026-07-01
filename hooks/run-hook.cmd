#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  session-start)
    echo "hook success: Auto Model Trainer plugin active. Use /auto-train <objective.yaml> to start autonomous ML training. Stop hook drives convergence detection."
    ;;
  *)
    echo "hook success: Auto Model Trainer hook executed."
    ;;
esac
