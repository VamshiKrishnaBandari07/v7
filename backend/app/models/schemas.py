"""Pydantic contracts shared by the simulator, search, API, and dashboard."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.sim.bounds import ENERGY_DESIGN_ABSOLUTE, GRIPPER_DESIGN_ABSOLUTE

DomainName = Literal["gripper_2d", "energy"]
ProviderName = Literal["mock", "rule", "meta"]
RunStatus = Literal[
    "PENDING",
    "PLANNING",
    "SIMULATING",
    "EVOLVING",
    "VALIDATING",
    "COMPLETE",
    "FAILED",
    "CANCELLED",
]
MethodName = Literal["random", "evolutionary", "adversarial"]


class BudgetConfig(BaseModel):
    total_simulator_calls: int = Field(default=1200, ge=90, le=40000)
    adversarial_fraction: float = Field(default=0.2, ge=0.0, le=0.6)
    playback_ms: int = Field(default=0, ge=0, le=2000)


class ScenarioCounts(BaseModel):
    train_count: int = Field(default=8, ge=4, le=400)
    holdout_count: int = Field(default=24, ge=4, le=800)


class RunConfig(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "domain": "gripper_2d",
                    "seed": 42,
                    "budget": {
                        "total_simulator_calls": 1200,
                        "adversarial_fraction": 0.2,
                        "playback_ms": 0,
                    },
                    "scenarios": {"train_count": 8, "holdout_count": 24},
                    "objectives": ["grip_success", "material_proxy"],
                    "model_provider": "mock",
                }
            ]
        }
    )

    domain: DomainName = "gripper_2d"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    design_bounds: dict[str, tuple[float, float]] | None = None
    scenarios: ScenarioCounts = Field(default_factory=ScenarioCounts)
    objectives: list[str] = Field(default_factory=lambda: ["grip_success", "material_proxy"])
    model_provider: ProviderName = "mock"
    blocking: bool = False

    @model_validator(mode="after")
    def bounds_inside_absolute(self) -> RunConfig:
        if self.design_bounds is None:
            return self
        absolute = (
            GRIPPER_DESIGN_ABSOLUTE if self.domain == "gripper_2d" else ENERGY_DESIGN_ABSOLUTE
        )
        if set(self.design_bounds) != set(absolute):
            missing = sorted(set(absolute) - set(self.design_bounds))
            extra = sorted(set(self.design_bounds) - set(absolute))
            raise ValueError(
                f"design_bounds keys must match the domain (missing {missing}, extra {extra})"
            )
        for key, pair in self.design_bounds.items():
            lo, hi = float(pair[0]), float(pair[1])
            if lo >= hi:
                raise ValueError(f"{key}: low must be below high")
            alo, ahi = absolute[key]
            if lo < alo - 1e-9 or hi > ahi + 1e-9:
                raise ValueError(f"{key}: {lo}..{hi} is outside absolute {alo}..{ahi}")
            self.design_bounds[key] = (lo, hi)
        if self.domain == "gripper_2d":
            pad_lo = self.design_bounds["pad_width_mm"][0]
            finger_hi = self.design_bounds["finger_length_mm"][1]
            if pad_lo > finger_hi:
                raise ValueError("pad width lower bound exceeds every feasible finger length")
        return self


class DesignConfig(BaseModel):
    jaw_opening_mm: float
    finger_length_mm: float
    pad_width_mm: float
    stiffness_n_per_mm: float
    actuator_force_n: float
    id: str = ""


class Scenario(BaseModel):
    object_mass_kg: float
    object_width_mm: float
    friction: float
    lateral_disturbance_n: float
    safety_factor: float
    id: str = ""


class SimulationResult(BaseModel):
    feasible: bool
    geometry_ok: bool
    valid_input: bool = True
    normal_force_n: float
    friction_capacity_n: float
    required_force_n: float
    margin_n: float
    deflection_mm: float
    deflection_scale: float
    engagement: float
    material_proxy: float
    reasons: list[str]
    simulator_version: str
    assumptions_hash: str
    scenario_id: str = ""
    design_id: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)


class AggregateScore(BaseModel):
    success_rate: float
    mean_margin_n: float
    worst_margin_n: float
    material_proxy: float
    mean_deflection_mm: float
    fitness: float
    scenario_count: int
    score_basis: str


class CandidateRecord(BaseModel):
    id: str
    method: str
    generation: int
    parent_ids: list[str] = Field(default_factory=list)
    origin: str
    parameters: dict[str, float]
    score: AggregateScore
    is_finalist: bool = False
    is_pareto: bool = False
    preregistered: bool = False


class FailureRecord(BaseModel):
    id: str
    method: str
    design_id: str
    generation: int
    parameters: dict[str, float]
    scenario: dict[str, Any]
    margin_n: float
    feasible: bool
    explanation: str
    reasons: list[str]
    linked_design_ids: list[str] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    generation: int
    simulator_calls: int
    best_fitness: float
    best_success_rate: float
    best_material: float
    best_worst_margin: float


class ParetoPoint(BaseModel):
    id: str
    method: str
    success_rate: float
    material_proxy: float
    worst_margin_n: float
    fitness: float
    parameters: dict[str, float]
    preregistered: bool = False


class CandidateRegion(BaseModel):
    name: str
    hypothesis: str = ""
    bounds: dict[str, tuple[float, float]] = Field(default_factory=dict)


class ExperimentPlan(BaseModel):
    objective: str
    hypothesis: str
    rationale: str
    simulation_calls: int
    candidate_regions: list[CandidateRegion] = Field(default_factory=list)
    prioritized_actions: list[str] = Field(default_factory=list)
    provider: str
    rejected_code: bool = False
    warnings: list[str] = Field(default_factory=list)


class ProvenanceEvent(BaseModel):
    id: str
    kind: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class HoldoutScore(BaseModel):
    method: str
    design_id: str
    parameters: dict[str, float]
    success_rate: float
    mean_margin_n: float
    worst_margin_n: float
    material_proxy: float
    scenario_count: int
    preregistered: bool
    exploratory: bool


class MethodReport(BaseModel):
    method: str
    simulator_calls: int
    design_evaluations: int
    adversarial_calls: int
    history: list[HistoryPoint]
    pareto: list[ParetoPoint]
    finalist_ids: list[str]
    best: ParetoPoint | None = None


class Report(BaseModel):
    run_id: str
    domain: str
    seed: int
    status: str
    simulator_version: str
    assumptions_hash: str
    holdout_fingerprint: str
    train_fingerprint: str
    search_budget_per_method: dict[str, int]
    validation_calls: int
    total_search_calls: int
    methods: list[MethodReport]
    holdout: list[HoldoutScore]
    planner: ExperimentPlan | None
    provenance: list[ProvenanceEvent]
    limitations: list[str]
    git_sha: str
    config: dict[str, Any]
    failure_count: int
    train_scenarios: list[dict[str, Any]]
    holdout_scenarios: list[dict[str, Any]]
    objective_labels: dict[str, str]


class ProgressView(BaseModel):
    phase: str
    message: str
    simulator_calls: int = 0
    budget: int = 0
    best_score: float | None = None
    best_success_rate: float | None = None
    method: str | None = None


class RunView(BaseModel):
    id: str
    status: str
    domain: str
    created_at: str
    updated_at: str
    progress: dict[str, Any]
    error: str | None = None
    report: Report | None = None


class RunCreated(BaseModel):
    id: str
    status: str
