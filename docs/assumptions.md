# Surrogate assumptions

This is not a certified mechanical simulation. It is a fast, deterministic scoring model so search results can be reproduced.

## Gripper, version gripper-2d-1.0.0

Internal arithmetic uses SI. Public fields keep the units in their names.

```
g = 9.81 m/s^2
required_force_n = safety_factor * hypot(mass_kg * g, lateral_disturbance_n)
engagement = min(1, pad_width_mm / max(8 mm, 0.25 * object_width_mm))
friction_raw_n = 2 * friction * actuator_force_n * engagement
k_tip_n_per_m = stiffness_n_per_mm * 1000 * (0.040 / finger_length_m)^3
deflection_m = actuator_force_n / k_tip_n_per_m
```

Deflection scale is 1 at or below 3 mm, 0 at or above 8 mm, and linear between. Friction capacity is the raw friction times that scale. Margin is capacity minus required force.

Geometry fails when the object is wider than the jaw, or when finger length is under 0.35 times object width. A case is feasible only when geometry holds, margin is non-negative, deflection scale is positive, and friction is positive.

```
material_proxy = 2 * (finger_length_mm / 10) * (pad_width_mm / 10) * sqrt(stiffness_n_per_mm)
```

Fitness is `100 * success + 0.5 * mean(margin capped to ±20 N) - 0.02 * material - 0.05 * mean deflection`. The cap stops a huge actuator from dominating the scalar.

Every result carries `simulator_version` and a hash of this equation block. The hash changes when the equations change.

Omitted on purpose: impact, rolling, torsion, pad compliance, actuator dynamics, and any 3D contact.

The adversary stays inside the training envelope. Its first sample each round is a hard corner of that envelope: high mass, low friction, and a large disturbance. The rest of the round is uniform. A design that survives the corner is not archived as a failure.

## Energy, version energy-toy-1.0.0

A 24-step educational balance. It is not a grid, market, or inverter model.

Daylight is `max(0, sin(pi * (hour - 5) / 14))`. Demand follows a sine shape between base and peak, plus an evening bump on hours 17 through 21. Charge efficiency is 0.95. Discharge is limited by the discharge rating and the state of charge. The battery starts half full.

A day is feasible when unmet energy is at most 2% of demand. `material_proxy` stores `900 * solar_kw + 350 * storage_kwh + 40 * discharge_kw`. Margin stores negative unmet kWh.

## Trust boundary

The planner may return a hypothesis, a region inside the bounds, and an action from a fixed allowlist. Application code clamps the region, rejects unknown actions, and discards any code, shell, or path fields. Nothing returned by the model is executed. Scores come only from the simulators above.
