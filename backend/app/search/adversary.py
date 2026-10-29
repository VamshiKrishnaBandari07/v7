"""Bounded stress-case search. Invalid scenarios are rejected before they are scored."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from app.models.schemas import FailureRecord, SimulationResult
from app.search.space import CallBudget
from app.sim import energy as energy_sim
from app.sim import gripper as gripper_sim
from app.sim.scenarios import sample_uniform

ValidateFn = Callable[[dict[str, Any]], list[str]]
EvaluateFn = Callable[[dict[str, Any]], SimulationResult]
SampleFn = Callable[[], dict[str, Any]]
ExplainFn = Callable[[dict[str, Any], SimulationResult], str]


def worse_for_design(new: SimulationResult, old: SimulationResult) -> bool:
    """True when `new` is a harsher valid outcome than `old`."""
    if new.feasible != old.feasible:
        return (not new.feasible) and old.feasible
    return new.margin_n < old.margin_n - 1e-12


def adversarial_search(
    *,
    design_params: dict[str, float],
    design_id: str,
    method: str,
    generation: int,
    sample_scenario: SampleFn,
    validate: ValidateFn,
    evaluate_one: EvaluateFn,
    explain: ExplainFn,
    rng: np.random.Generator,
    trials: int,
    budget: CallBudget,
) -> FailureRecord | None:
    best_result: SimulationResult | None = None
    best_scenario: dict[str, Any] | None = None
    del rng  # sampling closure owns the generator; kept for a stable call signature
    for trial in range(max(0, trials)):
        scenario = sample_scenario()
        if validate(scenario):
            continue
        if not budget.charge(1):
            break
        scenario = dict(scenario)
        scenario.setdefault("id", f"adv-{method}-g{generation}-{trial}")
        result = evaluate_one(scenario)
        if best_result is None or worse_for_design(result, best_result):
            best_result = result
            best_scenario = scenario
    if best_result is None or best_scenario is None:
        return None
    if best_result.feasible and best_result.margin_n >= -1e-9:
        return None
    return FailureRecord(
        id=f"fail-{method}-g{generation}-{design_id}",
        method=method,
        design_id=design_id,
        generation=generation,
        parameters={key: float(value) for key, value in design_params.items()},
        scenario=best_scenario,
        margin_n=best_result.margin_n,
        feasible=best_result.feasible,
        explanation=explain(best_scenario, best_result),
        reasons=list(best_result.reasons),
    )


def _quantile(bounds: dict[str, tuple[float, float]], key: str, quantile: float) -> float:
    lo, hi = bounds[key]
    return float(lo + quantile * (hi - lo))


def _subset(bounds: dict[str, tuple[float, float]], key: str, *, low_fraction: float) -> None:
    lo, hi = bounds[key]
    if low_fraction >= 0:
        bounds[key] = (lo, lo + low_fraction * (hi - lo))
    else:
        fraction = abs(low_fraction)
        bounds[key] = (hi - fraction * (hi - lo), hi)


def gripper_attack_bounds(
    design: dict[str, float],
    envelope: dict[str, tuple[float, float]],
    stress: str | None,
) -> dict[str, tuple[float, float]]:
    bounds = {key: (lo, hi) for key, (lo, hi) in envelope.items()}
    jaw = float(design["jaw_opening_mm"])
    lo, hi = bounds["object_width_mm"]
    if jaw >= lo:
        bounds["object_width_mm"] = (lo, min(hi, jaw))
    if stress == "stress_low_friction":
        _subset(bounds, "friction", low_fraction=0.4)
    elif stress == "stress_high_load":
        _subset(bounds, "object_mass_kg", low_fraction=-0.4)
    return bounds


def energy_attack_bounds(
    envelope: dict[str, tuple[float, float]],
    stress: str | None,
) -> dict[str, tuple[float, float]]:
    bounds = {key: (lo, hi) for key, (lo, hi) in envelope.items()}
    if stress == "stress_low_sun":
        _subset(bounds, "cloud_factor", low_fraction=0.4)
    elif stress == "stress_high_demand":
        _subset(bounds, "demand_peak_kw", low_fraction=-0.4)
        _subset(bounds, "evening_bump_kw", low_fraction=-0.5)
    return bounds


def attack_gripper(
    *,
    design_params: dict[str, float],
    design_id: str,
    method: str,
    generation: int,
    envelope: dict[str, tuple[float, float]],
    stress: str | None,
    rng: np.random.Generator,
    trials: int,
    budget: CallBudget,
) -> FailureRecord | None:
    bounds = gripper_attack_bounds(design_params, envelope, stress)
    counter = {"n": 0}

    def sample() -> dict[str, Any]:
        if counter["n"] == 0:
            row: dict[str, Any] = {
                "object_mass_kg": _quantile(bounds, "object_mass_kg", 0.85),
                "object_width_mm": _quantile(bounds, "object_width_mm", 0.7),
                "friction": _quantile(bounds, "friction", 0.2),
                "lateral_disturbance_n": _quantile(bounds, "lateral_disturbance_n", 0.8),
                "safety_factor": _quantile(bounds, "safety_factor", 0.8),
            }
        else:
            row = dict(sample_uniform(rng, bounds))
        row["id"] = f"adv-{method}-g{generation}-{counter['n']}"
        counter["n"] += 1
        return row

    def validate(row: dict[str, Any]) -> list[str]:
        return gripper_sim.validate_scenario(gripper_sim.scenario_from_params(row), envelope)

    def evaluate_one(row: dict[str, Any]) -> SimulationResult:
        design = gripper_sim.design_from_params(design_params, design_id)
        scenario = gripper_sim.scenario_from_params(row, str(row.get("id", "")))
        return gripper_sim.evaluate(design, scenario)

    def explain(row: dict[str, Any], result: SimulationResult) -> str:
        design = gripper_sim.design_from_params(design_params, design_id)
        scenario = gripper_sim.scenario_from_params(row, str(row.get("id", "")))
        return gripper_sim.explain(design, scenario, result)

    return adversarial_search(
        design_params=design_params,
        design_id=design_id,
        method=method,
        generation=generation,
        sample_scenario=sample,
        validate=validate,
        evaluate_one=evaluate_one,
        explain=explain,
        rng=rng,
        trials=trials,
        budget=budget,
    )


def attack_energy(
    *,
    design_params: dict[str, float],
    design_id: str,
    method: str,
    generation: int,
    envelope: dict[str, tuple[float, float]],
    stress: str | None,
    rng: np.random.Generator,
    trials: int,
    budget: CallBudget,
) -> FailureRecord | None:
    bounds = energy_attack_bounds(envelope, stress)
    counter = {"n": 0}

    def sample() -> dict[str, Any]:
        if counter["n"] == 0:
            row: dict[str, Any] = {
                "demand_base_kw": _quantile(bounds, "demand_base_kw", 0.8),
                "demand_peak_kw": _quantile(bounds, "demand_peak_kw", 0.85),
                "cloud_factor": _quantile(bounds, "cloud_factor", 0.15),
                "evening_bump_kw": _quantile(bounds, "evening_bump_kw", 0.85),
            }
        else:
            row = dict(sample_uniform(rng, bounds))
        if row["demand_peak_kw"] < row["demand_base_kw"]:
            row["demand_peak_kw"] = row["demand_base_kw"]
        lo, hi = bounds["demand_peak_kw"]
        row["demand_peak_kw"] = float(min(hi, max(lo, row["demand_peak_kw"])))
        row["id"] = f"adv-{method}-g{generation}-{counter['n']}"
        counter["n"] += 1
        return row

    def validate(row: dict[str, Any]) -> list[str]:
        return energy_sim.validate_scenario(row, envelope)

    def evaluate_one(row: dict[str, Any]) -> SimulationResult:
        return energy_sim.evaluate(design_params, row, design_id)

    def explain(row: dict[str, Any], result: SimulationResult) -> str:
        return energy_sim.explain(design_params, row, result)

    return adversarial_search(
        design_params=design_params,
        design_id=design_id,
        method=method,
        generation=generation,
        sample_scenario=sample,
        validate=validate,
        evaluate_one=evaluate_one,
        explain=explain,
        rng=rng,
        trials=trials,
        budget=budget,
    )
