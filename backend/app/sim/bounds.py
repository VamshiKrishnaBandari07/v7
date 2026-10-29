"""Declared numeric envelopes. User bounds may shrink these, never expand them."""

from __future__ import annotations

GRIPPER_DESIGN_ABSOLUTE: dict[str, tuple[float, float]] = {
    "jaw_opening_mm": (25.0, 90.0),
    "finger_length_mm": (20.0, 80.0),
    "pad_width_mm": (5.0, 30.0),
    "stiffness_n_per_mm": (1.0, 40.0),
    "actuator_force_n": (5.0, 80.0),
}

# Adversary and training scenarios stay inside this envelope.
GRIPPER_TRAIN_ENVELOPE: dict[str, tuple[float, float]] = {
    "object_mass_kg": (0.05, 1.5),
    "object_width_mm": (20.0, 80.0),
    "friction": (0.15, 0.80),
    "lateral_disturbance_n": (0.0, 8.0),
    "safety_factor": (1.2, 2.0),
}

# Disjoint seed plus shifted stress. Not used while choosing designs.
GRIPPER_HOLDOUT_ENVELOPE: dict[str, tuple[float, float]] = {
    "object_mass_kg": (0.05, 2.0),
    "object_width_mm": (18.0, 88.0),
    "friction": (0.08, 0.90),
    "lateral_disturbance_n": (0.0, 12.0),
    "safety_factor": (1.2, 2.5),
}

ENERGY_DESIGN_ABSOLUTE: dict[str, tuple[float, float]] = {
    "solar_kw": (0.5, 8.0),
    "storage_kwh": (0.5, 20.0),
    "discharge_kw": (0.2, 5.0),
}

ENERGY_TRAIN_ENVELOPE: dict[str, tuple[float, float]] = {
    "demand_base_kw": (0.4, 1.2),
    "demand_peak_kw": (1.0, 3.0),
    "cloud_factor": (0.45, 1.0),
    "evening_bump_kw": (0.0, 0.8),
}

ENERGY_HOLDOUT_ENVELOPE: dict[str, tuple[float, float]] = {
    "demand_base_kw": (0.3, 1.6),
    "demand_peak_kw": (0.8, 3.6),
    "cloud_factor": (0.25, 1.0),
    "evening_bump_kw": (0.0, 1.2),
}

GRIPPER_ACTIONS: tuple[str, ...] = (
    "bias_higher_force",
    "bias_wider_pads",
    "bias_stiffer",
    "bias_longer_fingers",
    "bias_wider_jaw",
    "reduce_material",
    "stress_low_friction",
    "stress_high_load",
)

ENERGY_ACTIONS: tuple[str, ...] = (
    "bias_more_solar",
    "bias_more_storage",
    "bias_more_discharge",
    "reduce_cost",
    "stress_low_sun",
    "stress_high_demand",
)
