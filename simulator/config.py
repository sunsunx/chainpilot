from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

PRODUCT_ID = "semiconductor_chip"


DECISION_MODE_BASIC_BASELINE = "basic_baseline"
DECISION_MODE_RULE_BASED_BDI = "rule_based_bdi"
DECISION_MODE_LLM = "llm_decision"

SUPPORTED_DECISION_MODES = {
    DECISION_MODE_BASIC_BASELINE,
    DECISION_MODE_RULE_BASED_BDI,
    DECISION_MODE_LLM,
}


def validate_decision_mode(decision_mode: str) -> str:
    if decision_mode not in SUPPORTED_DECISION_MODES:
        valid_modes = ", ".join(sorted(SUPPORTED_DECISION_MODES))
        raise ValueError(
            f"Unknown decision mode {decision_mode!r}. Expected one of: {valid_modes}"
        )
    return decision_mode


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    demand_multiplier: float
    demand_cv: float
    spike_probability: float
    spike_min: int
    spike_max: int
    international_leadtime_multiplier: float
    domestic_leadtime_multiplier: float
    supplier_capacity_factor: float
    hub_to_dc_capacity_factor: float
    dc_to_cu_capacity_factor: float
    disruption_start: int | None = None
    disruption_end: int | None = None
    disruption_capacity_factor: float = 1.0
    production_leadtime_multiplier: float = 1.0
    wafer_fab_min_days: int = 84
    wafer_fab_max_days: int = 140
    packaging_test_days: int = 42  # OSAT


SCENARIOS: Dict[str, ScenarioConfig] = {
    "baseline": ScenarioConfig(
        name="baseline",
        demand_multiplier=1.0,
        demand_cv=0.10,
        spike_probability=0.005,
        spike_min=20,
        spike_max=60,
        international_leadtime_multiplier=1.0,
        domestic_leadtime_multiplier=1.0,
        supplier_capacity_factor=1.0,
        hub_to_dc_capacity_factor=1.0,
        dc_to_cu_capacity_factor=1.0,
    ),
    "geopolitical": ScenarioConfig(
        name="geopolitical",
        demand_multiplier=1.12,
        demand_cv=0.18,
        spike_probability=0.020,
        spike_min=60,
        spike_max=160,
        international_leadtime_multiplier=3.2,
        domestic_leadtime_multiplier=1.20,
        supplier_capacity_factor=0.70,
        hub_to_dc_capacity_factor=0.22,
        dc_to_cu_capacity_factor=0.90,
        disruption_start=60,
        disruption_end=260,
        disruption_capacity_factor=0.35,
        production_leadtime_multiplier=1.10,
    ),
}
