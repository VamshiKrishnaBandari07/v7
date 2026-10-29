"""Planner parsing never executes model text, and the HTTP client retries."""

from __future__ import annotations

import httpx
import pytest
from app.agents.meta_client import MetaClient, MetaClientError, extract_output_text
from app.agents.planner import MockPlanner, build_planner, parse_plan_text
from app.core.config import Settings
from app.models.schemas import RunConfig
from app.sim.bounds import GRIPPER_ACTIONS, GRIPPER_DESIGN_ABSOLUTE


def test_extracts_responses_api_text() -> None:
    text = extract_output_text(
        {"output": [{"content": [{"type": "output_text", "text": '{"hypothesis": "h"}'}]}]}
    )
    assert "hypothesis" in text


def test_executable_fields_are_discarded() -> None:
    raw = """
    Here is the plan:
    {"objective": "grip", "hypothesis": "stiffer fingers", "rationale": "deflection",
     "simulation_calls": 99999, "candidate_regions": [],
     "prioritized_actions": ["bias_stiffer", "rm -rf"],
     "python": "import os; os.system('echo hacked')", "shell": "echo no"}
    """
    plan = parse_plan_text(raw, GRIPPER_DESIGN_ABSOLUTE, 100, GRIPPER_ACTIONS)
    assert plan.rejected_code is True
    assert plan.simulation_calls == 100
    assert plan.prioritized_actions == ["bias_stiffer"]
    assert "python" not in plan.model_dump()


def test_region_is_clamped_into_user_bounds() -> None:
    raw = (
        '{"objective": "grip", "hypothesis": "force", "rationale": "load", '
        '"simulation_calls": 10, "prioritized_actions": ["bias_higher_force"], '
        '"candidate_regions": [{"name": "hot", "bounds": {"actuator_force_n": [0, 500]}}]}'
    )
    plan = parse_plan_text(raw, GRIPPER_DESIGN_ABSOLUTE, 50, GRIPPER_ACTIONS)
    lo, hi = plan.candidate_regions[0].bounds["actuator_force_n"]
    assert lo >= 5
    assert hi <= 80


def test_mock_plan_is_deterministic_and_offline() -> None:
    config = RunConfig(model_provider="mock")
    first = MockPlanner().propose(config, GRIPPER_DESIGN_ABSOLUTE)
    second = MockPlanner().propose(config, GRIPPER_DESIGN_ABSOLUTE)
    assert first.model_dump() == second.model_dump()
    assert first.provider == "mock"
    assert first.candidate_regions[0].bounds["actuator_force_n"][0] >= 42


def test_disabled_meta_flag_uses_mock() -> None:
    settings = Settings(enable_meta=False, model_api_key="secret")
    planner = build_planner("meta", settings)
    plan = planner.propose(RunConfig(model_provider="meta"), GRIPPER_DESIGN_ABSOLUTE)
    assert plan.provider == "mock"
    assert any("ENABLE_META" in warning for warning in plan.warnings)


def test_timeouts_retry_then_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = MetaClient(
        Settings(
            enable_meta=True, model_api_key="test-key", meta_base_url="https://example.invalid/v1"
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(MetaClientError, match="timeout"):
        client.complete("Return JSON")
    assert client.usage["errors"] == 3
    assert client.usage["requests"] == 0


def test_rate_limit_then_success() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(
            200,
            json={"output_text": '{"ok": true}', "usage": {"input_tokens": 3, "output_tokens": 2}},
        )

    client = MetaClient(
        Settings(enable_meta=True, model_api_key="test-key"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _seconds: None,
    )
    text = client.complete("Return JSON")
    assert "ok" in text
    assert client.usage["requests"] == 2
    assert client.usage["input_tokens"] == 3


def test_malformed_reply_is_repaired_once() -> None:
    from app.agents.planner import MetaPlanner

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0
            self.usage = {"requests": 0}

        def complete(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "not json"
            return (
                '{"objective": "grip", "hypothesis": "raise force", "rationale": "margin", '
                '"simulation_calls": 12, "candidate_regions": [], '
                '"prioritized_actions": ["bias_higher_force"]}'
            )

    fake = FakeClient()
    planner = MetaPlanner(Settings(enable_meta=True, model_api_key="k"), client=fake)  # type: ignore[arg-type]
    plan = planner.propose(RunConfig(), GRIPPER_DESIGN_ABSOLUTE)
    assert plan.provider == "meta"
    assert fake.calls == 2
    assert plan.hypothesis == "raise force"
    assert any("repair" in warning for warning in plan.warnings)
