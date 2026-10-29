# Gripper experiment contract

Question: within declared bounds, which 2D opposing-jaw designs keep a grip on varied object widths, masses, friction levels, and lateral disturbances, and what material proxy do they spend to do it?

The finished loop must show a proposed design, an objectively scored failure, a redesign, and a holdout score that was not used to choose the finalist.

## Parameters

| Name | Unit | Absolute bounds |
| --- | --- | --- |
| jaw_opening_mm | mm | 25 to 90 |
| finger_length_mm | mm | 20 to 80 |
| pad_width_mm | mm | 5 to 30, and no wider than the finger |
| stiffness_n_per_mm | N/mm at a 40 mm reference length | 1 to 40 |
| actuator_force_n | N | 5 to 80 |

## Scenario inputs

Training envelope, also the only region the adversary may use:

| Name | Unit | Range |
| --- | --- | --- |
| object_mass_kg | kg | 0.05 to 1.5 |
| object_width_mm | mm | 20 to 80 |
| friction | dimensionless | 0.15 to 0.80 |
| lateral_disturbance_n | N | 0 to 8 |
| safety_factor | dimensionless | 1.2 to 2.0 |

Holdout uses seed + 900000 and a shifted envelope: mass to 2.0 kg, width 18 to 88 mm, friction 0.08 to 0.90, disturbance to 12 N, safety factor to 2.5.

## Outputs

Each scenario returns grip feasibility, friction capacity (N), required holding force (N), margin (N), deflection (mm), engagement, and the design material proxy. A run then reports train-core success, worst margin, material, fitness, a Pareto slice, and the same metrics on holdout for the frozen finalist.

## Ranking

Feasibility first, then higher worst-case margin, then lower material proxy, then the scalar fitness. The pre-registered finalist is the best design under that order on the training scenarios. Holdout does not break ties.

## Worked example

`experiments/example_manual_check.json` is the hand-checked case: a 60 mm jaw, 50 mm finger, 15 mm pad, 40 N/mm stiffness, and 30 N actuator, on a 0.5 kg object 40 mm wide with friction 0.5, 2 N disturbance, and safety factor 1.5. Expected margin is 22.054 N and the grasp is feasible. The unit test locks those numbers.

Illustrative run settings live in `experiments/gripper_mvp.json`. They are engineering bounds for this surrogate, not a hardware rating.
