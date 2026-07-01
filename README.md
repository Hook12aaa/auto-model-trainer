# Auto Model Trainer

Takes an objective file and gives you a Kaggle-competitive model. One command, full autonomy, mechanical convergence.

> **Status:** 0.6.0 · MIT licensed · the autonomous sibling of [model-trainer](https://github.com/Hook12aaa/model-trainer).

---

## The problem

[model-trainer](https://github.com/Hook12aaa/model-trainer) is gated by design. You approve the hypothesis, you approve the experiment plan, you approve the report. That is the right shape when you are learning, or when the dataset is unfamiliar and you want a hand on the wheel at every turn. But once you have run that loop a few times, the gates stop being safety rails and start being the bottleneck. You know what you want: set the objective, walk away, come back to a model and a report that explains how it got there.

So the gates had to go. Not the rigour, the gates. Every discipline model-trainer enforces stays in place: execute don't eyeball, structural distrust, tamper-evident lineage. What changes is that no human stands between the rounds. You hand it an objective YAML; it validates the data, engineers features, builds a baseline, explores an experiment tree across architecture families, prunes against a Pareto front, ensembles the survivors, and writes the report. The only two moments you are in the loop are the objective at the start and the approval at the end.

The hard part of removing the human is that "autonomous" usually means "until it gets bored and stops". Here it does not. Autonomy is structural, not aspirational. A Stop hook runs a convergence script every single time Claude tries to end the turn, and blocks the stop unless the evidence says the search is actually done. Claude physically cannot quit early. The loop ends when the math says it ends, not when the model decides it has done enough.

---

## Quickstart

```
/auto-train objective.yaml
```

That is the whole interface. The objective file is the only thing you write:

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

Resume an interrupted run with `/auto-train --resume`. Everything between the objective and the final report is autonomous.

---

## The pipeline

```
objective
   │
   ▼
data-validate ──▶ feature-engineer ──▶ baseline
                                          │
                                          ▼
              ┌──────────── explore (+HPO) ◀────────┐
              │                  │                   │
              ▼                  ▼                   │
        build-variant  ──▶  evaluate  ──▶  review-strategy
              │                                      │
              └──────────────────▶ converge ────────┘
                                       │
                            CONVERGED  ▼
                                  ensemble ──▶ final-report ──▶ submission.csv
```

The explore/build/evaluate/strategy loop runs many times. `converge` is what the Stop hook calls; until it returns `CONVERGED`, the loop keeps going. When it does converge, the Pareto-front survivors get blended and the report is written.

---

## Skills

| Skill | What it does |
|---|---|
| `using-auto-model-trainer` | Bootstrap, loaded at session start, establishes the skill inventory and core principles |
| `auto-train` | Orchestrator: registers the Stop hook, validates the objective, runs the autonomous explore-evaluate-converge loop |
| `data-validate` | Runs 8 universal data quality checks and autonomously mitigates fixable issues |
| `feature-engineer` | Researches the dataset domain via parallel agents, writes an executable `features.py`, verifies it runs before locking the manifest |
| `baseline` | Establishes `exp_000`, the simplest interpretable model that defines the performance floor |
| `explore` | Reads the experiment tree, proposes the next batch of variants, tags each with an architecture class, enforces divergence toward untried classes |
| `build-variant` | Builds one variant in an isolated git worktree, resolving config through the parent chain |
| `review-strategy` | Scores complexity, checks architecture-vs-HP balance, updates the Pareto front via dominance analysis |
| `evaluate` | Runs a variant, extracts metrics via executed scripts, scores it through a 4-layer review |
| `converge` | Two-tier convergence detection: within-class exhaustion plus cross-class coverage, wired into the Stop hook |
| `ensemble` | Caruana greedy selection over the Pareto front, routed back through the evaluate pipeline |
| `final-report` | The evidence-based report plus the Kaggle `submission.csv` generated from the winner's `eval.py` |

---

## Why this exists

This started as model-trainer. I built that one to be followable: someone learning ML could watch every decision, someone experienced could trust the evidence behind it. The gating was the feature. You signed off on the hypothesis, the plan, the report.

Then I ran it enough times to notice the gates were the bottleneck. The thinking model-trainer asked me to do at each gate (is this the right architecture direction, has this batch told us anything new, is the winner honest) was thinking the evidence already answered. I was rubber-stamping. So I pulled the human out of the middle and put a machine there instead.

The machine is the Stop hook. It is the same mechanism `/goal` and `/loop` use to keep Claude working, but with the subjective "should I keep going" replaced by a script that reads the experiment tree and decides mechanically. That is the key: a stop is only allowed when convergence passes, and convergence is computed, not felt. The other half of the insight was two-tier convergence. You cannot declare a search done just because one architecture family stopped improving. You have not tried the others. So convergence requires both per-class exhaustion *and* cross-class coverage. Breadth before you are allowed to call it.

It has been tested on six Kaggle competitions across binary classification, multi-class classification, and regression, over four versions of iterative improvement. Best scores range from 0.8268 accuracy (Titanic) to 0.1071 RMSE on log prices (House Prices) to 0.4387 log loss (Cirrhosis). The House Prices result lands inside the honest medal zone. Not record-breaking, not magic. A model you can trust, found without you in the room.

---

## How it actually behaves

### Data first

`data-validate` runs 8 universal checks (shape, types, missing values, target, duplicates, distributions, correlations, outliers) and mitigates what it can on its own. There is no separate human gate. What it fixes, it records; what it cannot fix, it surfaces as a concern the rest of the pipeline carries forward. Nothing trains on data that has not been looked at.

### Features are researched, not guessed

`feature-engineer` does not reach for a default bag of transformations. It spawns agents to research the dataset's domain (what `Cabin` means on the Titanic, how a passenger ID encodes a group on Spaceship Titanic), merges their proposals into an executable `features.py`, and runs it against the training data before locking the manifest. Features are derived from what the columns actually mean, not from a checklist.

### The experiment tree is a tree, not a chain

Experiments branch. Each node is a variant (an architecture, a hyperparameter set, a strategy shift) with a SHA-256 fingerprint derived from its own config hash and its parent's hash. That makes the tree a Merkle structure: tamper-evident, with every node's identity chained to where it came from. Different exploration paths are different branches, and you can read the lineage straight off the worktree path.

### Architecture breadth before hyperparameter depth

Research on AutoML consistently finds that roughly 94% of the variance is architecture and 6% is hyperparameters. So the explorer is forced to diverge: if fewer than the configured minimum of architecture classes have been tried, convergence is blocked and `explore` must generate variants from an untried class. You do not get to tune the 6% until you have surveyed the 94%.

### The Stop hook enforces autonomy

The hook is a command-type Stop hook: it runs `check_convergence.sh`, not a prompt. Every time Claude tries to end the turn, the script reads the tree and either lets the stop through or blocks it and sends Claude back into the loop. Because it is a script and not a remembered instruction, it survives context compaction. The loop does not forget itself when the conversation gets summarized. Autonomy that depends on the model remembering to be autonomous is not autonomy.

### Two-tier convergence

**Tier 1, within-class:** an architecture class is exhausted when any of three conditions holds: diminishing returns (under 1% over two rounds at depth ≥ 2), the depth ceiling is reached, or it is Pareto-dominated by another class at depth ≥ 1.

**Tier 2, cross-class:** the global search converges only when all three hold: the minimum number of architecture classes has been explored, no class is still in `EXPLORING`, and the Pareto front has been stable for two consecutive iterations.

Both tiers are executed scripts. Nothing here is a judgement call.

### Ensemble at the end

Once the search converges, `ensemble` runs Caruana greedy selection over the Pareto-front models (repeatedly adding the model that most improves the blend, with replacement) and routes the result back through the same 4-layer evaluate pipeline every other variant went through. The ensemble does not get a free pass.

---

## When not to use this

- **Image, text, or audio data.** This is built for tabular supervised learning. It will not load a CNN or a transformer for you.
- **Time-series with real temporal structure.** The split strategies assume rows are exchangeable. Leakage across time is not something it guards against.
- **Datasets above ~100K rows without tuning.** It will run, but the parallel-worktree exploration was sized for Kaggle-scale tabular problems, not millions of rows.
- **If you need neural architecture search.** The architecture classes are the classic tabular families (linear, tree ensembles, gradient boosting). It does not invent architectures.
- **If you want interactive control.** The whole point is that you do not get a gate between rounds. If you want to approve each step, use [model-trainer](https://github.com/Hook12aaa/model-trainer) instead.

---

## Installing

### From GitHub (recommended)

Run these inside Claude Code:

```
/plugin marketplace add Hook12aaa/auto-model-trainer
/plugin install auto-model-trainer@auto-model-trainer
```

### From a local clone

```
git clone https://github.com/Hook12aaa/auto-model-trainer.git
/plugin marketplace add /path/to/auto-model-trainer
/plugin install auto-model-trainer@auto-model-trainer
```

If the path contains spaces, quote it or symlink to a space-free location:

```bash
ln -s "/path/with spaces/auto-model-trainer" ~/auto-model-trainer-dev
/plugin marketplace add ~/auto-model-trainer-dev
```

The `SessionStart` hook bootstraps the plugin automatically and injects `using-auto-model-trainer` into every session. Verify the install by running `/auto-train` with no arguments. It will tell you it needs an objective file.

---

## What it needs

| Requirement | Why |
|---|---|
| **Git repository** | Variants live in git worktrees for isolation. If `git rev-parse --git-dir` fails, the pipeline stops and asks whether to `git init`. |
| **Python in `PATH`** | All numerical work (data checks, Pareto computation, convergence, merkle verification) runs through executed Python. Bring `pandas`, `scikit-learn`, `xgboost`, and `lightgbm`. |
| **A dataset** | Train and test CSVs, referenced by the objective file. |
| **An objective YAML** | The dataset paths, target column, metric and direction, and submission format. |

No custom runtime, no Python engine, no daemon. The plugin is markdown, YAML, and a handful of scripts. Claude Code is the runtime.

---

## Repository layout

```
.
├── .claude-plugin/        # plugin manifest + local marketplace
├── commands/              # /auto-train slash command stub
├── hooks/                 # SessionStart bootstrap + Stop convergence hook
├── scripts/
│   ├── check_convergence.sh        # called by the Stop hook
│   ├── check_class_exhaustion.py   # tier-1 within-class
│   ├── check_cross_class_coverage.py # tier-2 cross-class
│   ├── compute_pareto.py           # Pareto front
│   ├── caruana_ensemble.py         # greedy ensemble selection
│   └── verify_merkle_chain.py      # lineage integrity
├── skills/
│   ├── using-auto-model-trainer/   # session-start bootstrap
│   ├── auto-train/                 # orchestrator
│   ├── data-validate/              # 8-check validation + mitigation
│   ├── feature-engineer/           # researched feature transformations
│   ├── baseline/                   # exp_000 floor
│   ├── explore/                    # variant proposals + divergence
│   ├── build-variant/              # isolated worktree build
│   ├── review-strategy/            # complexity · Pareto · coherence
│   ├── evaluate/                   # 4-layer metric review
│   ├── converge/                   # two-tier convergence
│   ├── ensemble/                   # Caruana blend
│   └── final-report/               # report + submission.csv
├── docs/                  # design specs and plans
├── CLAUDE.md              # project instructions
└── README.md
```

---

## Principles I will not bend on

1. **Execute, don't eyeball.** Every metric comparison, every Pareto check, every gap calculation is a script that runs and returns JSON. LLMs are bad at arithmetic when numbers get close; scripts are not.
2. **Autonomous by default.** The human is in the loop twice: the objective and the final approval. Everywhere else, the evidence decides.
3. **Structural distrust.** No agent both produces and approves its own work. Builders are reviewed, metrics are reviewed, strategies are reviewed, even the ensemble is reviewed.
4. **Merkle lineage.** Every experiment's identity is its config hash chained to its parent's hash. The tree is tamper-evident, verified by an executed script.
5. **Explore then exploit.** Breadth-first discovery across architecture families, depth-first refinement within them, Pareto-guided pruning between them.
6. **Mandatory divergence.** Convergence is blocked until the minimum number of architecture classes has been explored. No premature convergence on one family.
7. **Compaction-proof.** The autonomous loop lives in a command-type Stop hook, not a remembered instruction. It survives context summarization because it is a script, not a memory.
8. **Mechanical convergence.** The search ends when two-tier convergence passes, computed by scripts. Never by a subjective "this looks done".

---

## Tested on

Six competitions tested across four plugin versions, all fully autonomous, zero human intervention between objective and final report.

| Competition | Task | Metric | v0.3.0 | v0.4.0 | v0.5.0 | v0.6.0 | Best |
|---|---|---|---|---|---|---|---|
| Titanic | Binary | Accuracy | 0.8268 | -- | -- | -- | 0.8268 |
| Spaceship Titanic | Binary | Accuracy | 0.8099 | 0.8153 | 0.8146 | 0.8062 | 0.8153 |
| House Prices | Regression | RMSE (log) | 0.1256 | 0.1105 | 0.1237 | 0.1071 | 0.1071 |
| Cirrhosis (PS S3E26) | Multi-class | Log loss | 0.4393 | 0.4424 | 0.4409 | 0.4387 | 0.4387 |
| Bank Churn (PS S4E1) | Binary | ROC-AUC | 0.8945 | 0.8926 | 0.8965 | -- | 0.8965 |
| TPS Jan 2021 | Regression | RMSE | 0.6953 | 0.6962 | 0.6967 | 0.6990 | 0.6953 |

All task types are covered: binary classification (accuracy, ROC-AUC), multi-class (log_loss), and regression (RMSE).

Four versions of iterative improvement got the scores here. v0.4.0 added feature engineering. The v0.4.0-to-v0.5.0 stretch added domain research, CatBoost, and ensemble diversity. v0.6.0 was a dispatch redesign to stop process drift mid-run. Across the re-tested competitions, scores improved on 2 of 5, held steady on 2, and one run was left incomplete. The dispatch redesign eliminated process drift on 3 of the 4 completed runs.

Honest read: these are well-studied tabular problems and the scores land in the competitive band, not at the top. The House Prices RMSE of 0.1071 is inside the honest medal zone, where top solutions sit around 0.105 to 0.115. The point is not record-breaking scores. The point is that six different problems got a trustworthy model with the human out of the room, and each left a 9-section report explaining exactly how.

---

## Inspirations

- **[model-trainer](https://github.com/Hook12aaa/model-trainer).** The direct predecessor. Auto Model Trainer is what happens when you keep its disciplines and remove its gates.
- **AIDE.** The idea of treating model building as a tree search over experiments, with each node a code variant, shaped how the experiment tree works here.
- **AutoGluon.** The baseline I measure against, and a reminder that a strong default ensemble is a high bar to clear.
- **Caruana ensemble selection.** The greedy forward-selection-with-replacement method the ensemble stage is built on, from Caruana et al.'s work on ensemble library selection.

---

## Contributing

If you have a sharper convergence criterion, an architecture class the explorer is missing, or a reviewer layer the evaluate pipeline should have, I want to see it. File an issue describing the behaviour you want to change and why, or open a pull request against a dedicated branch.

A few guidelines to save time in review:

- Anything numerical goes through a script. If you find yourself writing `if metric_a > metric_b` inline in a skill, that is the signal to extract it.
- Keep the autonomy structural. New loop logic belongs in the convergence scripts the Stop hook reads, not in prose the model is asked to remember.
- New skills follow the existing anatomy and emit a status from the formal vocabulary: `DONE`, `DONE_WITH_CONCERNS`, `BLOCKED`, `NEEDS_CONTEXT`, `CONVERGED`, `EXPLORING`.

---

## License

MIT. Use it, fork it, build on it. Attribution is welcome but not required.
