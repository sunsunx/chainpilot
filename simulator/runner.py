from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .config import (
    DECISION_MODE_RULE_BASED_BDI,
    SCENARIOS,
    validate_decision_mode,
)
from .model import SemiSCM
from .outputs import write_outputs


def run_scenario(
    scenario_name: str,
    days: int,
    seed: int,
    out_dir: Path,
    decision_mode: str = DECISION_MODE_RULE_BASED_BDI,
    llm_model: str = "llama3.2:3b",
    demand_sequence_dir: Optional[Path] = None,
) -> None:
    demand_sequence = None
    if demand_sequence_dir is not None:
        demand_path = demand_sequence_dir / f"{scenario_name}.csv"
        if not demand_path.exists():
            raise FileNotFoundError(f"Demand sequence not found: {demand_path}")
        demand_frame = pd.read_csv(demand_path)
        if "demand" not in demand_frame.columns:
            raise ValueError(
                f"Demand file must contain a 'demand' column: {demand_path}"
            )
        demand_sequence = demand_frame["demand"].astype(int).tolist()
        if len(demand_sequence) < days:
            raise ValueError(
                f"Demand file {demand_path} contains {len(demand_sequence)} rows; "
                f"at least {days} are required."
            )
    model = SemiSCM(
        scenario_name=scenario_name,
        days=days,
        seed=seed,
        decision_mode=validate_decision_mode(decision_mode),
        llm_model=llm_model,
        demand_sequence=demand_sequence,
    )
    model.run_model()
    write_outputs(model, out_dir)


def scenario_names(selection: str) -> Iterable[str]:
    if selection == "all":
        return SCENARIOS.keys()
    return [selection]
