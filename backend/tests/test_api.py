"""HTTP contract: create a run, read the frozen report, and export it again."""

from __future__ import annotations

from app.core.config import Settings
from app.main import create_app
from app.models.schemas import RunConfig
from app.orchestration.run import RunCancelled, execute_run
from fastapi.testclient import TestClient


def _client(tmp_path) -> TestClient:
    database = tmp_path / "runs.db"
    settings = Settings(
        database_url="sqlite:///" + database.as_posix(),
        enable_meta=False,
        model_api_key="",
    )
    return TestClient(create_app(settings))


def test_health_and_openapi(tmp_path) -> None:
    client = _client(tmp_path)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    schema = client.get("/openapi.json")
    paths = schema.json()["paths"]
    assert "/health" in paths
    assert "/runs" in paths
    assert "/runs/{run_id}/report" in paths


def test_blocking_run_round_trip(tmp_path) -> None:
    client = _client(tmp_path)
    created = client.post(
        "/runs",
        json={
            "domain": "gripper_2d",
            "seed": 18,
            "blocking": True,
            "model_provider": "mock",
            "budget": {"total_simulator_calls": 180, "adversarial_fraction": 0.2, "playback_ms": 0},
            "scenarios": {"train_count": 4, "holdout_count": 4},
        },
    )
    assert created.status_code == 200
    run_id = created.json()["id"]
    assert created.json()["status"] == "COMPLETE"
    report = client.get(f"/runs/{run_id}/report")
    candidates = client.get(f"/runs/{run_id}/candidates")
    failures = client.get(f"/runs/{run_id}/failures")
    again = client.get(f"/runs/{run_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["seed"] == 18
    assert body["assumptions_hash"]
    assert candidates.status_code == 200
    assert candidates.json()
    assert failures.status_code == 200
    assert again.json()["report"]["holdout_fingerprint"] == body["holdout_fingerprint"]

    replay = client.post(
        "/runs",
        json={
            "domain": "gripper_2d",
            "seed": 18,
            "blocking": True,
            "model_provider": "mock",
            "budget": {"total_simulator_calls": 180, "adversarial_fraction": 0.2, "playback_ms": 0},
            "scenarios": {"train_count": 4, "holdout_count": 4},
        },
    )
    replay_report = client.get(f"/runs/{replay.json()['id']}/report").json()
    assert replay_report["holdout"] == body["holdout"]
    assert replay_report["total_search_calls"] == body["total_search_calls"]


def test_unknown_run_is_404(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.get("/runs/missing").status_code == 404


def test_cancel_flag_stops_the_runner() -> None:
    settings = Settings(enable_meta=False, model_api_key="")
    config = RunConfig(
        budget={"total_simulator_calls": 240, "adversarial_fraction": 0.2, "playback_ms": 0},
        scenarios={"train_count": 4, "holdout_count": 4},
    )
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    try:
        execute_run(config, settings, "cancel-me", should_cancel=should_cancel)
    except RunCancelled:
        return
    raise AssertionError("run ignored cancellation")


def test_bounds_outside_absolute_limits_are_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/runs",
        json={
            "design_bounds": {
                "jaw_opening_mm": [10, 90],
                "finger_length_mm": [20, 80],
                "pad_width_mm": [5, 30],
                "stiffness_n_per_mm": [1, 40],
                "actuator_force_n": [5, 80],
            }
        },
    )
    assert response.status_code == 422
