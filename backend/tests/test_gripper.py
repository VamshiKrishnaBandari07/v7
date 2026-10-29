"""Deterministic gripper surrogate checks, including the hand-worked example."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
from app.models.schemas import DesignConfig, Scenario
from app.sim.gripper import (
    ASSUMPTIONS_HASH,
    ASSUMPTIONS_TEXT,
    SIMULATOR_VERSION,
    evaluate,
    material_proxy,
    validate_design,
    validate_scenario,
)
from app.sim.scoring import aggregate_gripper

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[2] / "experiments" / "example_manual_check.json").read_text(
        encoding="utf-8"
    )
)


def _design(**overrides: float) -> DesignConfig:
    base = dict(EXAMPLE["design"])
    base.update(overrides)
    return DesignConfig(**base)


def _scenario(**overrides: float) -> Scenario:
    base = dict(EXAMPLE["scenario"])
    base.update(overrides)
    return Scenario(**base)


def test_manual_example_matches_hand_calculation() -> None:
    result = evaluate(_design(), _scenario())
    expected = EXAMPLE["expected"]
    assert result.feasible is True
    assert result.geometry_ok is True
    assert result.engagement == pytest.approx(expected["engagement"])
    assert result.deflection_scale == pytest.approx(expected["deflection_scale"])
    assert result.required_force_n == pytest.approx(expected["required_force_n"])
    assert result.friction_capacity_n == pytest.approx(expected["friction_capacity_n"])
    assert result.margin_n == pytest.approx(expected["margin_n"])
    assert result.deflection_mm == pytest.approx(expected["deflection_mm"])
    assert result.material_proxy == pytest.approx(expected["material_proxy"])


def test_same_inputs_are_identical() -> None:
    first = evaluate(_design(), _scenario())
    second = evaluate(_design(), _scenario())
    assert first.model_dump() == second.model_dump()


def test_version_and_assumptions_hash_are_attached() -> None:
    result = evaluate(_design(), _scenario())
    assert result.simulator_version == SIMULATOR_VERSION
    assert result.assumptions_hash == ASSUMPTIONS_HASH
    assert ASSUMPTIONS_HASH == hashlib.sha256(ASSUMPTIONS_TEXT.encode("utf-8")).hexdigest()[:16]


def test_zero_friction_cannot_hold() -> None:
    result = evaluate(_design(actuator_force_n=40, stiffness_n_per_mm=40), _scenario(friction=0.0))
    assert result.feasible is False
    assert any("zero friction" in reason for reason in result.reasons)


def test_oversized_object_fails_geometry() -> None:
    result = evaluate(_design(jaw_opening_mm=50), _scenario(object_width_mm=70))
    assert result.geometry_ok is False
    assert result.feasible is False
    assert any("wider than jaw" in reason for reason in result.reasons)


def test_object_that_exactly_fits_is_geometrically_ok() -> None:
    result = evaluate(
        _design(
            jaw_opening_mm=50,
            finger_length_mm=40,
            pad_width_mm=15,
            stiffness_n_per_mm=30,
            actuator_force_n=40,
        ),
        _scenario(
            object_width_mm=50,
            object_mass_kg=0.2,
            friction=0.5,
            lateral_disturbance_n=0,
            safety_factor=1.2,
        ),
    )
    assert result.geometry_ok is True
    assert result.feasible is True


def test_width_just_over_opening_fails() -> None:
    result = evaluate(
        _design(jaw_opening_mm=50, finger_length_mm=40, actuator_force_n=40, stiffness_n_per_mm=30),
        _scenario(
            object_width_mm=50.1,
            object_mass_kg=0.2,
            friction=0.5,
            lateral_disturbance_n=0,
            safety_factor=1.2,
        ),
    )
    assert result.geometry_ok is False


def test_excessive_load_fails() -> None:
    result = evaluate(
        _design(
            jaw_opening_mm=80,
            finger_length_mm=40,
            pad_width_mm=20,
            stiffness_n_per_mm=40,
            actuator_force_n=5,
        ),
        _scenario(
            object_mass_kg=1.5,
            object_width_mm=40,
            friction=0.15,
            lateral_disturbance_n=8,
            safety_factor=2.0,
        ),
    )
    assert result.feasible is False
    assert result.margin_n < 0
    assert any("friction capacity" in reason for reason in result.reasons)


def test_invalid_dimensions_rejected() -> None:
    result = evaluate(_design(jaw_opening_mm=10), _scenario())
    assert result.valid_input is False
    assert result.feasible is False
    assert result.margin_n == -1.0e6


def test_negative_pad_rejected() -> None:
    errors = validate_design(_design(pad_width_mm=-1))
    assert errors


def test_non_finite_dimension_rejected() -> None:
    errors = validate_design(_design(actuator_force_n=math.nan))
    assert any("not finite" in error for error in errors)


def test_pad_longer_than_finger_rejected() -> None:
    errors = validate_design(_design(pad_width_mm=25, finger_length_mm=20))
    assert any("pad width exceeds" in error for error in errors)


def test_higher_friction_increases_margin() -> None:
    low = evaluate(_design(stiffness_n_per_mm=40, finger_length_mm=40), _scenario(friction=0.3))
    high = evaluate(_design(stiffness_n_per_mm=40, finger_length_mm=40), _scenario(friction=0.6))
    assert high.margin_n > low.margin_n
    assert aggregate_gripper([high], "one").fitness > aggregate_gripper([low], "one").fitness


def test_higher_mass_decreases_margin() -> None:
    light = evaluate(_design(), _scenario(object_mass_kg=0.2))
    heavy = evaluate(_design(), _scenario(object_mass_kg=1.2))
    assert heavy.margin_n < light.margin_n
    assert heavy.required_force_n > light.required_force_n


def test_higher_force_increases_capacity_when_stiff() -> None:
    weak = evaluate(
        _design(actuator_force_n=10, stiffness_n_per_mm=40, finger_length_mm=40), _scenario()
    )
    strong = evaluate(
        _design(actuator_force_n=40, stiffness_n_per_mm=40, finger_length_mm=40), _scenario()
    )
    assert strong.deflection_scale == 1
    assert weak.deflection_scale == 1
    assert strong.friction_capacity_n > weak.friction_capacity_n


def test_safety_factor_increases_required_force() -> None:
    mild = evaluate(_design(), _scenario(safety_factor=1.2))
    strict = evaluate(_design(), _scenario(safety_factor=2.0))
    assert strict.required_force_n > mild.required_force_n
    assert strict.margin_n < mild.margin_n


def test_lateral_disturbance_increases_required_force() -> None:
    calm = evaluate(_design(), _scenario(lateral_disturbance_n=0))
    disturbed = evaluate(_design(), _scenario(lateral_disturbance_n=8))
    assert disturbed.required_force_n > calm.required_force_n


def test_soft_long_finger_loses_contact() -> None:
    result = evaluate(
        _design(stiffness_n_per_mm=1, finger_length_mm=80, actuator_force_n=80),
        _scenario(object_mass_kg=0.2, object_width_mm=30, friction=0.6),
    )
    assert result.deflection_scale == 0
    assert result.feasible is False
    assert any("deflection exceeds" in reason for reason in result.reasons)


def test_partial_deflection_scales_friction() -> None:
    result = evaluate(
        _design(
            stiffness_n_per_mm=4,
            finger_length_mm=40,
            actuator_force_n=20,
            pad_width_mm=20,
            jaw_opening_mm=60,
        ),
        _scenario(object_width_mm=30, friction=0.5),
    )
    assert result.deflection_mm == pytest.approx(5.0, abs=1e-6)
    assert result.deflection_scale == pytest.approx(0.6)


def test_narrow_pad_cuts_engagement() -> None:
    result = evaluate(_design(pad_width_mm=5), _scenario(object_width_mm=40))
    assert result.engagement == pytest.approx(0.5)
    assert any("narrow pad" in reason for reason in result.reasons)


def test_short_finger_fails_wide_object() -> None:
    result = evaluate(
        _design(finger_length_mm=20, pad_width_mm=8, jaw_opening_mm=85),
        _scenario(object_width_mm=70),
    )
    assert any("too short" in reason for reason in result.reasons)
    assert result.feasible is False


def test_material_grows_with_length_and_stiffness() -> None:
    short = material_proxy(_design(finger_length_mm=30, stiffness_n_per_mm=4))
    long = material_proxy(_design(finger_length_mm=60, stiffness_n_per_mm=4))
    stiff = material_proxy(_design(finger_length_mm=30, stiffness_n_per_mm=16))
    assert long > short
    assert stiff > short


def test_score_breakdown_fields_present() -> None:
    result = evaluate(_design(), _scenario())
    dumped = result.model_dump()
    for key in (
        "friction_capacity_n",
        "required_force_n",
        "margin_n",
        "deflection_mm",
        "material_proxy",
        "engagement",
    ):
        assert key in dumped


def test_scenario_outside_train_envelope_is_rejected_by_validator() -> None:
    errors = validate_scenario(_scenario(friction=0.0))
    assert errors


def test_borderline_positive_margin_stays_feasible() -> None:
    result = evaluate(
        _design(actuator_force_n=20, stiffness_n_per_mm=20, finger_length_mm=40, pad_width_mm=20),
        _scenario(
            object_mass_kg=0.2,
            object_width_mm=30,
            friction=0.4,
            lateral_disturbance_n=0,
            safety_factor=1.2,
        ),
    )
    assert result.margin_n > 0
    assert result.feasible is True
