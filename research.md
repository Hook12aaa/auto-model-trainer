# Research Notes: auto-model-trainer

These are my working notes on how this plugin came to be. Not docs -- the thinking. What I tried, what broke, what I'd do differently.

## Starting point: the gates were the problem

I already had `model-trainer`. It worked, but it was a 5-stage gated pipeline:

```
data-check -> hypothesize -> design-experiments -> train -> report
```

Three of those stages stopped and waited for me: approve the hypotheses, approve the experiment plan, pick the winner from the batch report. That's fine for a careful one-shot run. It's terrible for anything long-horizon. The system couldn't run for more than a few minutes before it hit a gate and parked, waiting for a human to read something and say "yes, continue."

The gates were the bottleneck. Not the modeling, not the compute -- the human in the loop. And the human-in-the-loop wasn't adding much: most of the time I was rubber-stamping. The hypotheses were reasonable, the experiment plan was reasonable, the winner was usually obvious from the metrics.

So the question I kept coming back to was: what if autonomy was *structural* instead of *aspirational*? Most "autonomous" agents are autonomous by vibe -- you tell them to keep going and hope they don't stop early. I wanted a system that *physically could not stop* until the evidence said it was done. Not "please continue," but "you are not permitted to halt."

## The /goal insight

The mechanism turned out to be sitting in Claude Code already: `/goal`.

I went and looked at how `/goal` actually works internally. It's a Stop hook. After every turn, when Claude tries to end its turn, a hook fires. A lightweight model (Haiku) reads the conversation and judges: is the goal done? If not done, the hook blocks the stop and injects guidance, and the next turn starts immediately. That's the whole trick. The "autonomy" is just a hook that refuses to let you quit.

That was the breakthrough. But I could also see immediately where `/goal` was weak: it uses **LLM evaluation**. Haiku reads the *conversation history* to decide if you're done. That's fragile for a long run for two reasons:

1. It's subjective -- "are we done?" is a judgment call, and judgment calls drift.
2. It dies under compaction. When the conversation gets compressed, the evaluator is reading a summary of a summary. The actual state is gone.

So the improvement was obvious: don't judge the conversation, **judge the disk**. Replace Haiku-reads-transcript with a *script* that reads `experiment-tree.json`. Convergence becomes mechanical -- a Python script computes whether the conditions are met, returns block-or-allow. The conversation can be compacted into oblivion and it doesn't matter, because the experiment tree on disk *is* the state. The hook reads the tree, not the chat.

This is the single most important decision in the whole project. Everything else follows from it. "The state is on disk, the hook reads the disk, the conversation is disposable."

## Two-tier convergence: avoiding the XGBoost trap

Once the Stop hook is mechanical, the obvious next question is: what does the script actually check? And the naive answer -- "has the Pareto front stopped moving?" -- is wrong, and wrong in a way that took me a moment to see.

If you only watch the Pareto front, you converge too early. Here's the failure: you try XGBoost, it does well, you tune it, it plateaus, the front stabilizes for two rounds, so it declares CONVERGED. You never tried a neural net. You never tried KNN. You tuned one model family forever and called it done. This is, not coincidentally, the single most common AutoML failure mode I've watched happen: over-tuning one model family because it was the first thing that worked.

So convergence has to be two-tier:

- **Tier 1 -- within-class exhaustion.** Each architecture family (linear, tree-based, neural, etc.) has its own convergence curve. A class is EXHAUSTED when it shows diminishing returns (<1% relative improvement over 2 rounds at depth >= 2), or it hit a depth ceiling, or it got Pareto-dominated by another class after at least one refinement attempt.
- **Tier 2 -- cross-class coverage.** Global convergence requires that you've explored a *minimum number of architecture families* (3 for tabular), that no class is still EXPLORING, and that the global Pareto front has been stable for 2 consecutive iterations.

And the piece that ties it together: **mandatory divergence**. When a class goes EXHAUSTED, the explore skill is *forced* to propose variants from UNTRIED classes before it's allowed to do any more depth refinement. You literally cannot keep tuning XGBoost when neural nets haven't been touched. The convergence check blocks the stop *and* the explore logic blocks the lazy "just tune the winner again" move.

Tier 1 is "have I finished this family," Tier 2 is "have I tried enough families." You need both. One without the other either never stops or stops too soon.

## First dogfood: Titanic

Time to actually run it. Titanic -- 891 rows, binary classification, the "hello world" of Kaggle.

Result:
- **0.8268** validation accuracy
- Winner: **KNN with k=11**
- 9 experiments, 3 architecture classes, ~20 minutes, fully autonomous

My honest read: this is a *competent practitioner*. 0.82 is above the community "0.8 is a good score" bar, and it beats AutoGluon's default on the same data. The two-tier convergence did its job -- it didn't camp on the first tree model, it explored three families and the winner was actually KNN, which I would not have guessed going in. That's the system finding something a human wouldn't have bet on. Good.

But the result also told me exactly where the ceiling was, and it wasn't where I'd put my effort:

- **No feature engineering.** It trained on 9 raw columns. Anyone who's done Titanic knows the whole game is feature engineering -- Title extracted from Name, FamilySize, Deck from Cabin, fare bins. The system didn't do *any* of that.
- **No ensembling.** It picked one winner. The standard move is to blend the top models.
- **Architecture exploration added only +1.37% over baseline.** That's the damning number. All that careful tree-search over architecture families bought ~1.4%. The architecture choice barely mattered.

The benchmark conclusion wrote itself: **on tabular data, the ceiling is feature engineering, not architecture choice.** I'd built a sophisticated search over the thing that mattered least.

## Three enhancements (v0.4.0)

The Titanic run plus an industry benchmark pointed at three gaps, in priority order, so I built for all three at once.

**1. Feature engineering -- research-driven, not template-based.** I deliberately did *not* want a fixed library of "if categorical, one-hot it" templates. That's brittle and it doesn't generalize across domains. Instead: spawn research agents that *analyze the actual data and the actual domain* and propose transformations. They produce a single shared `features.py` that every variant imports. Crucially, the feature set is **locked before exploration begins** -- features don't vary between variants, only architecture and hyperparameters do. That keeps each experiment a clean single-variable test, and it means every model in the tree is comparable.

**2. Smart HPO -- diagnosis-driven, not random.** The old depth-refinement logic proposed arbitrary HP deltas. Replace that: when a class is plateauing, spawn an agent to *read the training trajectory* and diagnose the bottleneck. Train loss dropping but val flat means underfitting, so add capacity. Val diverging means overfitting, so add regularization. Both flat early means a capacity ceiling, so stop tuning and change class. The single-key delta rule stays; the delta is now *informed* rather than guessed. The hypothesis field carries the diagnosis: "Underfitting detected -- n_estimators 100 to 300."

**3. Caruana ensembling -- one pass, post-hoc.** After convergence, before the final report, take the Pareto-front models and run Caruana greedy weighted selection. Start with the best single model, greedily add whichever model most improves the blended score, repeat until nothing helps. One pass. It does *not* re-enter the exploration loop -- that was a firm constraint, because the whole point of ensembling here is to be a cheap finishing move, not another search.

## Second dogfood: Spaceship Titanic

Bigger test. Spaceship Titanic -- 8,693 rows, binary classification, more structure to find.

Result:
- **0.8153** OOF accuracy (v0.4.0)
- Winner: **Caruana ensemble (XGBoost + LightGBM)**
- 8 experiments, 4 architecture classes, ~27 minutes, autonomous
- Feature engineering produced **41 features from 33 research proposals**: group/cabin structure parsing, log1p on spend columns, cryo/age handling

The thing that made me sit up: the feature-engineering agents **independently rediscovered the canonical transformations** that the top public solutions use. Group structure from the passenger ID, splitting the cabin string into deck/num/side, log-transforming the spend columns, the cryosleep interaction. Nobody told it those. It read the data, reasoned about the domain, and arrived at the same features the leaderboard converged on. That's the research-driven approach working exactly as intended.

The ensemble beat the best single model by a small margin, but *correct* and in the right direction. Caruana isn't going to produce miracles; averaging Pareto-front models is a modest, reliable gain, and that's what it delivered.

Overall: beats AutoGluon's default, lands in the competitive band. Two datasets now, both autonomous, both landing where a competent human would land.

## Data expertise maturation (v0.4.0 to v0.5.0)

I retested on five more competitions to see whether the three enhancements held up across problem types. The scores landed at median, not in the medal range. I dug into why.

The root cause was shallow data understanding, thin feature sets, and homogeneous ensembles. The system was competent but generic. It wasn't reaching for the domain-specific moves that separate a median finish from a medal.

So I deepened the data side. I added domain research framing to data-validate -- column semantics, and active discovery of external data sources. I added CatBoost as an architecture class, since it was the obvious missing strong single model on categorical-heavy data. I added ensemble diversity guidance and a stacking description so the blends stopped being three flavors of gradient boosting. And I added domain-aware evaluation thresholds: medical and financial problems now get stricter overfitting checks, because the cost of an overfit model is higher there.

That stretch produced Bank Churn at **0.8965** ROC-AUC, the best result on that competition across all versions.

## The drift problem

The v0.5.0 re-test surfaced something I hadn't fully appreciated: Claude writes its own scripts instead of using the ones the plugin provides.

`ensemble_blend.py` and `build_ensemble.py` appeared in run after run, despite HARD-GATEs that explicitly said "Do NOT write this script." Claude also invented its own directory structures -- `autotrain/`, `experiments/` -- instead of using the `.auto-trainer/` layout the plugin defines.

The realization: HARD-GATEs don't prevent drift, because drift is an assumption problem, not a violation problem. Claude decides to write a script before it ever reads the gate that says not to. By the time the gate is in context, the decision is already made and the gate just gets rationalized around. You can't gate your way out of a choice that was made upstream of the gate.

## Gates vs process design

This reframed the whole problem for me. HARD-GATEs are for integrity checks: wrong preconditions, missing data, a tampered lineage chain. They catch states that are objectively wrong. Process drift is a different animal, and it's solved by process design, not by prohibitions.

I went and studied model-trainer's dispatch pattern for how it avoided this. The pattern is narrow-scope subagents, inline context, pre-created paths, and proof-of-execution. The orchestrator resolves everything up front, inlines it in the dispatch, and the subagent has no room to improvise because there's nothing left for it to decide. You don't tell the subagent "don't invent a path" -- you hand it the path so there's no path to invent.

## Dispatch redesign (v0.6.0)

I converted auto-train from a skill-invoking orchestrator into a subagent-dispatching one.

build-variant, evaluate, and review-strategy became narrow subagent contracts that receive inline context only. The ensemble logic became a reference doc -- the orchestrator runs `caruana_ensemble.py` directly instead of asking a subagent to handle ensembling, which is exactly where the rogue `ensemble_blend.py` scripts kept appearing.

The result: drift was eliminated on 3 of 4 completed runs. House Prices hit **0.1071** RMSLE, inside the medal zone. Cirrhosis hit **0.4387** log loss, a new best. And the `-p` mode pipeline completion issue that had been nagging since v0.4.0 is fully solved -- the pipeline runs end to end without parking.

## Benchmark summary

Best scores across four versions of iterative improvement, on six Kaggle competitions:

| Competition | Task | Metric | Best | Version |
|---|---|---|---|---|
| House Prices | Regression | RMSLE | 0.1071 | v0.6.0 |
| Cirrhosis (PS S3E26) | Multi-class | Log loss | 0.4387 | v0.6.0 |
| Bank Churn (PS S4E1) | Binary | ROC-AUC | 0.8965 | v0.5.0 |
| Spaceship Titanic | Binary | Accuracy | 0.8153 | v0.4.0 |
| TPS Jan 2021 | Regression | RMSE | 0.6953 | v0.3.0 |
| Titanic | Binary | Accuracy | 0.8268 | v0.3.0 |

The House Prices RMSLE of 0.1071 is inside the honest medal zone, where top solutions sit around 0.105 to 0.115. The rest land in the competitive band, not at the top. The point was never record-breaking scores. The point is that six different problems got a trustworthy model with the human out of the room, each with a 9-section report explaining exactly how it got there.

## What I know now

- **The Stop hook is the whole thing.** Everything else is downstream of "the hook reads disk state and refuses to stop until a script says so." If I had to throw away everything but one idea, it'd be that.
- **Feature engineering beats architecture choice on tabular data.** Both early dogfood runs confirmed it. The +1.37% from architecture search on Titanic versus the canonical-feature rediscovery on Spaceship -- the evidence is one-sided.
- **Mandatory divergence prevents the most common AutoML failure.** Over-tuning one model family is the default failure, and forcing UNTRIED classes before more depth is what stops it. This is a structural fix, not a heuristic.
- **Merkle lineage is genuinely novel.** Every node's identity is SHA-256(config_hash + parent_sha), chained to the root. I haven't found another AutoML tool or autonomous agent that does config-hash chaining of experiments. It means tampering with any ancestor invalidates the chain, and the convergence script verifies integrity before it trusts the tree.
- **Process drift is the hardest problem in LLM-as-runtime systems.** You cannot tell an LLM "don't improvise." You have to design the process so improvisation has no room. The dispatch pattern -- inline context, pre-created paths, a single deliverable per subagent -- is the structural answer. It isn't perfect, but it took drift from endemic to rare, and that's the difference between a system you can trust to run unattended and one you can't.
- **The skill-cheat canonical structure earns its keep.** Writing the skills with HARD-GATEs, explicit Gate Functions, and Rationalization Tables felt like overhead, but the voice-review pass caught real design bugs -- places where a skill could rationalize its way out of doing the work. Worth it.

## What's still missing

Being honest about the gaps:

- **Real stacking.** Caruana greedy averaging is the weak form of ensembling. A meta-learner trained on out-of-fold predictions would be stronger. I chose Caruana because it's a safe one-pass move; stacking is the next step up.
- **Validation-overfit hardening.** Right now the validation metric is the proxy for leaderboard score. A held-out test gate would catch the case where the search overfits to the validation split.
- **MLE-bench.** I'm scoring on six hand-picked datasets. To make any defensible claim about capability, this needs to run on MLE-bench.
- **Neural net architecture class.** The tabular families are covered; a proper NN class isn't built out.
- **External data and pseudo-labeling.** The gap to medals is in data tricks and ensemble diversity, not in the loop. That's a modeling problem, not a governance problem, and it's the headroom now.

## Where this sits

Let me be precise about what this is and isn't, because it's easy to oversell.

It is **not** an AutoML framework in the Auto-sklearn / AutoGluon sense. There's no Bayesian optimization, no meta-learning warm-start, no learned model portfolio. The HPO is diagnosis-driven, not algorithmic.

What it *is*: an **autonomous ML-engineering agent**, in the lineage of AIDE and AI-Scientist. The closest relatives are agents that treat ML engineering as a search problem driven by an LLM.

On a maturity axis:

- **Novel on governance.** The Stop hook as structural autonomy, Merkle lineage for experiment identity, two-tier convergence with mandatory divergence, and the whole thing as a declarative skill runtime with no Python engine -- that combination I haven't seen elsewhere.
- **Standard on structure.** Tree search over experiments, structural distrust (no agent approves its own work) -- these are known-good patterns, not inventions.
- **Behind on search and ensembling.** No HPO algorithm, no deep stacking. This is where the real ML-performance headroom is.

Maturity level, calling it honestly: **~2.5**. It works autonomously across six datasets and is approaching AutoML competitiveness, but it's not there on raw search sophistication. The governance is ahead of the modeling. That's a fine place to be -- the governance was the hard part and the modeling gaps are known and additive. For a single-developer project, this sits architecturally alongside what funded labs build. The honest gap is measurement and operator richness: there's no MLE-bench score yet, and there's no web-search-to-seed-SOTA path that pulls current best-known approaches into the search. The bones are right. What's left is breadth.
