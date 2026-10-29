"""Shared sampling, repair, variation, and Pareto helpers."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from app.models.schemas import AggregateScore, CandidateRecord
from app.sim.scoring import rank_key

RepairFn = Callable[[dict[str, float]], dict[str, float]]


class CallBudget:
    def __init__(self, limit: int) -> None:
        self.limit = max(0, int(limit))
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def charge(self, count: int = 1) -> bool:
        if count < 0 or count > self.remaining:
            return False
        self.used += count
        return True


def clip_params(
    params: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> dict[str, float]:
    clipped: dict[str, float] = {}
    for key, (lo, hi) in bounds.items():
        clipped[key] = float(min(hi, max(lo, float(params[key]))))
    return clipped


def repair_gripper(
    params: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> dict[str, float]:
    repaired = clip_params(params, bounds)
    if repaired["pad_width_mm"] > repaired["finger_length_mm"]:
        repaired["pad_width_mm"] = repaired["finger_length_mm"]
        repaired = clip_params(repaired, bounds)
        if repaired["pad_width_mm"] > repaired["finger_length_mm"]:
            repaired["finger_length_mm"] = repaired["pad_width_mm"]
            repaired = clip_params(repaired, bounds)
    return repaired


def repair_energy(
    params: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> dict[str, float]:
    return clip_params(params, bounds)


def sample_params(
    rng: np.random.Generator, bounds: dict[str, tuple[float, float]]
) -> dict[str, float]:
    return {key: float(rng.uniform(lo, hi)) for key, (lo, hi) in bounds.items()}


def merge_bounds(
    base: dict[str, tuple[float, float]],
    region: dict[str, tuple[float, float]] | None,
) -> dict[str, tuple[float, float]]:
    merged = dict(base)
    if not region:
        return merged
    for key, pair in region.items():
        if key not in merged:
            continue
        lo = max(merged[key][0], float(pair[0]))
        hi = min(merged[key][1], float(pair[1]))
        if lo < hi:
            merged[key] = (lo, hi)
    return merged


def crossover(
    left: dict[str, float], right: dict[str, float], rng: np.random.Generator
) -> dict[str, float]:
    child: dict[str, float] = {}
    for key in left:
        weight = float(rng.random())
        child[key] = weight * float(left[key]) + (1.0 - weight) * float(right[key])
    return child


def mutate(
    params: dict[str, float],
    rng: np.random.Generator,
    bounds: dict[str, tuple[float, float]],
    bias: dict[str, float] | None = None,
    probability: float = 0.45,
) -> tuple[dict[str, float], list[str]]:
    changed: list[str] = []
    updated = dict(params)
    bias = bias or {}
    for key, (lo, hi) in bounds.items():
        span = hi - lo
        if float(rng.random()) < probability:
            shift = float(bias.get(key, 0.0)) * span
            updated[key] = float(updated[key]) + float(rng.normal(shift, 0.12 * span))
            changed.append(key)
    return updated, changed


def tournament(
    population: list[CandidateRecord],
    rng: np.random.Generator,
    select_scores: dict[str, AggregateScore],
    k: int = 3,
) -> CandidateRecord:
    size = min(k, len(population))
    picks = rng.choice(len(population), size=size, replace=False)
    winner = population[int(picks[0])]
    for index in picks[1:]:
        challenger = population[int(index)]
        if rank_key(select_scores[challenger.id]) > rank_key(select_scores[winner.id]):
            winner = challenger
    return winner


def pareto_front(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    """Maximise success and worst margin, minimise material."""
    front: list[CandidateRecord] = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other.id == candidate.id:
                continue
            if _dominates(other.score, candidate.score):
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def _dominates(left: AggregateScore, right: AggregateScore) -> bool:
    better_or_equal = (
        left.success_rate >= right.success_rate - 1e-12
        and left.worst_margin_n >= right.worst_margin_n - 1e-9
        and left.material_proxy <= right.material_proxy + 1e-9
    )
    strictly = (
        left.success_rate > right.success_rate + 1e-12
        or left.worst_margin_n > right.worst_margin_n + 1e-9
        or left.material_proxy < right.material_proxy - 1e-9
    )
    return better_or_equal and strictly


def population_size(design_budget: int, scenario_count: int, target_generations: int = 4) -> int:
    if scenario_count <= 0 or design_budget < scenario_count:
        return 0
    affordable = design_budget // scenario_count
    desired = max(1, design_budget // (scenario_count * target_generations))
    if affordable >= 8 and desired < 4:
        desired = 4
    return max(1, min(12, desired, affordable))
