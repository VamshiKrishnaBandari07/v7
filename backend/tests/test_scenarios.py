"""Scenario generators, the failure gallery, and the bounded adversary."""

from __future__ import annotations

import numpy as np
from app.models.schemas import DesignConfig, Scenario
from app.search.adversary import adversarial_search, attack_gripper
from app.search.space import CallBudget
from app.sim.bounds import GRIPPER_TRAIN_ENVELOPE
from app.sim.gripper import evaluate, explain, scenario_from_params, validate_scenario
from app.sim.scenarios import FAILURE_GALLERY, fingerprint, generate_gripper


def test_train_sample_is_seeded() -> None:
    first = generate_gripper(42, 12, holdout=False)
    second = generate_gripper(42, 12, holdout=False)
    assert first == second
    assert len(first) == 12


def test_holdout_uses_a_different_draw_than_train() -> None:
    train = generate_gripper(42, 10, holdout=False)
    holdout = generate_gripper(42, 10, holdout=True)
    assert fingerprint(train) != fingerprint(holdout)
    assert train[0]["id"].startswith("train")
    assert holdout[0]["id"].startswith("holdout")


def test_gallery_has_five_distinct_in_envelope_failures() -> None:
    reasons = set()
    for case in FAILURE_GALLERY:
        design = DesignConfig(**case["design"])
        scenario = Scenario(**case["scenario"])
        assert not validate_scenario(scenario, GRIPPER_TRAIN_ENVELOPE)
        result = evaluate(design, scenario)
        assert result.feasible is False
        blob = " ".join(result.reasons)
        assert case["expect"] in blob
        reasons.add(case["expect"])
        text = explain(design, scenario, result)
        assert case["expect"] in text
    assert len(FAILURE_GALLERY) == 5
    assert len(reasons) == 5


def test_adversary_stays_inside_the_envelope_and_hurts_a_weak_design() -> None:
    design = {
        "jaw_opening_mm": 70.0,
        "finger_length_mm": 40.0,
        "pad_width_mm": 12.0,
        "stiffness_n_per_mm": 30.0,
        "actuator_force_n": 6.0,
    }
    mild = {
        "object_mass_kg": 0.2,
        "object_width_mm": 30.0,
        "friction": 0.6,
        "lateral_disturbance_n": 0.0,
        "safety_factor": 1.2,
        "id": "mild",
    }
    mild_result = evaluate(DesignConfig(**design), Scenario(**mild))
    failure = attack_gripper(
        design_params=design,
        design_id="weak",
        method="adversarial",
        generation=0,
        envelope=GRIPPER_TRAIN_ENVELOPE,
        stress=None,
        rng=np.random.default_rng(1),
        trials=40,
        budget=CallBudget(40),
    )
    assert failure is not None
    assert failure.margin_n < mild_result.margin_n
    scenario = Scenario(
        **{key: failure.scenario[key] for key in mild if key != "id"},
        id=str(failure.scenario["id"]),
    )
    assert validate_scenario(scenario, GRIPPER_TRAIN_ENVELOPE) == []


def test_adversary_rejects_out_of_envelope_samples_without_charging() -> None:
    seen: list[dict] = []
    calls = {"n": 0}

    def sample() -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "object_mass_kg": 9.0,
                "object_width_mm": 30.0,
                "friction": 0.4,
                "lateral_disturbance_n": 0.0,
                "safety_factor": 1.2,
                "id": "illegal",
            }
        return {
            "object_mass_kg": 1.4,
            "object_width_mm": 40.0,
            "friction": 0.15,
            "lateral_disturbance_n": 8.0,
            "safety_factor": 2.0,
            "id": "legal-hard",
        }

    def validate(row: dict) -> list[str]:
        return validate_scenario(scenario_from_params(row), GRIPPER_TRAIN_ENVELOPE)

    def evaluate_one(row: dict):
        seen.append(row)
        design = DesignConfig(
            jaw_opening_mm=70,
            finger_length_mm=40,
            pad_width_mm=12,
            stiffness_n_per_mm=30,
            actuator_force_n=8,
        )
        return evaluate(design, scenario_from_params(row, str(row["id"])))

    budget = CallBudget(5)
    failure = adversarial_search(
        design_params={"actuator_force_n": 8},
        design_id="d",
        method="adversarial",
        generation=0,
        sample_scenario=sample,
        validate=validate,
        evaluate_one=evaluate_one,
        explain=lambda row, result: "slip",
        rng=np.random.default_rng(0),
        trials=2,
        budget=budget,
    )
    assert failure is not None
    assert failure.scenario["id"] == "legal-hard"
    assert budget.used == 1
