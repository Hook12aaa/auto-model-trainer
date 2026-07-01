# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Auto Model Trainer** is a Claude Code plugin for long-horizon autonomous ML model training. It ships as pure markdown/YAML skills with no Python engine. Claude Code is the runtime.

Unlike the stage-gated model-trainer, auto-model-trainer explores multiple experiment paths simultaneously, tracks their lineage with SHA fingerprints, and autonomously converges on the best solution. A Stop hook enforces the autonomous loop -- Claude cannot stop until two-tier convergence passes mechanically.

## Plugin Structure

- `skills/` -- SKILL.md files that Claude loads and follows
- `commands/` -- Slash command stubs that trigger skills
- `hooks/` -- SessionStart hook bootstraps the plugin
- `scripts/` -- Python and bash scripts for convergence detection, Pareto computation, and merkle verification
- `.claude-plugin/` -- Plugin manifest

## Workflow

```
/auto-train <objective.yaml>
```

Single entry point. The system autonomously handles data validation, baseline creation, hypothesis generation, experiment tree exploration via Dynamic Workflows, variant evaluation, two-tier convergence detection, and final reporting with Kaggle submission.

To resume a previous run:

```
/auto-train --resume
```

## Key Concepts

### Experiment Tree (not a pipeline)

Experiments form a tree, not a linear chain. Each node is a variant (architecture, hyperparameter, or strategy change). Branches represent different exploration paths. The SHA fingerprint of each node's config + parent hash creates a Merkle-like lineage tree.

### Variant Worktrees

Each experiment variant lives in its own git worktree. Multiple variants can be explored in parallel via Dynamic Workflows. The worktree path encodes the lineage: `.auto-trainer/worktrees/<tree-hash>/`.

### Stop Hook and Autonomous Loop

The Stop hook runs check_convergence.sh every time Claude attempts to stop. If convergence conditions are not met, the stop is blocked and Claude must continue exploring. This makes autonomy structural rather than aspirational -- the system physically cannot stop until the evidence says it should.

### Two-Tier Convergence

**Tier 1 (Within-Class):** Each architecture class is checked for exhaustion via three conditions: diminishing returns (<1% over 2 rounds at depth >= 2), depth ceiling reached, or Pareto domination by another class at depth >= 1.

**Tier 2 (Cross-Class):** Global convergence requires all three conditions: minimum architecture class count explored, no classes still in EXPLORING status, and Pareto front stable for 2 consecutive iterations.

### Mandatory Divergence

If fewer architecture classes than the configured minimum have been explored, convergence is blocked and the explore skill must generate variants from untried classes. This prevents premature convergence on a single architecture family.

### Final Report

One report at the end: what was tried, what worked, why, and the recommended solution with full evidence trail. Includes Kaggle submission.csv generated from the winner's eval.py run on the test set.

## Objective File Format

The objective YAML must contain all required fields:

```yaml
dataset:
  train: path/to/train.csv
  test: path/to/test.csv
target_column: target
competition:
  metric: roc_auc
  metric_direction: maximize
submission_format:
  id_column: id
  prediction_column: prediction
```

## Skills

| Skill | What it does |
|---|---|
| using-auto-model-trainer | Bootstrap -- loaded at session start, establishes the 12-skill inventory and core principles |
| auto-train | Orchestrator -- dispatches subagents with inline context, runs convergence scripts directly, drives the full pipeline in one pass |
| data-validate | Runs 8 universal data quality checks with domain research and autonomous mitigation |
| feature-engineer | Spawns domain research agents to discover and lock feature transformations before exploration begins |
| baseline | Creates the minimal baseline variant at depth 0 to establish the floor metric |
| explore | Reads the experiment tree and Pareto front, generates variant specs with architecture-class tags, enforces mandatory divergence |
| build-variant | Subagent contract -- builds one variant from inline spec at a pre-created worktree path |
| evaluate | Subagent contract -- runs a variant, extracts metrics via inline manifest command, scores through 4-layer review |
| review-strategy | Subagent contract -- computes complexity ratios and Pareto dominance from inline numbers |
| converge | Two-tier convergence detection -- within-class exhaustion and cross-class coverage |
| ensemble | Reference doc -- the orchestrator runs caruana_ensemble.py directly, this skill documents the methodology |
| final-report | Produces the evidence-based report with 9 sections and generates the Kaggle submission.csv |

## Key Principles

- **Execute, Don't Eyeball** -- all numerical comparisons via executed Python scripts, never by reading numbers
- **Autonomous by Default** -- human intervention only at objective-setting and final approval, enforced by the Stop hook
- **Structural Distrust** -- no agent both produces and approves its own work
- **Merkle Lineage** -- every experiment's identity is its config hash chained to its parent hash
- **Explore then Exploit** -- breadth-first discovery, depth-first refinement, Pareto-guided pruning
- **Mechanical Convergence** -- two-tier convergence detection via executed scripts, never by subjective assessment

## Status Vocabulary

All skills use: DONE, DONE_WITH_CONCERNS, BLOCKED, NEEDS_CONTEXT, CONVERGED, EXPLORING.
