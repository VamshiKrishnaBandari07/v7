"""Aggregate per-scenario rows into a feasibility-first score."""

from __future__ import annotations

from app.models.schemas import AggregateScore, SimulationResult


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def aggregate_gripper(results: list[SimulationResult], basis: str) -> AggregateScore:
    if not results:
        raise ValueError("cannot aggregate an empty result list")
    margins = [row.margin_n for row in results]
    deflections = [row.deflection_mm for row in results]
    capped = [max(-20.0, min(20.0, value)) for value in margins]
    success = sum(1 for row in results if row.feasible) / len(results)
    material = results[0].material_proxy
    return AggregateScore(
        success_rate=success,
        mean_margin_n=_mean(margins),
        worst_margin_n=min(margins),
        material_proxy=material,
        mean_deflection_mm=_mean(deflections),
        fitness=success * 100.0 + 0.5 * _mean(capped) - 0.02 * material - 0.05 * _mean(deflections),
        scenario_count=len(results),
        score_basis=basis,
    )


def aggregate_energy(results: list[SimulationResult], basis: str) -> AggregateScore:
    if not results:
        raise ValueError("cannot aggregate an empty result list")
    margins = [row.margin_n for row in results]
    capped = [max(-30.0, min(0.0, value)) for value in margins]
    success = sum(1 for row in results if row.feasible) / len(results)
    cost = results[0].material_proxy
    return AggregateScore(
        success_rate=success,
        mean_margin_n=_mean(margins),
        worst_margin_n=min(margins),
        material_proxy=cost,
        mean_deflection_mm=0.0,
        fitness=success * 100.0 + 0.4 * _mean(capped) - 0.002 * cost,
        scenario_count=len(results),
        score_basis=basis,
    )


def rank_key(score: AggregateScore) -> tuple[float, float, float, float]:
    """Feasibility first, then worst-case margin, then less material, then fitness."""
    return (score.success_rate, score.worst_margin_n, -score.material_proxy, score.fitness)
