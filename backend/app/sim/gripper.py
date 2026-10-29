"""Analytic 2D opposing-jaw gripper surrogate.

Equations are the measurement. Model text is never a score.
See docs/assumptions.md. Internal units are SI; the public fields stay in
millimetres and newtons as declared on each quantity.
"""

from __future__ import annotations

import hashlib
import math

from app.models.schemas import DesignConfig, Scenario, SimulationResult
from app.sim.bounds import GRIPPER_DESIGN_ABSOLUTE, GRIPPER_TRAIN_ENVELOPE

SIMULATOR_VERSION = "gripper-2d-1.0.0"
G_MPS2 = 9.81
L_REF_M = 0.040
DELTA_SOFT_M = 0.003
DELTA_HARD_M = 0.008
FINGER_WIDTH_RATIO = 0.35

ASSUMPTIONS_TEXT = """\
gripper-analytic-surrogate-v1
g = 9.81 m/s^2
required_force_n = safety_factor * hypot(mass_kg * g, lateral_disturbance_n)
engagement = min(1, pad_width_mm / max(8 mm, 0.25 * object_width_mm))
friction_raw_n = 2 * friction * actuator_force_n * engagement
k_tip_n_per_m = stiffness_n_per_mm * 1000 * (0.040 / finger_length_m)^3
deflection_m = actuator_force_n / k_tip_n_per_m
deflection scale is 1 at or below 0.003 m, 0 at or above 0.008 m, linear between
friction_capacity_n = friction_raw_n * deflection_scale
margin_n = friction_capacity_n - required_force_n
geometry fails when object_width_mm > jaw_opening_mm
geometry fails when finger_length_mm < 0.35 * object_width_mm
feasible when geometry_ok and margin_n >= 0 and deflection_scale > 0 and friction > 0
material_proxy = 2 * (finger_length_mm / 10) * (pad_width_mm / 10) * sqrt(stiffness_n_per_mm)
"""

ASSUMPTIONS_HASH = hashlib.sha256(ASSUMPTIONS_TEXT.encode("utf-8")).hexdigest()[:16]


def material_proxy(design: DesignConfig) -> float:
    return (
        2.0
        * (design.finger_length_mm / 10.0)
        * (design.pad_width_mm / 10.0)
        * math.sqrt(design.stiffness_n_per_mm)
    )


def material_proxy_params(params: dict[str, float]) -> float:
    return material_proxy(DesignConfig(**params))


def validate_design(design: DesignConfig) -> list[str]:
    errors: list[str] = []
    for key, (lo, hi) in GRIPPER_DESIGN_ABSOLUTE.items():
        value = float(getattr(design, key))
        if not math.isfinite(value):
            errors.append(f"{key} is not finite")
            continue
        if value < lo - 1e-9 or value > hi + 1e-9:
            errors.append(f"{key} {value:.4g} is outside {lo:g} to {hi:g}")
    if design.pad_width_mm > design.finger_length_mm + 1e-9:
        errors.append("pad width exceeds finger length")
    return errors


def validate_scenario(
    scenario: Scenario, envelope: dict[str, tuple[float, float]] | None = None
) -> list[str]:
    bounds = envelope or GRIPPER_TRAIN_ENVELOPE
    errors: list[str] = []
    for key, (lo, hi) in bounds.items():
        value = float(getattr(scenario, key))
        if not math.isfinite(value):
            errors.append(f"{key} is not finite")
            continue
        if value < lo - 1e-9 or value > hi + 1e-9:
            errors.append(f"{key} {value:.4g} is outside envelope {lo:g} to {hi:g}")
    if scenario.friction < -1e-12 or scenario.friction > 1.5:
        errors.append("friction is outside the physical allowlist 0 to 1.5")
    if scenario.safety_factor < 1.0:
        errors.append("safety factor below 1 is not a valid requirement")
    return errors


def _invalid(
    reasons: list[str], design: DesignConfig | None, scenario_id: str, design_id: str
) -> SimulationResult:
    material = 0.0
    if design is not None:
        try:
            if (
                design.stiffness_n_per_mm > 0
                and design.finger_length_mm > 0
                and design.pad_width_mm > 0
            ):
                material = material_proxy(design)
        except (ValueError, OverflowError):
            material = 0.0
    return SimulationResult(
        feasible=False,
        geometry_ok=False,
        valid_input=False,
        normal_force_n=0.0,
        friction_capacity_n=0.0,
        required_force_n=0.0,
        margin_n=-1.0e6,
        deflection_mm=0.0,
        deflection_scale=0.0,
        engagement=0.0,
        material_proxy=material,
        reasons=reasons,
        simulator_version=SIMULATOR_VERSION,
        assumptions_hash=ASSUMPTIONS_HASH,
        scenario_id=scenario_id,
        design_id=design_id,
    )


def evaluate(
    design: DesignConfig, scenario: Scenario, *, check_scenario_envelope: bool = False
) -> SimulationResult:
    """Score one design on one scenario. Pure and deterministic."""
    design_errors = validate_design(design)
    if design_errors:
        return _invalid(design_errors, None, scenario.id, design.id)
    if check_scenario_envelope:
        scenario_errors = validate_scenario(scenario)
        if scenario_errors:
            return _invalid(scenario_errors, design, scenario.id, design.id)

    reasons: list[str] = []
    geometry_ok = True
    if scenario.object_width_mm > design.jaw_opening_mm + 1e-9:
        geometry_ok = False
        reasons.append("object wider than jaw opening")
    if design.finger_length_mm + 1e-9 < FINGER_WIDTH_RATIO * scenario.object_width_mm:
        geometry_ok = False
        reasons.append("finger too short for object width")

    weight_n = scenario.object_mass_kg * G_MPS2
    required = scenario.safety_factor * math.hypot(weight_n, scenario.lateral_disturbance_n)
    engagement = min(
        1.0,
        design.pad_width_mm / max(8.0, 0.25 * scenario.object_width_mm),
    )
    if engagement < 0.9:
        reasons.append("narrow pad reduces contact engagement")

    normal = design.actuator_force_n
    friction_raw = 2.0 * scenario.friction * normal * engagement
    length_m = design.finger_length_mm / 1000.0
    k_tip = (design.stiffness_n_per_mm * 1000.0) * (L_REF_M / length_m) ** 3
    deflection_m = normal / k_tip
    if deflection_m <= DELTA_SOFT_M:
        scale = 1.0
    elif deflection_m >= DELTA_HARD_M:
        scale = 0.0
        reasons.append("deflection exceeds hard limit and contact is lost")
    else:
        scale = 1.0 - (deflection_m - DELTA_SOFT_M) / (DELTA_HARD_M - DELTA_SOFT_M)
        reasons.append("deflection in the penalty band reduces normal contact")

    friction = friction_raw * scale
    margin = friction - required
    if scenario.friction <= 1e-12:
        reasons.append("zero friction cannot transmit holding force")
    elif margin < 0.0 and geometry_ok and scale > 0.0:
        reasons.append("friction capacity is below the required holding force")

    feasible = geometry_ok and margin >= -1e-9 and scale > 0.0 and scenario.friction > 0.0
    return SimulationResult(
        feasible=feasible,
        geometry_ok=geometry_ok,
        valid_input=True,
        normal_force_n=normal,
        friction_capacity_n=friction,
        required_force_n=required,
        margin_n=margin,
        deflection_mm=deflection_m * 1000.0,
        deflection_scale=scale,
        engagement=engagement,
        material_proxy=material_proxy(design),
        reasons=reasons,
        simulator_version=SIMULATOR_VERSION,
        assumptions_hash=ASSUMPTIONS_HASH,
        scenario_id=scenario.id,
        design_id=design.id,
    )


def explain(design: DesignConfig, scenario: Scenario, result: SimulationResult) -> str:
    cause = (
        "; ".join(result.reasons)
        if result.reasons
        else "the grasp meets the surrogate inequalities"
    )
    return (
        f"Friction capacity {result.friction_capacity_n:.2f} N versus required "
        f"{result.required_force_n:.2f} N for a {scenario.object_mass_kg:.2f} kg object "
        f"{scenario.object_width_mm:.1f} mm wide, friction {scenario.friction:.2f}, "
        f"disturbance {scenario.lateral_disturbance_n:.2f} N, safety factor {scenario.safety_factor:.2f}. "
        f"Jaw {design.jaw_opening_mm:.1f} mm, finger {design.finger_length_mm:.1f} mm, "
        f"pad {design.pad_width_mm:.1f} mm, stiffness {design.stiffness_n_per_mm:.2f} N/mm, "
        f"actuator {design.actuator_force_n:.1f} N. "
        f"Deflection {result.deflection_mm:.2f} mm scales contact by {result.deflection_scale:.2f} "
        f"and engagement is {result.engagement:.2f}. Causes: {cause}."
    )


def design_from_params(params: dict[str, float], design_id: str = "") -> DesignConfig:
    return DesignConfig(
        jaw_opening_mm=float(params["jaw_opening_mm"]),
        finger_length_mm=float(params["finger_length_mm"]),
        pad_width_mm=float(params["pad_width_mm"]),
        stiffness_n_per_mm=float(params["stiffness_n_per_mm"]),
        actuator_force_n=float(params["actuator_force_n"]),
        id=design_id,
    )


def scenario_from_params(params: dict[str, float], scenario_id: str = "") -> Scenario:
    return Scenario(
        object_mass_kg=float(params["object_mass_kg"]),
        object_width_mm=float(params["object_width_mm"]),
        friction=float(params["friction"]),
        lateral_disturbance_n=float(params["lateral_disturbance_n"]),
        safety_factor=float(params["safety_factor"]),
        id=scenario_id,
    )
