"""Typed planners. Mock and rule planners keep the demo runnable with no network."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.agents.meta_client import MetaClient, MetaClientError
from app.core.config import Settings
from app.models.schemas import CandidateRegion, ExperimentPlan, RunConfig
from app.sim.bounds import ENERGY_ACTIONS, GRIPPER_ACTIONS

FORBIDDEN_FIELDS = {"python", "shell", "exec", "code", "file_path", "command", "path"}

GRIPPER_BIAS: dict[str, dict[str, float]] = {
    "bias_higher_force": {"actuator_force_n": 0.08},
    "bias_wider_pads": {"pad_width_mm": 0.08},
    "bias_stiffer": {"stiffness_n_per_mm": 0.08},
    "bias_longer_fingers": {"finger_length_mm": 0.05},
    "bias_wider_jaw": {"jaw_opening_mm": 0.08},
    "reduce_material": {
        "finger_length_mm": -0.06,
        "pad_width_mm": -0.05,
        "stiffness_n_per_mm": -0.04,
    },
}

ENERGY_BIAS: dict[str, dict[str, float]] = {
    "bias_more_solar": {"solar_kw": 0.08},
    "bias_more_storage": {"storage_kwh": 0.08},
    "bias_more_discharge": {"discharge_kw": 0.08},
    "reduce_cost": {"solar_kw": -0.05, "storage_kwh": -0.05},
}


class Critique(BaseModel):
    hypothesis: str
    action: str
    rationale: str
    provider: str
    warnings: list[str] = Field(default_factory=list)


class Planner(Protocol):
    name: str

    def propose(
        self, config: RunConfig, bounds: dict[str, tuple[float, float]]
    ) -> ExperimentPlan: ...

    def critique(self, evidence: dict[str, Any], allowlist: tuple[str, ...]) -> Critique: ...


def allowlist_for(domain: str) -> tuple[str, ...]:
    return GRIPPER_ACTIONS if domain == "gripper_2d" else ENERGY_ACTIONS


def bias_for(domain: str, action: str) -> dict[str, float]:
    table = GRIPPER_BIAS if domain == "gripper_2d" else ENERGY_BIAS
    return dict(table.get(action, {}))


def stress_name(action: str | None) -> str | None:
    if action and action.startswith("stress_"):
        return action
    return None


def _band(
    bounds: dict[str, tuple[float, float]], key: str, low: float, high: float
) -> tuple[float, float]:
    lo, hi = bounds[key]
    span = hi - lo
    start = lo + low * span
    end = lo + high * span
    return (start, end)


def _load_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model text")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model JSON was not an object")
    return data


def _clean_bounds(
    raw: Any, bounds: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    cleaned: dict[str, tuple[float, float]] = {}
    if not isinstance(raw, dict):
        return cleaned
    for key, value in raw.items():
        if key not in bounds or not isinstance(value, list | tuple) or len(value) != 2:
            continue
        try:
            lo, hi = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            continue
        ulo, uhi = bounds[key]
        lo, hi = max(lo, ulo), min(hi, uhi)
        if lo < hi:
            cleaned[str(key)] = (lo, hi)
    return cleaned


def parse_plan_text(
    text: str,
    bounds: dict[str, tuple[float, float]],
    call_budget: int,
    allowlist: tuple[str, ...],
) -> ExperimentPlan:
    """Parse planner JSON. Executable fields are discarded and never run."""
    data = _load_object(text)
    rejected = any(key in data for key in FORBIDDEN_FIELDS)
    hypothesis = str(data.get("hypothesis") or "").strip()
    if not hypothesis:
        raise ValueError("hypothesis missing")
    rationale = str(data.get("rationale") or "").strip() or "No rationale was provided."
    objective = str(
        data.get("objective") or "Improve the declared objective within bounds."
    ).strip()
    try:
        calls = int(data.get("simulation_calls") or call_budget)
    except (TypeError, ValueError):
        calls = call_budget
    actions: list[str] = []
    raw_actions = data.get("prioritized_actions") or []
    if isinstance(raw_actions, list):
        for action in raw_actions:
            if action in allowlist and action not in actions:
                actions.append(str(action))
    regions: list[CandidateRegion] = []
    raw_regions = data.get("candidate_regions") or []
    if isinstance(raw_regions, list):
        for item in raw_regions[:4]:
            if not isinstance(item, dict):
                continue
            regions.append(
                CandidateRegion(
                    name=str(item.get("name") or "region")[:80],
                    hypothesis=str(item.get("hypothesis") or "")[:400],
                    bounds=_clean_bounds(item.get("bounds"), bounds),
                )
            )
    warnings: list[str] = []
    if rejected:
        warnings.append("Model output included executable fields. They were discarded and not run.")
    return ExperimentPlan(
        objective=objective[:400],
        hypothesis=hypothesis[:800],
        rationale=rationale[:800],
        simulation_calls=max(0, min(calls, call_budget)),
        candidate_regions=regions,
        prioritized_actions=actions,
        provider="parsed",
        rejected_code=rejected,
        warnings=warnings,
    )


def parse_critique_text(text: str, allowlist: tuple[str, ...]) -> tuple[str, str, str]:
    data = _load_object(text)
    if any(key in data for key in FORBIDDEN_FIELDS):
        raise ValueError("critique included executable fields")
    action = str(data.get("action") or "")
    if action not in allowlist:
        raise ValueError("critique action is not allowlisted")
    hypothesis = str(data.get("hypothesis") or "").strip()
    rationale = str(data.get("rationale") or "").strip()
    if not hypothesis or not rationale:
        raise ValueError("critique is missing hypothesis or rationale")
    return hypothesis[:800], action, rationale[:800]


def _proposal_prompt(
    config: RunConfig, bounds: dict[str, tuple[float, float]], allowlist: tuple[str, ...]
) -> str:
    return (
        "You are a design-of-experiments planner for a numerical simulator. "
        "Return one JSON object and nothing else. Do not return Python, shell, file paths, or code. "
        "The application will ignore any such fields and will not execute them.\n"
        f"Domain: {config.domain}. Seed: {config.seed}. "
        f"Simulator call budget: {config.budget.total_simulator_calls}.\n"
        f"Design bounds: {json.dumps(bounds)}.\n"
        f"Allowed actions: {list(allowlist)}.\n"
        'Schema: {"objective": str, "hypothesis": str, "rationale": str, '
        '"simulation_calls": int, "candidate_regions": [{"name": str, "hypothesis": str, '
        '"bounds": {parameter: [low, high]}}], "prioritized_actions": [action]}.'
    )


class RulePlanner:
    name = "rule"

    def propose(self, config: RunConfig, bounds: dict[str, tuple[float, float]]) -> ExperimentPlan:
        if config.domain == "gripper_2d":
            hypothesis = (
                "Keep the search inside the declared jaw, pad, force, and stiffness limits, "
                "and spend the early evaluations on stiffer fingers before adding length."
            )
            actions = ["bias_stiffer", "stress_low_friction"]
            objective = "Raise grip success, then reduce the material proxy."
        else:
            hypothesis = (
                "Cover the synthetic day with storage before buying extra solar, "
                "and reserve part of the budget for low-sun days inside the envelope."
            )
            actions = ["bias_more_storage", "stress_low_sun"]
            objective = "Serve the synthetic demand, then reduce the cost proxy."
        return ExperimentPlan(
            objective=objective,
            hypothesis=hypothesis,
            rationale="Rule planner uses fixed engineering priorities and does not call a model.",
            simulation_calls=config.budget.total_simulator_calls,
            candidate_regions=[],
            prioritized_actions=actions,
            provider=self.name,
        )

    def critique(self, evidence: dict[str, Any], allowlist: tuple[str, ...]) -> Critique:
        success = float(evidence.get("best_success_rate") or 0.0)
        domain = str(evidence.get("domain") or "gripper_2d")
        if domain == "gripper_2d":
            action = "bias_higher_force" if success < 0.75 else "stress_low_friction"
            hypothesis = (
                "Low train-core success means the actuator force is the first lever; "
                "otherwise look for a low-friction stress case inside the envelope."
            )
        else:
            action = "bias_more_solar" if success < 0.75 else "stress_low_sun"
            hypothesis = "Unserved days call for more solar first; otherwise stress the low-sun end of the envelope."
        if action not in allowlist:
            action = allowlist[0]
        return Critique(
            hypothesis=hypothesis,
            action=action,
            rationale="Chosen from train-core success only. Holdout scores are not visible to this rule.",
            provider=self.name,
        )


class MockPlanner:
    """Deterministic stand-in used for tests, CI, and the offline demo."""

    name = "mock"
    forced_warning = ""

    def propose(self, config: RunConfig, bounds: dict[str, tuple[float, float]]) -> ExperimentPlan:
        if config.domain == "gripper_2d":
            region = CandidateRegion(
                name="upper-force-stiffness",
                hypothesis="Upper-half force and stiffness should clear the safety-weighted load with less deflection.",
                bounds={
                    "actuator_force_n": _band(bounds, "actuator_force_n", 0.5, 1.0),
                    "stiffness_n_per_mm": _band(bounds, "stiffness_n_per_mm", 0.5, 1.0),
                },
            )
            actions = ["bias_higher_force", "bias_stiffer"]
            hypothesis = (
                "Seeding the upper half of actuator force and stiffness finds feasible grasps "
                "before the search spends material on longer fingers."
            )
            objective = "Maximise grip success at a restrained material proxy."
        else:
            region = CandidateRegion(
                name="upper-solar-storage",
                hypothesis="More solar and storage should cut unmet energy before discharge is increased.",
                bounds={
                    "solar_kw": _band(bounds, "solar_kw", 0.5, 1.0),
                    "storage_kwh": _band(bounds, "storage_kwh", 0.5, 1.0),
                },
            )
            actions = ["bias_more_solar", "bias_more_storage"]
            hypothesis = (
                "Seeding the upper half of solar and storage covers the evening bump "
                "on the synthetic training days."
            )
            objective = "Serve synthetic demand at a restrained cost proxy."
        warnings = [self.forced_warning] if self.forced_warning else []
        return ExperimentPlan(
            objective=objective,
            hypothesis=hypothesis,
            rationale="Deterministic mock planner. No model was called and no generated code was run.",
            simulation_calls=config.budget.total_simulator_calls,
            candidate_regions=[region],
            prioritized_actions=actions,
            provider=self.name,
            warnings=warnings,
        )

    def critique(self, evidence: dict[str, Any], allowlist: tuple[str, ...]) -> Critique:
        domain = str(evidence.get("domain") or "gripper_2d")
        action = "bias_higher_force" if domain == "gripper_2d" else "bias_more_storage"
        if action not in allowlist:
            action = allowlist[0]
        return Critique(
            hypothesis=(
                "Shift the next generation toward the allowlisted bias and keep the adversary inside the envelope."
            ),
            action=action,
            rationale="Mock critique is a fixed allowlisted action so the offline loop stays reproducible.",
            provider=self.name,
            warnings=[self.forced_warning] if self.forced_warning else [],
        )


class MetaPlanner:
    name = "meta"

    def __init__(self, settings: Settings, client: MetaClient | None = None) -> None:
        self.settings = settings
        self.client = client or MetaClient(settings)
        self._rule = RulePlanner()

    def propose(self, config: RunConfig, bounds: dict[str, tuple[float, float]]) -> ExperimentPlan:
        allowlist = allowlist_for(config.domain)
        prompt = _proposal_prompt(config, bounds, allowlist)
        try:
            plan = parse_plan_text(
                self.client.complete(prompt),
                bounds,
                config.budget.total_simulator_calls,
                allowlist,
            )
        except (MetaClientError, ValueError, json.JSONDecodeError) as first_error:
            try:
                repair = (
                    "Your previous reply was rejected. Return one JSON object matching the schema. "
                    "Do not return Python, shell, file paths, or code.\n" + prompt
                )
                plan = parse_plan_text(
                    self.client.complete(repair),
                    bounds,
                    config.budget.total_simulator_calls,
                    allowlist,
                )
                plan.warnings.append(
                    "The first model reply failed validation and one repair was attempted."
                )
            except (MetaClientError, ValueError, json.JSONDecodeError):
                plan = self._rule.propose(config, bounds)
                plan.provider = "rule-fallback"
                plan.warnings.append(
                    f"Meta planner fell back to the rule planner ({first_error.__class__.__name__})."
                )
                return plan
        plan.provider = "meta"
        plan.warnings.append(f"Model usage: {self.client.usage}")
        return plan

    def critique(self, evidence: dict[str, Any], allowlist: tuple[str, ...]) -> Critique:
        prompt = (
            "Given this compact evidence, choose one next action. Return JSON only. "
            "Do not return code.\n"
            f"Allowed actions: {list(allowlist)}.\n"
            f"Evidence: {json.dumps(evidence, default=str)[:2000]}\n"
            'Schema: {"hypothesis": str, "action": str, "rationale": str}.'
        )
        try:
            hypothesis, action, rationale = parse_critique_text(
                self.client.complete(prompt), allowlist
            )
            return Critique(
                hypothesis=hypothesis,
                action=action,
                rationale=rationale,
                provider="meta",
            )
        except (MetaClientError, ValueError, json.JSONDecodeError) as exc:
            critique = self._rule.critique(evidence, allowlist)
            critique.provider = "rule-fallback"
            critique.warnings.append(
                f"Critique fell back to the rule planner ({exc.__class__.__name__})."
            )
            return critique


def build_planner(provider: str, settings: Settings, client: MetaClient | None = None) -> Planner:
    if provider == "meta":
        if not settings.enable_meta:
            planner = MockPlanner()
            planner.forced_warning = (
                "ENABLE_META is false, so the deterministic mock planner was used instead of the model."
            )
            return planner
        return MetaPlanner(settings, client=client)
    if provider == "rule":
        return RulePlanner()
    return MockPlanner()
