# Broad optimization round

This round implements all 21 previously proposed directions as bounded model experiments,
training comparisons, or evaluation/data audits. It is not an exhaustive hyperparameter search.
All fits use only course training inputs and references; no pretrained weights or external data.

## Commands (Anaconda Prompt, from code/)
conda activate mp1
python -B check_broad_round.py --smoke
python -B run_broad_round.py --stage prepare
python -B run_broad_round.py --stage train
python -B run_broad_round.py --stage freeze
python -B check_broad_round.py
python -B run_broad_round.py --stage evaluate
python -B report_broad_round.py

No dependency installation is needed beyond the existing NumPy and PyTorch environment.
Inference requires NumPy only. See runs/broad_round/plan.json for exact dependency versions.
The attempt to download optional SciPy/sklearn/XGBoost packages failed due to network
connectivity, recorded in dependency-install.log. They were not used or substituted with
incompatible packages from another Python environment.

## Protocol
- Three stratified question folds, seed 2026, 1,585 questions each.
- Each outer training portion has an 85/15 internal split for neural/linear-earlystop
  checkpoint selection. Its preprocessing is independently fitted.
- Other fixed configurations use fixed training budgets. Neural/residual methods start
  from a baseline fitted exclusively on the same fitting subset.
- Full training-set refits use the median epoch selected inside the three training folds.
- All centering/scaling, PCA, spline knots and supervised feature masks are fit locally.
- Paired bootstrap intervals are exploratory and unadjusted for multiple comparisons.
- Promotion requires at least five OOF questions gained, positive gains in at least two
  folds, no fold worse than -5, and at least three validation questions gained.
- Among eligible models, OOF correctness ranks first and validation breaks ties.
  Otherwise retain the matched baseline.
- OOF is used for development, not claimed to be an untouched estimate of a selected
  method. The previously reused validation set also has selection bias.
- Fixed-weight mixtures use model scales measured on that model's training portion.
- Temperature calibration uses distinct answer groups, cross-fitted on base OOF
  predictions. Its second-level folds are not fully nested across base fitting.
  Temperature does not change argmax accuracy.
- Every variant, asset hash, selected method and source hash is frozen before official
  test scoring. No changes or choices are made from test results.

## Implemented methods
External ideas: native depth-3 histogram gradient boosting (BCE), lambda-weighted
pairwise tree boosting, quantile-hinge additive model plus six prescribed interactions,
rank-4 factorization-machine correction, 128 random Fourier features, randomly initialized
character CNN, and within-question supervised contrastive projection.
These are lightweight adaptations, not official XGBoost, LambdaMART, GA2M or EBM packages.
CNN, contrastive and FM versions retain a frozen trained linear baseline and learn a correction.

The compact tree/RFF representation uses 32 fold-local PCA coordinates and 50 engineered
features. Full representation uses 1,024 embeddings and these 50 engineered features.
Matched baseline uses embeddings plus the original 22 text features. Standardized features
are capped at +/-20 in this round. This is recorded as a difference from older implementations.

Training comparisons: frozen-base residual MLP, width 16/32, dropout .2, Adam+explicit L2
versus AdamW, L-BFGS, internal early stopping up to 360 linear epochs, batch 128 versus 512,
EMA, SWA and SAM. Default residual AdamW learning rate .003, decay .01.
Adam+L2 and AdamW are different objectives/updates, not assumed equivalent regularizers.
The multi-positive group likelihood need not be convex; L-BFGS is a convergence diagnostic,
not a guarantee of a global optimum.

Data/feature changes: inverse-stratum question loss weights, training-time invalid-answer
mask, no-style ablation, supervised scalar feature screening from two training halves,
and conservative whole-line arithmetic plus question/answer semantic features.
No official parser, scorer, labels or inputs are modified. Arithmetic synthetic cases test
basic correctness only; they do not establish natural-language verification reliability.

## Sources and reuse
All model implementations are original small adaptations of published ideas.
- Gradient boosting / second-order tree scoring: https://arxiv.org/abs/1603.02754
- Lambda ranking: https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/MSR-TR-2010-82.pdf
- Additive pairwise models: https://yinlou.github.io/papers/lou-kdd13.pdf
- Factorization machines (Rendle, 2010): https://jame-zhang.github.io/assets/algo/Factorization-Machines-Rendle2010.pdf
- Random Fourier features: https://papers.nips.cc/paper_files/paper/2007/hash/013a006f03dbc5392effeb8f18fda755-Abstract.html
- TextCNN architecture (character-level here, no external embeddings): https://arxiv.org/abs/1408.5882
- Supervised contrastive learning (same-question adaptation here): https://arxiv.org/abs/2004.11362
- AdamW: https://arxiv.org/abs/1711.05101
- SWA: https://arxiv.org/abs/1803.05407
- SAM: https://arxiv.org/abs/2010.01412

## Resource interpretation
Each deployable variant must independently fit 16 MiB uncompressed, counting all ensemble
members and preprocessing statistics. The entire experiment archive is not a deployment
bundle. Time is one fresh CPU prediction process plus the independent official scorer,
with four total library threads. Local passing times do not certify the reference Xeon CPU.
The final report records hardware, search costs and every variant.

Additional fixed seeds: PCA/RFF 77; inner splits 900/901/902; half-sample supervised feature screening 2026. Trees and neural initialization 2026.
Validation subgroup analysis: python -B analyze_broad_round.py
