"""Random and evolutionary baselines share a call budget and stay replayable."""

from __future__ import annotations

import numpy as np
from app.core.config import Settings
from app.models.schemas import RunConfig
from app.orchestration.run import execute_run
from app.search.baselines import run_evolutionary_search, run_random_search
from app.search.space import CallBudget, repair_gripper
from app.sim.bounds import GRIPPER_DESIGN_ABSOLUTE
from app.sim.gripper import design_from_params, evaluate, scenario_from_params
from app.sim.scenarios import generate_gripper
from app.sim.scoring import aggregate_gripper, rank_key


def _eval(params, scenarios, design_id):
    design = design_from_params(params, design_id)
    return [
        evaluate(design, scenario_from_params(scenario, str(scenario.get("id", ""))))
        for scenario in scenarios
    ]


def _repair(params):
    return repair_gripper(params, GRIPPER_DESIGN_ABSOLUTE)


def test_search_replay_is_exact() -> None:
    core = generate_gripper(5, 6, holdout=False)
    first = run_evolutionary_search(
        method="evolutionary",
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        region=None,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(240),
        rng=np.random.default_rng(5),
    )
    second = run_evolutionary_search(
        method="evolutionary",
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        region=None,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(240),
        rng=np.random.default_rng(5),
    )
    assert [item.model_dump() for item in first.candidates] == [
        item.model_dump() for item in second.candidates
    ]
    assert first.simulator_calls == second.simulator_calls


def test_methods_respect_the_call_budget() -> None:
    core = generate_gripper(9, 4, holdout=False)
    limit = 160
    random_output = run_random_search(
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(limit),
        rng=np.random.default_rng(9),
    )
    evolutionary = run_evolutionary_search(
        method="evolutionary",
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        region=None,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(limit),
        rng=np.random.default_rng(9),
    )
    assert random_output.simulator_calls <= limit
    assert evolutionary.simulator_calls <= limit
    assert random_output.simulator_calls >= limit - len(core)
    assert evolutionary.design_evaluations >= 4
    assert evolutionary.history
    assert any(record.parent_ids for record in evolutionary.candidates)
    assert any(record.is_pareto for record in evolutionary.candidates)


def test_evolution_improves_on_the_random_baseline_for_the_benchmark_seed() -> None:
    core = generate_gripper(11, 6, holdout=False)
    limit = 360
    random_output = run_random_search(
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(limit),
        rng=np.random.default_rng(11),
    )
    evolutionary = run_evolutionary_search(
        method="evolutionary",
        bounds=GRIPPER_DESIGN_ABSOLUTE,
        region=None,
        core_scenarios=core,
        eval_fn=_eval,
        aggregate_fn=aggregate_gripper,
        repair=_repair,
        budget=CallBudget(limit),
        rng=np.random.default_rng(11),
    )
    random_best = max(random_output.candidates, key=lambda record: rank_key(record.score))
    evolved_best = max(evolutionary.candidates, key=lambda record: rank_key(record.score))
    assert rank_key(evolved_best.score) >= rank_key(random_best.score)


def test_end_to_end_loop_is_replayable_without_a_model() -> None:
    settings = Settings(enable_meta=False, model_api_key="", database_url="sqlite://")
    config = RunConfig(
        domain="gripper_2d",
        seed=21,
        budget={"total_simulator_calls": 240, "adversarial_fraction": 0.2, "playback_ms": 0},
        scenarios={"train_count": 4, "holdout_count": 6},
        model_provider="mock",
    )
    first, first_candidates, first_failures = execute_run(config, settings, "run-a")
    second, second_candidates, _failures = execute_run(config, settings, "run-b")
    assert first.holdout_fingerprint == second.holdout_fingerprint
    assert [row.model_dump() for row in first.holdout if row.preregistered] == [
        row.model_dump() for row in second.holdout if row.preregistered
    ]
    assert first.total_search_calls <= config.budget.total_simulator_calls
    assert {item.method for item in first.methods} == {"random", "evolutionary", "adversarial"}
    seeded = [
        record
        for record in first_candidates
        if record.method == "adversarial" and record.generation == 0 and record.origin == "planner_region"
    ]
    assert seeded
    assert all(record.parameters["actuator_force_n"] >= 42.5 - 1e-6 for record in seeded)
    assert first_failures
    assert any(event.kind == "critique" for event in first.provenance)
    assert any(event.kind == "validated_action" for event in first.provenance)
    assert any(not event.payload.get("rejected_code", False) for event in first.provenance)
    assert len(first_candidates) == len(second_candidates)
    assert first_failures or first.failure_count == 0
