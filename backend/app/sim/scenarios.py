"""Seeded scenario generators. Holdout uses a distant seed and a shifted envelope."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
from scipy.stats import qmc

from app.sim.bounds import (
    ENERGY_HOLDOUT_ENVELOPE,
    ENERGY_TRAIN_ENVELOPE,
    GRIPPER_HOLDOUT_ENVELOPE,
    GRIPPER_TRAIN_ENVELOPE,
)

HOLDOUT_SEED_OFFSET = 900_000


def fingerprint(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def latin_rows(
    seed: int, count: int, bounds: dict[str, tuple[float, float]]
) -> list[dict[str, float]]:
    keys = list(bounds)
    sampler = qmc.LatinHypercube(d=len(keys), seed=seed)
    unit = sampler.random(count)
    rows: list[dict[str, float]] = []
    for i in range(count):
        row: dict[str, float] = {}
        for j, key in enumerate(keys):
            lo, hi = bounds[key]
            row[key] = float(lo + float(unit[i, j]) * (hi - lo))
        rows.append(row)
    return rows


def _repair_energy(
    row: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> dict[str, float]:
    repaired = dict(row)
    if repaired["demand_peak_kw"] < repaired["demand_base_kw"]:
        repaired["demand_peak_kw"] = repaired["demand_base_kw"]
    lo, hi = bounds["demand_peak_kw"]
    repaired["demand_peak_kw"] = float(min(hi, max(lo, repaired["demand_peak_kw"])))
    return repaired


def generate_gripper(seed: int, count: int, *, holdout: bool) -> list[dict[str, Any]]:
    envelope = GRIPPER_HOLDOUT_ENVELOPE if holdout else GRIPPER_TRAIN_ENVELOPE
    draw_seed = seed + HOLDOUT_SEED_OFFSET if holdout else seed + 1_000
    rows = latin_rows(draw_seed, count, envelope)
    labelled: list[dict[str, Any]] = []
    prefix = "holdout" if holdout else "train"
    for index, row in enumerate(rows):
        item: dict[str, Any] = dict(row)
        item["id"] = f"{prefix}-{index:03d}"
        labelled.append(item)
    return labelled


def generate_energy(seed: int, count: int, *, holdout: bool) -> list[dict[str, Any]]:
    envelope = ENERGY_HOLDOUT_ENVELOPE if holdout else ENERGY_TRAIN_ENVELOPE
    draw_seed = seed + HOLDOUT_SEED_OFFSET if holdout else seed + 2_000
    rows = latin_rows(draw_seed, count, envelope)
    labelled: list[dict[str, Any]] = []
    prefix = "holdout" if holdout else "train"
    for index, row in enumerate(rows):
        item: dict[str, Any] = dict(_repair_energy(row, envelope))
        item["id"] = f"{prefix}-{index:03d}"
        labelled.append(item)
    return labelled


def sample_uniform(
    rng: np.random.Generator,
    bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    return {key: float(rng.uniform(lo, hi)) for key, (lo, hi) in bounds.items()}


# Five in-envelope failures with different physical causes. Numbers are designs
# and scenarios; the evaluator produces the measured reasons.
FAILURE_GALLERY: list[dict[str, Any]] = [
    {
        "name": "low-friction slip",
        "design": {
            "jaw_opening_mm": 70.0,
            "finger_length_mm": 45.0,
            "pad_width_mm": 12.0,
            "stiffness_n_per_mm": 30.0,
            "actuator_force_n": 8.0,
        },
        "scenario": {
            "object_mass_kg": 1.4,
            "object_width_mm": 40.0,
            "friction": 0.16,
            "lateral_disturbance_n": 7.5,
            "safety_factor": 1.9,
            "id": "gallery-slip",
        },
        "expect": "friction capacity is below the required holding force",
    },
    {
        "name": "object does not fit",
        "design": {
            "jaw_opening_mm": 40.0,
            "finger_length_mm": 50.0,
            "pad_width_mm": 16.0,
            "stiffness_n_per_mm": 25.0,
            "actuator_force_n": 40.0,
        },
        "scenario": {
            "object_mass_kg": 0.3,
            "object_width_mm": 75.0,
            "friction": 0.6,
            "lateral_disturbance_n": 1.0,
            "safety_factor": 1.3,
            "id": "gallery-fit",
        },
        "expect": "object wider than jaw opening",
    },
    {
        "name": "soft finger loses contact",
        "design": {
            "jaw_opening_mm": 60.0,
            "finger_length_mm": 80.0,
            "pad_width_mm": 18.0,
            "stiffness_n_per_mm": 1.0,
            "actuator_force_n": 50.0,
        },
        "scenario": {
            "object_mass_kg": 0.2,
            "object_width_mm": 30.0,
            "friction": 0.7,
            "lateral_disturbance_n": 0.5,
            "safety_factor": 1.2,
            "id": "gallery-deflection",
        },
        "expect": "deflection exceeds hard limit",
    },
    {
        "name": "finger too short",
        "design": {
            "jaw_opening_mm": 85.0,
            "finger_length_mm": 20.0,
            "pad_width_mm": 8.0,
            "stiffness_n_per_mm": 20.0,
            "actuator_force_n": 35.0,
        },
        "scenario": {
            "object_mass_kg": 0.4,
            "object_width_mm": 70.0,
            "friction": 0.55,
            "lateral_disturbance_n": 1.0,
            "safety_factor": 1.3,
            "id": "gallery-short",
        },
        "expect": "finger too short for object width",
    },
    {
        "name": "narrow pad on a heavy part",
        "design": {
            "jaw_opening_mm": 70.0,
            "finger_length_mm": 40.0,
            "pad_width_mm": 5.0,
            "stiffness_n_per_mm": 30.0,
            "actuator_force_n": 15.0,
        },
        "scenario": {
            "object_mass_kg": 1.2,
            "object_width_mm": 50.0,
            "friction": 0.2,
            "lateral_disturbance_n": 4.0,
            "safety_factor": 1.8,
            "id": "gallery-pad",
        },
        "expect": "narrow pad reduces contact engagement",
    },
]
