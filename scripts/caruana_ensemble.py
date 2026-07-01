#!/usr/bin/env python3
"""Caruana greedy ensemble selection over the Pareto front.

Usage: python caruana_ensemble.py <experiment-tree.json> <metric_key> <metric_direction> <output_path>

Reads the tree's pareto_front, loads each front model's val_predictions.npy and
val_labels.npy from its worktree_path, then runs Caruana greedy forward selection
with replacement: start from the best single model and repeatedly add the model
whose inclusion most improves the blended validation score, stopping when no
addition improves. Writes ensemble_config.json and prints a JSON summary.
"""

import json
import os
import sys

import numpy as np


def score(preds, labels, metric_key):
    if metric_key == "accuracy":
        return float(np.mean(np.round(preds) == labels))
    if metric_key == "rmse":
        return float(np.sqrt(np.mean((preds - labels) ** 2)))
    if metric_key == "mae":
        return float(np.mean(np.abs(preds - labels)))
    if metric_key == "r2":
        ss_res = np.sum((labels - preds) ** 2)
        ss_tot = np.sum((labels - np.mean(labels)) ** 2)
        return float(1.0 - ss_res / ss_tot)
    if metric_key == "f1":
        pred_pos = np.round(preds) == 1
        true_pos = labels == 1
        tp = float(np.sum(pred_pos & true_pos))
        fp = float(np.sum(pred_pos & ~true_pos))
        fn = float(np.sum(~pred_pos & true_pos))
        denom = 2.0 * tp + fp + fn
        return 2.0 * tp / denom if denom > 0 else 0.0
    if metric_key == "roc_auc":
        order = np.argsort(preds)
        ranked_labels = labels[order]
        n_pos = float(np.sum(labels == 1))
        n_neg = float(np.sum(labels == 0))
        if n_pos == 0 or n_neg == 0:
            return 0.5
        ranks = np.argsort(np.argsort(preds)) + 1.0
        sum_ranks_pos = float(np.sum(ranks[labels == 1]))
        return (sum_ranks_pos - n_pos * (n_pos + 1.0) / 2.0) / (n_pos * n_neg)
    raise ValueError(f"Unsupported metric: {metric_key}")


def resolve_front_nodes(tree, output_path):
    nodes = tree.get("nodes", {})
    resolved = []
    for entry in tree.get("pareto_front", []):
        if isinstance(entry, dict):
            exp_id = entry["exp_id"]
            worktree_path = entry["worktree_path"]
        else:
            exp_id = entry
            worktree_path = nodes[entry]["worktree_path"]
        resolved.append((exp_id, worktree_path))
    return resolved


def main():
    if len(sys.argv) != 5:
        print(
            f"Usage: {sys.argv[0]} <experiment-tree.json> <metric_key> <metric_direction> <output_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    tree_path, metric_key, metric_direction, output_path = sys.argv[1:5]
    maximize = metric_direction == "maximize"

    with open(tree_path, "r") as f:
        tree = json.load(f)

    front = resolve_front_nodes(tree, output_path)

    if len(front) <= 1:
        result = {"status": "SKIPPED"}
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result))
        sys.exit(0)

    exp_ids = []
    preds_list = []
    labels = None
    for exp_id, worktree_path in front:
        p = np.load(os.path.join(worktree_path, "val_predictions.npy")).astype(float)
        l = np.load(os.path.join(worktree_path, "val_labels.npy")).astype(float)
        if labels is None:
            labels = l
        exp_ids.append(exp_id)
        preds_list.append(p)

    n = len(preds_list)

    def better(a, b):
        return a > b if maximize else a < b

    single_scores = [score(preds_list[i], labels, metric_key) for i in range(n)]
    best_idx = max(range(n), key=lambda i: single_scores[i] if maximize else -single_scores[i])
    best_single_score = single_scores[best_idx]

    selection = [best_idx]
    current_sum = preds_list[best_idx].copy()
    current_score = best_single_score

    while True:
        candidate_idx = None
        candidate_score = current_score
        for i in range(n):
            blend = (current_sum + preds_list[i]) / (len(selection) + 1)
            s = score(blend, labels, metric_key)
            if better(s, candidate_score):
                candidate_score = s
                candidate_idx = i
        if candidate_idx is None:
            break
        selection.append(candidate_idx)
        current_sum = current_sum + preds_list[candidate_idx]
        current_score = candidate_score

    counts = {}
    for i in selection:
        counts[i] = counts.get(i, 0) + 1
    total = len(selection)

    selected_models = [
        {"exp_id": exp_ids[i], "weight": counts[i] / total}
        for i in sorted(counts, key=lambda i: counts[i], reverse=True)
    ]

    result = {
        "status": "DONE",
        "selected_models": selected_models,
        "ensemble_score": current_score,
        "best_single_score": best_single_score,
        "beats_best_single": better(current_score, best_single_score),
    }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
