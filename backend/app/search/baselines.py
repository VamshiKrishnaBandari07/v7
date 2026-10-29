"""Random search and evolutionary search under an explicit simulator-call budget."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.models.schemas import (
    AggregateScore,
    CandidateRecord,
    FailureRecord,
    HistoryPoint,
    SimulationResult,
)
from app.search.space import (
    CallBudget,
    crossover,
    merge_bounds,
    mutate,
    pareto_front,
    population_size,
    repair_gripper,
    sample_params,
    tournament,
)
from app.sim.scoring import rank_key

EvalFn = Callable[[dict[str, float], list[dict[str, Any]], str], list[SimulationResult]]
AggFn = Callable[[list[SimulationResult], str], AggregateScore]
Repair = Callable[[dict[str, float]], dict[str, float]]
AfterGeneration = Callable[[int, CandidateRecord, dict[str, float]], list[FailureRecord]]
BiasFn = Callable[[], dict[str, float]]

PREFIX = {"random": "rnd", "evolutionary": "evo", "adversarial": "adv"}


@dataclass
class SearchOutput:
    method: str
    candidates: list[CandidateRecord] = field(default_factory=list)
    history: list[HistoryPoint] = field(default_factory=list)
    failures: list[FailureRecord] = field(default_factory=list)
    simulator_calls: int = 0
    design_evaluations: int = 0


def _score_split(
    results: list[SimulationResult],
    core_count: int,
    aggregate_fn: AggFn,
) -> tuple[AggregateScore, AggregateScore]:
    core_score = aggregate_fn(results[:core_count], "train_core")
    if len(results) == core_count:
        return core_score, core_score
    return core_score, aggregate_fn(results, "train_core_plus_archive")


def _record(
    *,
    method: str,
    generation: int,
    index: int,
    params: dict[str, float],
    parents: list[str],
    origin: str,
    score: AggregateScore,
) -> CandidateRecord:
    prefix = PREFIX.get(method, method[:3])
    return CandidateRecord(
        id=f"{prefix}-g{generation:02d}-{index:02d}",
        method=method,
        generation=generation,
        parent_ids=list(parents),
        origin=origin,
        parameters={key: float(value) for key, value in params.items()},
        score=score,
    )


def _history(generation: int, calls: int, best: CandidateRecord) -> HistoryPoint:
    return HistoryPoint(
        generation=generation,
        simulator_calls=calls,
        best_fitness=best.score.fitness,
        best_success_rate=best.score.success_rate,
        best_material=best.score.material_proxy,
        best_worst_margin=best.score.worst_margin_n,
    )


def run_random_search(
    *,
    bounds: dict[str, tuple[float, float]],
    core_scenarios: list[dict[str, Any]],
    eval_fn: EvalFn,
    aggregate_fn: AggFn,
    repair: Repair,
    budget: CallBudget,
    rng: np.random.Generator,
) -> SearchOutput:
    output = SearchOutput(method="random")
    if not core_scenarios:
        return output
    cost = len(core_scenarios)
    best: CandidateRecord | None = None
    index = 0
    while budget.remaining >= cost and index < 10_000:
        params = repair(sample_params(rng, bounds))
        if not budget.charge(cost):
            break
        design_id = f"rnd-g00-{index:02d}"
        results = eval_fn(params, core_scenarios, design_id)
        score = aggregate_fn(results, "train_core")
        record = _record(
            method="random",
            generation=0,
            index=index,
            params=params,
            parents=[],
            origin="uniform",
            score=score,
        )
        output.candidates.append(record)
        output.design_evaluations += 1
        if best is None or rank_key(score) > rank_key(best.score):
            best = record
        output.history.append(_history(index, budget.used, best))
        index += 1
    output.simulator_calls = budget.used
    _mark_pareto(output.candidates)
    return output


def run_evolutionary_search(
    *,
    method: str,
    bounds: dict[str, tuple[float, float]],
    region: dict[str, tuple[float, float]] | None,
    core_scenarios: list[dict[str, Any]],
    eval_fn: EvalFn,
    aggregate_fn: AggFn,
    repair: Repair,
    budget: CallBudget,
    rng: np.random.Generator,
    after_generation: AfterGeneration | None = None,
    bias_provider: BiasFn | None = None,
    extra_calls: Callable[[], int] | None = None,
    max_generations: int = 8,
) -> SearchOutput:
    output = SearchOutput(method=method)
    if not core_scenarios:
        return output
    pop = population_size(budget.limit, len(core_scenarios))
    if pop < 1:
        return output
    region_slots = max(1, pop // 2) if region else 0
    pending: list[tuple[dict[str, float], list[str], str]] = []
    for index in range(pop):
        use_region = index < region_slots
        sample_bounds = merge_bounds(bounds, region if use_region else None)
        origin0 = "planner_region" if use_region else "uniform"
        pending.append((repair(sample_params(rng, sample_bounds)), [], origin0))

    archive: list[dict[str, Any]] = []
    carried_failures: list[FailureRecord] = []
    for generation in range(max_generations):
        scenarios = list(core_scenarios) + list(archive)
        cost = len(scenarios) * len(pending)
        if cost == 0 or budget.remaining < cost:
            break
        if not budget.charge(cost):
            break
        generation_records: list[CandidateRecord] = []
        select_scores: dict[str, AggregateScore] = {}
        scored_params: dict[str, dict[str, float]] = {}
        for index, (params, parents, origin) in enumerate(pending):
            record_id_preview = f"{PREFIX.get(method, method[:3])}-g{generation:02d}-{index:02d}"
            results = eval_fn(params, scenarios, record_id_preview)
            core_score, select_score = _score_split(results, len(core_scenarios), aggregate_fn)
            record = _record(
                method=method,
                generation=generation,
                index=index,
                params=params,
                parents=parents,
                origin=origin,
                score=core_score,
            )
            generation_records.append(record)
            select_scores[record.id] = select_score
            scored_params[record.id] = dict(params)
        if carried_failures:
            for failure in carried_failures:
                failure.linked_design_ids = [
                    record.id
                    for record in generation_records
                    if failure.design_id in record.parent_ids
                ]
            output.failures.extend(carried_failures)
            carried_failures = []
        output.candidates.extend(generation_records)
        output.design_evaluations += len(generation_records)
        winner = max(generation_records, key=lambda record: rank_key(select_scores[record.id]))
        spent = budget.used + (extra_calls() if extra_calls else 0)
        output.history.append(_history(generation, spent, winner))

        if after_generation is not None:
            weakest = min(generation_records, key=lambda record: rank_key(select_scores[record.id]))
            targets = [winner] if weakest.id == winner.id else [winner, weakest]
            carried_failures = []
            for target in targets:
                carried_failures.extend(after_generation(generation, target, scored_params[target.id]))
            for failure in carried_failures:
                scenario = failure.scenario
                if scenario.get("id") not in {row.get("id") for row in archive}:
                    archive.append(scenario)
            archive = archive[-6:]
        if output.history:
            output.history[-1].simulator_calls = budget.used + (extra_calls() if extra_calls else 0)

        if generation + 1 >= max_generations:
            output.failures.extend(carried_failures)
            break
        bias = bias_provider() if bias_provider else {}
        elite_n = 1 if len(generation_records) < 6 else 2
        ranked = sorted(
            generation_records,
            key=lambda record: rank_key(select_scores[record.id]),
            reverse=True,
        )
        pending = []
        for elite in ranked[:elite_n]:
            pending.append((dict(scored_params[elite.id]), [elite.id], "elite"))
        while len(pending) < len(generation_records):
            first = tournament(generation_records, rng, select_scores)
            second = tournament(generation_records, rng, select_scores)
            child = crossover(scored_params[first.id], scored_params[second.id], rng)
            child, changed = mutate(child, rng, bounds, bias)
            child = repair(child)
            origin = "crossover" if not changed else "crossover+mutation:" + ",".join(changed)
            pending.append((child, [first.id, second.id], origin))
        next_cost = (len(core_scenarios) + len(archive)) * len(pending)
        if budget.remaining < next_cost:
            output.failures.extend(carried_failures)
            break

    output.simulator_calls = budget.used + (extra_calls() if extra_calls else 0)
    _mark_pareto(output.candidates)
    return output


def _mark_pareto(candidates: list[CandidateRecord]) -> None:
    front_ids = {record.id for record in pareto_front(candidates)}
    for record in candidates:
        record.is_pareto = record.id in front_ids


def gripper_repair_factory(
    bounds: dict[str, tuple[float, float]],
) -> Repair:
    def repair(params: dict[str, float]) -> dict[str, float]:
        return repair_gripper(params, bounds)

    return repair
