#!/usr/bin/env python3
"""Verify SHA-256 Merkle chain integrity of the experiment tree.

Usage: python verify_merkle_chain.py <path-to-experiment-tree.json>

For each node: recomputes SHA-256(config_hash + parent_sha) and compares
against the stored sha. parent_sha is the parent node's sha, or "root"
for baseline nodes (no parent).

Exit 0 if all valid, exit 1 if any tamper detected.
"""

import hashlib
import json
import sys


def expected_sha(config_hash, parent_sha):
    return hashlib.sha256(f"{config_hash}+{parent_sha}".encode()).hexdigest()


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <experiment-tree.json>", file=sys.stderr)
        sys.exit(1)

    tree_path = sys.argv[1]
    with open(tree_path, "r") as f:
        tree = json.load(f)

    nodes = tree.get("nodes", {})

    mismatches = []
    checked = 0

    for exp_id, node in nodes.items():
        config_hash = node["config_hash"]
        stored_sha = node["sha"]
        parent_id = node.get("parent")

        if parent_id is None:
            parent_sha = "root"
        else:
            parent_node = nodes.get(parent_id)
            if parent_node is None:
                mismatches.append({
                    "exp_id": exp_id,
                    "error": f"parent {parent_id} not found in tree",
                })
                checked += 1
                continue
            parent_sha = parent_node["sha"]

        computed = expected_sha(config_hash, parent_sha)
        checked += 1

        if computed != stored_sha:
            mismatches.append({
                "exp_id": exp_id,
                "expected": computed,
                "stored": stored_sha,
            })

    valid = len(mismatches) == 0
    result = {
        "valid": valid,
        "nodes_checked": checked,
        "mismatches": mismatches,
    }
    print(json.dumps(result))
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
