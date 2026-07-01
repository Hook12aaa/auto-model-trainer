#!/usr/bin/env python3
"""Check minimum architecture diversity for global convergence.

Usage: python check_cross_class_coverage.py <experiment-tree.json> <convergence-config.json>

Convergence config fields:
  - architecture_classes_minimum (int): min distinct classes explored
  - pareto_stability_rounds (int): pareto_front must be unchanged this many rounds

CONVERGED when ALL conditions hold:
  (a) explored classes >= architecture_classes_minimum
  (b) no class in EXPLORING status
  (c) pareto_front unchanged for pareto_stability_rounds consecutive snapshots

Updates global_status and pareto_history in the tree.
"""

import json
import sys


def main():
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <experiment-tree.json> <convergence-config.json>",
            file=sys.stderr,
        )
        sys.exit(1)

    tree_path = sys.argv[1]
    config_path = sys.argv[2]

    with open(tree_path, "r") as f:
        tree = json.load(f)
    with open(config_path, "r") as f:
        config = json.load(f)

    min_classes = config["architecture_classes_minimum"]
    stability_rounds = config["pareto_stability_rounds"]

    class_status = tree.get("class_status", {})
    pareto_front = sorted(tree.get("pareto_front", []))
    pareto_history = tree.get("pareto_history", [])

    pareto_history.append(pareto_front)
    tree["pareto_history"] = pareto_history

    explored_classes = [
        c for c, info in class_status.items()
        if info.get("status") in ("EXHAUSTED", "EXPLORING")
    ]
    exploring_classes = [
        c for c, info in class_status.items()
        if info.get("status") == "EXPLORING"
    ]

    reasons = []

    condition_a = len(explored_classes) >= min_classes
    if not condition_a:
        reasons.append(
            f"Only {len(explored_classes)} classes explored, need {min_classes}"
        )

    condition_b = len(exploring_classes) == 0
    if not condition_b:
        reasons.append(
            f"Classes still exploring: {exploring_classes}"
        )

    condition_c = False
    if len(pareto_history) >= stability_rounds:
        recent = pareto_history[-stability_rounds:]
        condition_c = all(snapshot == recent[0] for snapshot in recent)
    if not condition_c:
        reasons.append(
            f"Pareto front not stable for {stability_rounds} rounds "
            f"(history length: {len(pareto_history)})"
        )

    converged = condition_a and condition_b and condition_c
    verdict = "CONVERGED" if converged else "EXPLORING"

    tree["global_status"] = verdict

    with open(tree_path, "w") as f:
        json.dump(tree, f, indent=2)

    result = {
        "global_status": verdict,
        "explored_classes": len(explored_classes),
        "exploring_classes": exploring_classes,
        "pareto_stable": condition_c,
        "reasons": reasons if not converged else [],
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
