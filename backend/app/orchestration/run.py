"""Run a seeded experiment. The holdout set is fingerprinted before any design is scored on it."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from app.agents.planner import allowlist_for, bias_for, build_planner, stress_name
from app.core.config import ROOT, Settings
from app.models.schemas import (
    CandidateRecord,
    FailureRecord,
    HoldoutScore,
    MethodReport,
    ParetoPoint,
    ProvenanceEvent,
    Report,
    RunConfig,
)
from app.search.adversary import attack_energy, attack_gripper
from app.search.baselines import SearchOutput, run_evolutionary_search, run_random_search
from app.search.space import CallBudget, repair_energy, repair_gripper
from app.sim import energy as energy_sim
from app.sim import gripper as gripper_sim
from app.sim.bounds import (
    ENERGY_DESIGN_ABSOLUTE,
    ENERGY_HOLDOUT_ENVELOPE,
    ENERGY_TRAIN_ENVELOPE,
    GRIPPER_DESIGN_ABSOLUTE,
    GRIPPER_HOLDOUT_ENVELOPE,
    GRIPPER_TRAIN_ENVELOPE,
)
from app.sim.scenarios import fingerprint, generate_energy, generate_gripper
from app.sim.scoring import aggregate_energy, aggregate_gripper, rank_key

ProgressFn = Callable[..., None]
CancelFn = Callable[[], bool]


class RunCancelled(Exception):
    pass


GRIPPER_LIMITATIONS = [
    "The gripper score is an analytic surrogate, not a certified mechanical or contact simulation.",
    "The model uses Coulomb friction at two pads, a quasi-static cantilever, and no impact, torsion, or 3D geometry.",
    "Train-core metrics use a fixed seeded slice. Finalists are chosen on that slice before holdout scores exist.",
    "The adversary may only propose scenarios inside the training envelope. That is not evidence outside the envelope.",
    "Planner text is a hypothesis. Only the simulator assigns scores, and generated code is never executed.",
]

ENERGY_LIMITATIONS = [
    "The energy score is a 24-step educational balance, not a grid, market, or inverter model.",
    "Demand and solar shapes are synthetic. A feasible day means unmet energy is within 2 percent of demand.",
    "Finalists are frozen on the training days before the shifted holdout weather is scored.",
    "The weather adversary stays inside the declared envelope.",
    "Planner text is a hypothesis. Only the simulator assigns scores, and generated code is never executed.",
]


def current_git_sha() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted"
    return sha or "uncommitted"


def split_budget(total: int) -> dict[str, int]:
    base = total // 3
    remainder = total - (base * 3)
    return {
        "random": base,
        "evolutionary": base,
        "adversarial": base + remainder,
    }


def _pareto_point(record: CandidateRecord) -> ParetoPoint:
    return ParetoPoint(
        id=record.id,
        method=record.method,
        success_rate=record.score.success_rate,
        material_proxy=record.score.material_proxy,
        worst_margin_n=record.score.worst_margin_n,
        fitness=record.score.fitness,
        parameters=dict(record.parameters),
        preregistered=record.preregistered,
    )


def _freeze_finalists(output: SearchOutput) -> list[CandidateRecord]:
    if not output.candidates:
        return []
    primary = max(output.candidates, key=lambda record: rank_key(record.score))
    primary.preregistered = True
    primary.is_finalist = True
    chosen = [primary]
    for record in output.candidates:
        if record.is_pareto and record.id not in {item.id for item in chosen} and len(chosen) < 3:
            record.is_finalist = True
            chosen.append(record)
    return chosen


def execute_run(
    config: RunConfig,
    settings: Settings,
    run_id: str,
    on_progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> tuple[Report, list[CandidateRecord], list[FailureRecord]]:
    playback = config.budget.playback_ms / 1000.0
    search_calls = 0
    best_score: float | None = None
    best_success: float | None = None
    events: list[ProvenanceEvent] = []
    sequence = 0

    def event(kind: str, summary: str, payload: dict[str, Any] | None = None) -> None:
        nonlocal sequence
        sequence += 1
        events.append(
            ProvenanceEvent(
                id=f"prov-{sequence:03d}",
                kind=kind,
                summary=summary,
                payload=payload or {},
            )
        )

    def tick(phase: str, message: str, method: str | None = None) -> None:
        if should_cancel and should_cancel():
            raise RunCancelled()
        if playback:
            time.sleep(playback)
        if on_progress:
            on_progress(
                {
                    "phase": phase,
                    "message": message,
                    "simulator_calls": search_calls,
                    "budget": config.budget.total_simulator_calls,
                    "best_score": best_score,
                    "best_success_rate": best_success,
                    "method": method,
                }
            )
        event("phase", f"{phase}: {message}", {"phase": phase, "method": method})

    domain = config.domain
    if domain == "gripper_2d":
        absolute = GRIPPER_DESIGN_ABSOLUTE
        train_envelope = GRIPPER_TRAIN_ENVELOPE
        holdout_envelope = GRIPPER_HOLDOUT_ENVELOPE
        version = gripper_sim.SIMULATOR_VERSION
        assumptions = gripper_sim.ASSUMPTIONS_HASH
        limitations = list(GRIPPER_LIMITATIONS)
        labels = {
            "success_rate": "Grip success rate",
            "material_proxy": "Material proxy",
            "worst_margin_n": "Worst holding margin (N)",
            "fitness": "Feasibility-first fitness",
        }
        aggregate = aggregate_gripper

        def repair(params: dict[str, float]) -> dict[str, float]:
            return repair_gripper(params, bounds)

        def eval_fn(params: dict[str, float], scenarios: list[dict[str, Any]], design_id: str):
            design = gripper_sim.design_from_params(params, design_id)
            return [
                gripper_sim.evaluate(
                    design,
                    gripper_sim.scenario_from_params(scenario, str(scenario.get("id", ""))),
                )
                for scenario in scenarios
            ]

        def attack(design_params, design_id, generation, stress, rng, trials, adv_budget):
            return attack_gripper(
                design_params=design_params,
                design_id=design_id,
                method="adversarial",
                generation=generation,
                envelope=train_envelope,
                stress=stress,
                rng=rng,
                trials=trials,
                budget=adv_budget,
            )

        train = generate_gripper(config.seed, config.scenarios.train_count, holdout=False)
        holdout = generate_gripper(config.seed, config.scenarios.holdout_count, holdout=True)
    else:
        absolute = ENERGY_DESIGN_ABSOLUTE
        train_envelope = ENERGY_TRAIN_ENVELOPE
        holdout_envelope = ENERGY_HOLDOUT_ENVELOPE
        version = energy_sim.ENERGY_VERSION
        assumptions = energy_sim.ENERGY_ASSUMPTIONS_HASH
        limitations = list(ENERGY_LIMITATIONS)
        labels = {
            "success_rate": "Share of days within 2% unmet energy",
            "material_proxy": "Cost proxy",
            "worst_margin_n": "Worst case as negative unmet kWh",
            "fitness": "Service-first fitness",
        }
        aggregate = aggregate_energy

        def repair(params: dict[str, float]) -> dict[str, float]:
            return repair_energy(params, bounds)

        def eval_fn(params: dict[str, float], scenarios: list[dict[str, Any]], design_id: str):
            return [energy_sim.evaluate(params, scenario, design_id) for scenario in scenarios]

        def attack(design_params, design_id, generation, stress, rng, trials, adv_budget):
            return attack_energy(
                design_params=design_params,
                design_id=design_id,
                method="adversarial",
                generation=generation,
                envelope=train_envelope,
                stress=stress,
                rng=rng,
                trials=trials,
                budget=adv_budget,
            )

        train = generate_energy(config.seed, config.scenarios.train_count, holdout=False)
        holdout = generate_energy(config.seed, config.scenarios.holdout_count, holdout=True)

    bounds: dict[str, tuple[float, float]] = {
        key: (float(absolute[key][0]), float(absolute[key][1])) for key in absolute
    }
    if config.design_bounds:
        bounds = {key: (float(config.design_bounds[key][0]), float(config.design_bounds[key][1])) for key in absolute}

    # Fingerprint both sets before search. Holdout rows are not passed into the optimisers.
    holdout_fingerprint = fingerprint(holdout)
    train_fingerprint_full = fingerprint(train)
    del holdout_envelope

    budgets = split_budget(config.budget.total_simulator_calls)
    adversarial_limit = int(round(budgets["adversarial"] * config.budget.adversarial_fraction))
    adversarial_design_limit = budgets["adversarial"] - adversarial_limit
    smallest_design_budget = min(
        budgets["random"], budgets["evolutionary"], adversarial_design_limit
    )
    core = list(train)
    if smallest_design_budget < len(core):
        core = core[: max(1, smallest_design_budget)]
        event(
            "budget_note",
            "Training scenario count was shortened so every method could score at least one design.",
            {"requested": len(train), "used": len(core)},
        )
    train_fingerprint = fingerprint(core)

    tick("PLANNING", "Requesting a typed experiment plan")
    planner = build_planner(config.model_provider, settings)
    plan = planner.propose(config, bounds)
    event(
        "planner_proposal",
        plan.hypothesis,
        {
            "provider": plan.provider,
            "actions": plan.prioritized_actions,
            "rejected_code": plan.rejected_code,
            "warnings": plan.warnings,
            "regions": [region.model_dump(mode="json") for region in plan.candidate_regions],
            "requested_provider": config.model_provider,
        },
    )
    region = None
    if plan.candidate_regions and plan.candidate_regions[0].bounds:
        region = dict(plan.candidate_regions[0].bounds)

    tick("SIMULATING", f"Scoring baselines on {len(core)} seeded training scenarios")
    rng_random = np.random.default_rng(config.seed)
    rng_evo = np.random.default_rng(config.seed + 1)
    rng_adv = np.random.default_rng(config.seed + 2)
    rng_attack = np.random.default_rng(config.seed + 3)

    random_output = run_random_search(
        bounds=bounds,
        core_scenarios=core,
        eval_fn=eval_fn,
        aggregate_fn=aggregate,
        repair=repair,
        budget=CallBudget(budgets["random"]),
        rng=rng_random,
    )
    search_calls += random_output.simulator_calls
    best_score, best_success = _track_best(best_score, best_success, random_output)

    tick("EVOLVING", "Running evolutionary search without the adversary", method="evolutionary")
    evolutionary_output = run_evolutionary_search(
        method="evolutionary",
        bounds=bounds,
        region=None,
        core_scenarios=core,
        eval_fn=eval_fn,
        aggregate_fn=aggregate,
        repair=repair,
        budget=CallBudget(budgets["evolutionary"]),
        rng=rng_evo,
    )
    search_calls += evolutionary_output.simulator_calls
    best_score, best_success = _track_best(best_score, best_success, evolutionary_output)
    calls_before_adversary = search_calls

    adv_budget = CallBudget(adversarial_limit)
    design_budget = CallBudget(adversarial_design_limit)
    critic_state: dict[str, Any] = {"stress": None, "bias": {}, "before": None, "logged": False}

    def after_generation(generation: int, winner: CandidateRecord, params: dict[str, float]):
        nonlocal search_calls
        if generation == 0 and not critic_state.get("action"):
            critique = planner.critique(
                {
                    "domain": domain,
                    "best_success_rate": winner.score.success_rate,
                    "worst_margin_n": winner.score.worst_margin_n,
                    "material_proxy": winner.score.material_proxy,
                    "generation": generation,
                },
                allowlist_for(domain),
            )
            critic_state["bias"] = bias_for(domain, critique.action)
            critic_state["stress"] = stress_name(critique.action)
            critic_state["before"] = winner.score.success_rate
            critic_state["action"] = critique.action
            event(
                "critique",
                critique.hypothesis,
                {
                    "action": critique.action,
                    "rationale": critique.rationale,
                    "provider": critique.provider,
                    "applied_to_next_generation": True,
                },
            )
        elif generation > 0 and critic_state.get("action") and not critic_state["logged"]:
            before = float(critic_state["before"])
            supported = winner.score.success_rate > before + 1e-9
            event(
                "validated_action",
                (
                    f"Action {critic_state['action']} "
                    f"{'raised' if supported else 'did not raise'} train-core success "
                    f"from {before:.3f} to {winner.score.success_rate:.3f}."
                ),
                {
                    "action": critic_state["action"],
                    "before_success_rate": before,
                    "after_success_rate": winner.score.success_rate,
                    "supported_by_simulation": supported,
                },
            )
            critic_state["logged"] = True
        per_round = max(4, adv_budget.limit // 4 or 1)
        trials = 0 if adv_budget.remaining <= 0 else min(8, adv_budget.remaining, per_round)
        if trials <= 0:
            return []
        found = attack(
            params,
            winner.id,
            generation,
            critic_state.get("stress"),
            rng_attack,
            trials,
            adv_budget,
        )
        search_calls = calls_before_adversary + design_budget.used + adv_budget.used
        tick(
            "EVOLVING",
            f"Adversary spent {adv_budget.used} calls"
            + (f" and queued {critic_state.get('action')}" if critic_state.get("action") else ""),
            method="adversarial",
        )
        return [found] if found else []

    tick(
        "EVOLVING", "Running adversarial co-evolution from the planner region", method="adversarial"
    )
    adversarial_output = run_evolutionary_search(
        method="adversarial",
        bounds=bounds,
        region=region,
        core_scenarios=core,
        eval_fn=eval_fn,
        aggregate_fn=aggregate,
        repair=repair,
        budget=design_budget,
        rng=rng_adv,
        after_generation=after_generation,
        bias_provider=lambda: dict(critic_state.get("bias") or {}),
        extra_calls=lambda: adv_budget.used,
    )
    search_calls = calls_before_adversary + adversarial_output.simulator_calls
    best_score, best_success = _track_best(best_score, best_success, adversarial_output)

    # Finalists are frozen on train-core rank before this block reads holdout.
    tick("VALIDATING", "Scoring frozen finalists on the held-out scenarios")
    if fingerprint(holdout) != holdout_fingerprint:
        raise RuntimeError("holdout set changed after it was fingerprinted")
    validation_calls = 0
    holdout_rows: list[HoldoutScore] = []
    method_reports: list[MethodReport] = []
    candidates: list[CandidateRecord] = []
    failures: list[FailureRecord] = []
    for output in (random_output, evolutionary_output, adversarial_output):
        finalists = _freeze_finalists(output)
        for record in finalists:
            results = eval_fn(record.parameters, holdout, record.id)
            validation_calls += len(results)
            score = aggregate(results, "holdout")
            holdout_rows.append(
                HoldoutScore(
                    method=output.method,
                    design_id=record.id,
                    parameters=dict(record.parameters),
                    success_rate=score.success_rate,
                    mean_margin_n=score.mean_margin_n,
                    worst_margin_n=score.worst_margin_n,
                    material_proxy=score.material_proxy,
                    scenario_count=score.scenario_count,
                    preregistered=record.preregistered,
                    exploratory=not record.preregistered,
                )
            )
        front = [record for record in output.candidates if record.is_pareto][:24]
        primary = next((record for record in finalists if record.preregistered), None)
        method_reports.append(
            MethodReport(
                method=output.method,
                simulator_calls=output.simulator_calls,
                design_evaluations=output.design_evaluations,
                adversarial_calls=adv_budget.used if output.method == "adversarial" else 0,
                history=output.history,
                pareto=[_pareto_point(record) for record in front],
                finalist_ids=[record.id for record in finalists],
                best=_pareto_point(primary) if primary else None,
            )
        )
        candidates.extend(output.candidates)
        failures.extend(output.failures)

    event(
        "holdout",
        "Frozen finalists were scored on scenarios that were not used to choose them.",
        {
            "holdout_fingerprint": holdout_fingerprint,
            "train_fingerprint": train_fingerprint,
            "train_fingerprint_full": train_fingerprint_full,
            "validation_calls": validation_calls,
        },
    )
    tick("COMPLETE", "Experiment finished")
    report = Report(
        run_id=run_id,
        domain=domain,
        seed=config.seed,
        status="COMPLETE",
        simulator_version=version,
        assumptions_hash=assumptions,
        holdout_fingerprint=holdout_fingerprint,
        train_fingerprint=train_fingerprint,
        search_budget_per_method=budgets,
        validation_calls=validation_calls,
        total_search_calls=search_calls,
        methods=method_reports,
        holdout=holdout_rows,
        planner=plan,
        provenance=events,
        limitations=limitations,
        git_sha=current_git_sha(),
        config=config.model_dump(mode="json"),
        failure_count=len(failures),
        train_scenarios=core,
        holdout_scenarios=holdout,
        objective_labels=labels,
    )
    return report, candidates, failures


def _track_best(
    best_score: float | None, best_success: float | None, output: SearchOutput
) -> tuple[float | None, float | None]:
    if not output.history:
        return best_score, best_success
    last = output.history[-1]
    if best_score is None or last.best_fitness > best_score:
        return last.best_fitness, last.best_success_rate
    return best_score, best_success
