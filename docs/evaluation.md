# Holdout evaluation

Pre-registered finalists only. Each method receives the same search-call budget.
The finalist is the best design on the train-core slice. Holdout scores are computed after that choice.
The adversarial arm is also seeded by the deterministic mock planner, so this is not a live Meta model result.

Simulator `gripper-2d-1.0.0`. Seeds [42, 43, 44]. Budget 900 simulator calls split across the three methods. 8 training scenarios per design, 24 holdout scenarios.

| Method | Mean holdout success | Spread | Mean worst margin (N) | Mean material proxy |
| --- | ---: | ---: | ---: | ---: |
| random | 0.736 | 0.071 | -20.39 | 134.6 |
| evolutionary | 0.597 | 0.119 | -22.72 | 63.6 |
| adversarial | 0.847 | 0.020 | -19.30 | 109.9 |

## What this does and does not show

A higher holdout success rate is the claim that matters. Material and worst-case margin are trade-offs, not a second chance to pick the winner.
Three seeds is a small sample. The spread column is the population standard deviation of holdout success, not a confidence interval.
The holdout envelope is shifted, but it is still drawn from the same analytic surrogate, so this is not evidence about a physical gripper.
If the adversarial arm does not lead on holdout success, that negative result stands. Adversarial search spends part of its budget on stress cases, so it evaluates fewer designs.

Machine-readable copy: `experiments/out/ablation.csv`.
