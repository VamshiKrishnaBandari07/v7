"""Toy hourly energy balance. Educational surrogate, not a grid model.

Design: solar_kw, storage_kwh, discharge_kw.
Scenario: demand_base_kw, demand_peak_kw, cloud_factor, evening_bump_kw.
A day is feasible when unmet energy is at most 2% of demand.
material_proxy stores the cost proxy. margin_n stores negative unmet kWh.
"""

from __future__ import annotations

import hashlib
import math

from app.models.schemas import SimulationResult
from app.sim.bounds import ENERGY_DESIGN_ABSOLUTE, ENERGY_TRAIN_ENVELOPE

ENERGY_VERSION = "energy-toy-1.0.0"

ENERGY_ASSUMPTIONS_TEXT = """\
energy-toy-surrogate-v1
24 hourly steps
daylight = max(0, sin(pi * (hour - 5) / 14))
demand = base + (peak - base) * (0.55 + 0.45 * sin(2 * pi * (hour - 8) / 24))
hours 17 through 21 add evening_bump_kw
solar = solar_kw * daylight * cloud_factor
charge efficiency 0.95, discharge limited by discharge_kw and state of charge
initial state of charge is half of storage
feasible when unmet_kwh <= 0.02 * demand_kwh
cost_proxy = 900 * solar_kw + 350 * storage_kwh + 40 * discharge_kw
margin_n = -unmet_kwh
"""

ENERGY_ASSUMPTIONS_HASH = hashlib.sha256(ENERGY_ASSUMPTIONS_TEXT.encode("utf-8")).hexdigest()[:16]


def cost_proxy(params: dict[str, float]) -> float:
    return (
        900.0 * params["solar_kw"] + 350.0 * params["storage_kwh"] + 40.0 * params["discharge_kw"]
    )


def validate_design(params: dict[str, float]) -> list[str]:
    errors: list[str] = []
    for key, (lo, hi) in ENERGY_DESIGN_ABSOLUTE.items():
        value = float(params[key])
        if not math.isfinite(value) or value < lo - 1e-9 or value > hi + 1e-9:
            errors.append(f"{key} {value:.4g} is outside {lo:g} to {hi:g}")
    return errors


def validate_scenario(
    params: dict[str, float], envelope: dict[str, tuple[float, float]] | None = None
) -> list[str]:
    bounds = envelope or ENERGY_TRAIN_ENVELOPE
    errors: list[str] = []
    for key, (lo, hi) in bounds.items():
        value = float(params[key])
        if not math.isfinite(value) or value < lo - 1e-9 or value > hi + 1e-9:
            errors.append(f"{key} {value:.4g} is outside envelope {lo:g} to {hi:g}")
    if float(params["demand_peak_kw"]) + 1e-9 < float(params["demand_base_kw"]):
        errors.append("demand peak is below demand base")
    return errors


def _hour_demand(hour: int, scenario: dict[str, float]) -> float:
    shape = 0.55 + 0.45 * math.sin(2.0 * math.pi * (hour - 8) / 24.0)
    demand = (
        scenario["demand_base_kw"]
        + (scenario["demand_peak_kw"] - scenario["demand_base_kw"]) * shape
    )
    if 17 <= hour <= 21:
        demand += scenario["evening_bump_kw"]
    return max(0.05, demand)


def _daylight(hour: int) -> float:
    return max(0.0, math.sin(math.pi * (hour - 5) / 14.0))


def evaluate(
    params: dict[str, float], scenario: dict[str, float], design_id: str = ""
) -> SimulationResult:
    errors = validate_design(params)
    if errors:
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
            material_proxy=0.0,
            reasons=errors,
            simulator_version=ENERGY_VERSION,
            assumptions_hash=ENERGY_ASSUMPTIONS_HASH,
            scenario_id=str(scenario.get("id", "")),
            design_id=design_id,
        )

    soc = 0.5 * params["storage_kwh"]
    soc_max = params["storage_kwh"]
    unmet = 0.0
    served = 0.0
    demand_total = 0.0
    solar_total = 0.0
    for hour in range(24):
        demand = _hour_demand(hour, scenario)
        solar = params["solar_kw"] * _daylight(hour) * scenario["cloud_factor"]
        demand_total += demand
        solar_total += solar
        if solar >= demand:
            room = max(0.0, soc_max - soc)
            charge = min(solar - demand, room)
            soc += 0.95 * charge
            served += demand
        else:
            deficit = demand - solar
            deliver = min(deficit, soc, params["discharge_kw"])
            soc -= deliver
            served += solar + deliver
            unmet += deficit - deliver
        soc = min(soc_max, max(0.0, soc))

    feasible = unmet <= 0.02 * demand_total + 1e-9
    reasons: list[str] = []
    if not feasible:
        reasons.append("unmet demand exceeds 2 percent of the day's energy")
    if scenario["cloud_factor"] < 0.55:
        reasons.append("low-sun day reduces solar inflow")
    if scenario["evening_bump_kw"] > 0.5:
        reasons.append("evening bump arrives after daylight has fallen")
    cost = cost_proxy(params)
    return SimulationResult(
        feasible=feasible,
        geometry_ok=True,
        valid_input=True,
        normal_force_n=solar_total,
        friction_capacity_n=served,
        required_force_n=demand_total,
        margin_n=-unmet,
        deflection_mm=0.0,
        deflection_scale=1.0,
        engagement=soc / soc_max if soc_max else 0.0,
        material_proxy=cost,
        reasons=reasons,
        simulator_version=ENERGY_VERSION,
        assumptions_hash=ENERGY_ASSUMPTIONS_HASH,
        scenario_id=str(scenario.get("id", "")),
        design_id=design_id,
        metrics={
            "unmet_kwh": unmet,
            "served_kwh": served,
            "demand_kwh": demand_total,
            "cost_proxy": cost,
            "final_soc_kwh": soc,
        },
    )


def explain(params: dict[str, float], scenario: dict[str, float], result: SimulationResult) -> str:
    unmet = result.metrics.get("unmet_kwh", -result.margin_n)
    demand = result.metrics.get("demand_kwh", result.required_force_n)
    cause = (
        "; ".join(result.reasons)
        if result.reasons
        else "the day stays within the 2 percent unmet band"
    )
    return (
        f"Unmet energy {unmet:.2f} kWh of {demand:.2f} kWh demand. "
        f"Solar {params['solar_kw']:.2f} kW, storage {params['storage_kwh']:.2f} kWh, "
        f"discharge limit {params['discharge_kw']:.2f} kW, cloud factor {scenario['cloud_factor']:.2f}, "
        f"evening bump {scenario['evening_bump_kw']:.2f} kW. Cost proxy {result.material_proxy:.0f}. "
        f"Causes: {cause}."
    )
