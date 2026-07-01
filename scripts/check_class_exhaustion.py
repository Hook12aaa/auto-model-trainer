#!/usr/bin/env python3
"""Check per-architecture-class diminishing returns.

Usage: python check_class_exhaustion.py <path-to-experiment-tree.json>

For each architecture_class in the tree:
  - EXHAUSTED if diminishing returns (<1% relative improvement in last 2 rounds
    within class) AND depth >= 2
  - EXHAUSTED if Pareto-dominated by another class AND depth >= 1
  - EXPLORING if experiments exist but neither exhaustion condition met
  - UNTRIED if no completed experiments

Updates class_status in the tree and writes back to disk.
"""

import json
import sys


def get_class_nodes(nodes_dict, arch_class):
    matching = [
        {**n, "exp_id": eid}
        for eid, n in nodes_dict.items()
        if n.get("architecture_class") == arch_class
        and n.get("status") in ("DONE", "DONE_WITH_CONCERNS")
    ]
    return sorted(matching, key=lambda n: n.get("depth", 0))


def best_metric(nodes, metric_key, maximize):
    values = [
        n["metrics"][metric_key]
        for n in nodes
        if metric_key in n.get("metrics", {})
    ]
    if not values:
        return None
    return max(values) if maximize else min(values)


def check_diminishing_returns(class_nodes, metric_key, maximize):
    if len(class_nodes) < 3:
        return False

    by_depth = {}
    for n in class_nodes:
        d = n.get("depth", 0)
        by_depth.setdefault(d, []).append(n)

    depths = sorted(by_depth.keys())
    if len(depths) < 3:
        return False

    last_three = depths[-3:]
    bests = []
    for d in last_three:
        b = best_metric(by_depth[d], metric_key, maximize)
        if b is None:
            return False
        bests.append(b)

    if bests[0] == 0:
        return False

    improvement_1 = abs(bests[1] - bests[0]) / abs(bests[0])
    improvement_2 = abs(bests[2] - bests[1]) / max(abs(bests[1]), 1e-12)

    return improvement_1 < 0.01 and improvement_2 < 0.01


def class_is_pareto_dominated(nodes_dict, target_class, all_classes, metric_key, maximize):
    target_nodes = [n for n in nodes_dict.values() if n.get("architecture_class") == target_class
                    and n.get("status") in ("DONE", "DONE_WITH_CONCERNS")]
    target_best_metric = best_metric(target_nodes, metric_key, maximize)
    target_min_params = min(
        (n.get("trainable_params", float("inf")) for n in target_nodes),
        default=float("inf")
    )

    if target_best_metric is None:
        return False

    for other_class in all_classes:
        if other_class == target_class:
            continue
        other_nodes = [n for n in nodes_dict.values() if n.get("architecture_class") == other_class
                       and n.get("status") in ("DONE", "DONE_WITH_CONCERNS")]
        other_best = best_metric(other_nodes, metric_key, maximize)
        other_min_params = min(
            (n.get("trainable_params", float("inf")) for n in other_nodes),
            default=float("inf")
        )
        if other_best is None:
            continue

        if maximize:
            metric_at_least = other_best >= target_best_metric
            metric_better = other_best > target_best_metric
        else:
            metric_at_least = other_best <= target_best_metric
            metric_better = other_best < target_best_metric

        params_at_least = other_min_params <= target_min_params
        params_better = other_min_params < target_min_params

        if (metric_at_least and params_at_least) and (metric_better or params_better):
            return True

    return False


def max_depth(class_nodes):
    if not class_nodes:
        return 0
    return max(n.get("depth", 0) for n in class_nodes)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <experiment-tree.json>", file=sys.stderr)
        sys.exit(1)

    tree_path = sys.argv[1]
    with open(tree_path, "r") as f:
        tree = json.load(f)

    metric_key = tree["primary_metric_key"]
    maximize = tree["metric_direction"] == "maximize"
    nodes = tree.get("nodes", {})

    all_classes = set()
    for n in nodes.values():
        ac = n.get("architecture_class")
        if ac:
            all_classes.add(ac)

    class_status = {}
    for arch_class in sorted(all_classes):
        class_nodes = get_class_nodes(nodes, arch_class)
        depth = max_depth(class_nodes)

        if not class_nodes:
            class_status[arch_class] = {
                "status": "UNTRIED",
                "best": None,
                "depth": 0,
            }
            continue

        best = best_metric(class_nodes, metric_key, maximize)

        exhausted = False
        if depth >= 2 and check_diminishing_returns(class_nodes, metric_key, maximize):
            exhausted = True
        if depth >= 1 and class_is_pareto_dominated(
            nodes, arch_class, all_classes, metric_key, maximize
        ):
            exhausted = True

        class_status[arch_class] = {
            "status": "EXHAUSTED" if exhausted else "EXPLORING",
            "best": best,
            "depth": depth,
        }

    tree["class_status"] = class_status

    with open(tree_path, "w") as f:
        json.dump(tree, f, indent=2)

    print(json.dumps(class_status))


if __name__ == "__main__":
    main()
