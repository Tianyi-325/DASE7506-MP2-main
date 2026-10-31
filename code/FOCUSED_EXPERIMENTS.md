# Focused optimization round

Scope: the three priorities selected after the broad round. This is a controlled follow-up,
not another broad algorithm sweep. All old frozen scripts/assets remain unchanged.

## Run (Anaconda Prompt, from code/)
conda activate mp1
python -B check_focused_round.py --smoke
python -B run_focused_round.py --stage prepare
python -B run_focused_round.py --stage train
python -B run_focused_round.py --stage freeze
python -B check_focused_round.py
python -B run_focused_round.py --stage evaluate
python -B report_focused_round.py

Python/NumPy/PyTorch versions and the complete grid are pinned in runs/focused_round/plan.json.
No extra dependencies, external data, pretrained weights or model downloads are used.
Inference imports NumPy only.

## Training and evaluation
Initially 35 configurations, plus 8 documented pre-test controls (43 total), two new question-fold partitions (seeds 101 and 307), 3 folds each.
These are repeated training CV diagnostics, not 9,510 independent questions or an untouched
selection assessment. The historical validation set remains development data.
All statistics and knots fit only the corresponding training portion.
Full-batch float64 L-BFGS, max 100 iterations / 140 evaluations, history 12;
gradient tolerance 1e-7, change tolerance 1e-11, strong Wolfe line search.
This is a local optimization budget; multi-positive likelihood need not be globally convex.

All main variants use the SAME normalized score units: divide by that fit's training
within-question centered score standard deviation, then add .25 per additional same-answer
candidate. Native baseline with .25 and normalized no-vote baseline are recorded separately.
All inference statistics, weights and configs count toward the asset cap.

Selection is frozen before test: >=8 mean OOF questions gained per seed, nonnegative gain in
both seeds, >=4/6 positive folds, worst fold >=-6, validation not worse than normalized baseline.
Eligible models rank by mean OOF correctness, worst seed, validation, fewer parameters.
If nobody qualifies, retain the normalized matched baseline. These are predeclared engineering
gates, not a test of statistical significance. Bootstrap intervals are exploratory.

## Supervision ablation
Two representations: base+all styles and full+broad-style removal. For each compare:
- all questions;
- omit all-positive groups, divide loss sum by the ORIGINAL fitting fold size;
- omit all-positive groups, average only retained groups;
- disagreement questions only, original denominator;
- disagreement questions only, retained-group mean;
- disagreement questions only, mask invalid candidate logits, original denominator;
- all questions, mask invalid candidate logits, original denominator;
- disagreement questions only with preprocessing also fit on the disagreement subset.

Except for the final explicit preprocessing variant, all normalization/knots use all fitting
fold inputs to isolate the LOSS change. Loss normalization and L2 scaling are recorded.
Analytical loss+gradient tests verify:
(1) dropping all-positive groups with fixed denominator is an identical objective;
(2) after invalid-answer masking, restricting to disagreement groups with fixed denominator
is also identical. This avoids mistaking altered regularization for new supervision.

## Style ablation
Base = 1,024 embeddings + original 22 scalar features.
Full = embeddings + all 50 broad-round scalar features.
All retained features have identical fold-fitted statistics across the matched comparisons.
Narrow removed block: lengths, answer markers, step/confidence/revision counts, sentence count.
Broad removed block additionally removes number count, question word count, equal/operator counts.
The broader block is not purely cosmetic and can contain useful mathematical signals.

## Additive ablation
Full scalar representation, all styles versus broad removal, L2 .01 versus .02:
- linear only;
- linear + quantile hinge functions (.2/.4/.6/.8 knots);
- linear + six prescribed interactions;
- linear + hinges + interactions.
Every variant includes the SAME retained scalar linear terms. Derived features are centered
and scaled using training-only statistics. This differs from the previous unscaled hinge
prototype and removes the missing-extra-linear-terms confound.

## Combinations
Select best hard-supervision, no-style linear, and additive representatives by training OOF
only (not validation or test). Five prescribed pairs (baseline/hard, baseline/no-style,
baseline/additive, hard/additive, no-style/additive), each at .5/.5 and .75/.25.
One triple weights baseline/hard/additive .5/.25/.25. Same score normalization/vote weight;
the normalized baseline provides the required vote-unit control.

## Compliance and disclosure
Train on CPU, four threads. Measure each frozen deployable variant in one fresh CPU prediction
process plus an independent official scoring process. Keep official data/parser/scorer unchanged.
16 MiB applies to ONE deployable bundle including ALL its members, not the experiment archive.
Local timings do not certify performance on the reference Xeon.
Feature extraction is reused from broad_models.py/reasoning_features.py; additive architecture
is an original lightweight adaptation, not an official GAM/EBM package.

For a standalone official prediction command in Anaconda Prompt, first set thread limits:
```bat
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
```
Select the exact bundle named by runs/focused_round/freeze.json; run predict.py with --method focused_models.py and that --checkpoint, then score_predictions.py in a separate process.

## Pre-test amendment
After the initial 35 configurations, eight orth_hinges/orth_both controls were added (43 main configurations total; 258 CV fits + 43 full fits). No focused-round test scoring had occurred. The original plan and wall time are retained. Duplicate knots are removed per source scalar; affine projection on that source is subtracted and near-zero residual columns removed, then standardized. Binary-only hinges therefore cannot merely duplicate their source linear term. See plan-amendment.json. Original 35 cached fits remain valid; their code paths are unchanged.
