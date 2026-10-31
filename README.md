# DASE7506 MP2: Selecting Reliable LLM Reasoning

This individual course project selects a numerically correct answer from four fixed mathematical solutions. See the [course guide](guide/GUIDE.md) for assignment requirements and the [original running instructions](code/README.md) for the supplied tools.

## Final method

**Groupwise Relative Evidence Correction (GREC)** combines a frozen 1070-dimensional joint answer-group backbone with a learned correction from 70 condition, local-verification and cross-candidate evidence features.

| Split | Correct answers | Accuracy |
|---|---:|---:|
| Validation | 751/798 | 94.11% |
| Test | 401/467 | 85.87% |

The implementation identifier is joint_residual_relative_r3. Configuration and weights occupy **22,399 bytes**. Fresh full-test prediction plus independent scoring takes approximately **3.05 seconds** on the local four-thread Intel Core i9-12900H CPU.

## Report and experiment records

- [Final report (PDF)](report/Report.pdf)
- [Checkpoint files](checkpoints/grec/)
- [Checkpoint ZIP](release/grec-checkpoint.zip)
- [Checkpoint manifest and checksums](release/checkpoint-manifest.json)
- [Final-model ablation results](code/runs/final_ablation/ablation-results.json)
- [Evidence experiment report](code/runs/evidence_round/REPORT.md)
- [Experiment summary](code/EXPERIMENT_SUMMARY.md)

## Run the frozen model

Use Python 3.12 and NumPy 2.5.3. From the repository root, run these commands in Anaconda Prompt:

    conda activate mp1
    cd code
    set OMP_NUM_THREADS=4
    set OPENBLAS_NUM_THREADS=4
    set MKL_NUM_THREADS=4
    python -X utf8 -B predict.py --method evidence_models.py --checkpoint ../checkpoints/grec --split test --output runs/GREC-test-predictions.json
    python -X utf8 -B score_predictions.py --split test --predictions runs/GREC-test-predictions.json --output runs/GREC-test-score.json

Inference dependencies are specified in [code/requirements.txt](code/requirements.txt); training additionally uses [code/requirements-vector.txt](code/requirements-vector.txt). The predictor requires its imported project modules and the model bundle. Training caches are not inference assets.

The bundle contains config.json and member0.npz. Asset and source hashes are recorded in [freeze.json](code/runs/evidence_round/freeze.json). The original course data, parser, scorer and release files remain unchanged.

## AI assistance and reuse

OpenAI Codex provided assistance with implementation, experiment design, checks and analysis.
The task, data, parser and scorer are course-provided; GREC reuses earlier
components implemented within this project. Public-method explorations are
not needed to explain GREC are not individually listed here; their records
and attribution remain in the repository. No additional pretrained weights
or training datasets enter GREC, and frozen evaluation makes no LLM/API calls.
Data licenses and Qwen preparation attribution are retained.

## Data attribution

Questions and reference solutions derive from GSM8K. Candidate traces and fixed representations were prepared by the course using Qwen3-0.6B. Retain [LICENSE.txt](code/data/LICENSE.txt) and [NOTICE.txt](code/data/NOTICE.txt) when redistributing the supplied data.

## Delivery checks

The final PDF is available in report/Report.pdf. The standalone checkpoint ZIP and its manifest are available in release/. Clean-environment reproduction, public code/checkpoint links and the final website issue submission still require verification. Experiment records and official scores under code/runs/ remain trackable; rebuildable feature caches and execution logs are ignored.
