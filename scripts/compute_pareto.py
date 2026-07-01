#!/usr/bin/env python3
"""Compute Pareto front over (primary_metric, trainable_params).

Usage: python compute_pareto.py <path-to-experiment-tree.json>

Reads completed nodes, finds the non-dominated set, updates the tree's
pareto_front array, writes back to disk, and prints a JSON summary.
"""

import json
import sys


def dominates(a, b, maximize_metric):
    a_metric, a_params = a
    b_metric, b_params = b

    if maximize_metric:
        metric_at_least = a_metric >= b_metric
        metric_better = a_metric > b_metric
    else:
        metric_at_least = a_metric <= b_metric
        metric_better = a_metric < b_metric

    params_at_least = a_params <= b_params
    params_better = a_params < b_params

    return (metric_at_least and params_at_least) and (metric_better or params_better)


def compute_pareto_front(nodes_dict, metric_key, maximize_metric):
    points = []
    for exp_id, node in nodes_dict.items():
        if node.get("status") not in ("DONE", "DONE_WITH_CONCERNS"):
            continue
        metrics = node.get("metrics", {})
        metric_val = metrics.get(metric_key)
        params = node.get("trainable_params")
        if metric_val is None or params is None:
            continue
        points.append((exp_id, float(metric_val), int(params)))

    front = []
    for i, (eid_i, m_i, p_i) in enumerate(points):
        dominated = False
        for j, (eid_j, m_j, p_j) in enumerate(points):
            if i == j:
                continue
            if dominates((m_j, p_j), (m_i, p_i), maximize_metric):
                dominated = True
                break
        if not dominated:
            front.append(eid_i)

    return front


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <experiment-tree.json>", file=sys.stderr)
        sys.exit(1)

    tree_path = sys.argv[1]
    with open(tree_path, "r") as f:
        tree = json.load(f)

    metric_key = tree["primary_metric_key"]
    maximize_metric = tree["metric_direction"] == "maximize"
    nodes = tree.get("nodes", {})

    front = compute_pareto_front(nodes, metric_key, maximize_metric)

    tree["pareto_front"] = front

    with open(tree_path, "w") as f:
        json.dump(tree, f, indent=2)

    result = {"pareto_front": front, "total_points": len([
        n for n in nodes.values()
        if n.get("status") in ("DONE", "DONE_WITH_CONCERNS")
    ])}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
