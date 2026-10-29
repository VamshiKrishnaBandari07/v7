"""Toy energy surrogate stays deterministic and fails closed on a dark, heavy day."""

from __future__ import annotations

from app.core.config import Settings
from app.models.schemas import RunConfig
from app.orchestration.run import execute_run
from app.sim.energy import ENERGY_VERSION, evaluate


def _design(**overrides: float) -> dict[str, float]:
    params = {"solar_kw": 4.0, "storage_kwh": 8.0, "discharge_kw": 2.0}
    params.update(overrides)
    return params


def _day(**overrides: float) -> dict[str, float]:
    scenario = {
        "demand_base_kw": 0.6,
        "demand_peak_kw": 1.4,
        "cloud_factor": 0.9,
        "evening_bump_kw": 0.2,
        "id": "day",
    }
    scenario.update(overrides)
    return scenario


def test_clear_day_can_be_served() -> None:
    result = evaluate(_design(), _day())
    assert result.simulator_version == ENERGY_VERSION
    assert result.feasible is True
    assert result.metrics["unmet_kwh"] <= 0.02 * result.metrics["demand_kwh"]


def test_dark_high_demand_day_is_unserved_by_a_small_system() -> None:
    result = evaluate(
        _design(solar_kw=0.5, storage_kwh=0.5, discharge_kw=0.2),
        _day(demand_base_kw=1.2, demand_peak_kw=3.0, cloud_factor=0.45, evening_bump_kw=0.8),
    )
    assert result.feasible is False
    assert result.margin_n < 0
    assert "unmet" in " ".join(result.reasons)


def test_energy_is_deterministic() -> None:
    assert evaluate(_design(), _day()).model_dump() == evaluate(_design(), _day()).model_dump()


def test_more_storage_does_not_lower_the_cost_proxy() -> None:
    small = evaluate(_design(storage_kwh=1), _day())
    large = evaluate(_design(storage_kwh=10), _day())
    assert large.material_proxy > small.material_proxy


def test_invalid_energy_design_is_rejected() -> None:
    result = evaluate(_design(solar_kw=0.1), _day())
    assert result.valid_input is False
    assert result.feasible is False


def test_energy_pipeline_completes_on_the_shared_runner() -> None:
    settings = Settings(enable_meta=False, model_api_key="")
    config = RunConfig(
        domain="energy",
        seed=4,
        budget={"total_simulator_calls": 180, "adversarial_fraction": 0.2, "playback_ms": 0},
        scenarios={"train_count": 4, "holdout_count": 4},
        model_provider="rule",
        objectives=["service", "cost_proxy"],
    )
    report, _candidates, _failures = execute_run(config, settings, "energy-1")
    assert report.domain == "energy"
    assert report.simulator_version == ENERGY_VERSION
    assert report.validation_calls > 0
    assert {row.method for row in report.holdout} == {"random", "evolutionary", "adversarial"}
