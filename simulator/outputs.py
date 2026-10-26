from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .model import SemiSCM


def write_outputs(model: SemiSCM, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(model.daily_records).to_csv(out_dir / "daily_records.csv", index=False)
    pd.DataFrame(model.shipment_records).to_csv(out_dir / "shipments.csv", index=False)
    pd.DataFrame(model.nego_records).to_csv(
        out_dir / "negos.csv",
        index=False,
    )
    with (out_dir / "scenario.json").open("w", encoding="utf-8") as f:
        json.dump(asdict(model.scenario_config), f, indent=2)

    final = model.daily_records[-1]
    summary = {
        "scenario": model.scenario_config.name,
        "decision_mode": model.decision_mode,
        "llm_provider": model.llm_provider,
        "llm_model": model.llm_model,
        "days": model.days,
        "total_demand": int(sum(r["demand"] for r in model.daily_records)),
        "final_cu_backlog": int(final["cu_backlog"]),
        "final_fulfilment_rate_to_date": float(final["fulfilment_rate_to_date"]),
        "mean_dc_inv": float(
            pd.DataFrame(model.daily_records)["dc_on_hand"].mean()
        ),
        "total_shipped_to_market": int(
            sum(r["shipped_dc_to_cu"] for r in model.daily_records)
        ),
        "cml_production_cost": float(final["cml_production_cost"]),
        "cml_transport_cost": float(final["cml_transport_cost"]),
        "cml_holding_cost": float(final["cml_holding_cost"]),
        "cml_backlog_cost": float(final["cml_backlog_cost"]),
        "cml_nego_premium_cost": float(final["cml_nego_premium_cost"]),
        "cml_production_priority_cost": float(final["cml_production_priority_cost"]),
        "cml_total_cost": float(final["cml_total_cost"]),
        "cost_per_unit_demand": float(
            final["cml_total_cost"]
            / max(1, sum(r["demand"] for r in model.daily_records))
        ),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "service_summary.csv", index=False)
