from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd


PathLike = Union[str, Path]


def load_daily_records(csv_path: PathLike) -> pd.DataFrame:
    """read simulation daily record"""
    df = pd.read_csv(csv_path)

    required_columns = {
        "day",
        "demand",
        "shipped_dc_to_cu",
        "dc_on_hand",
        "cu_backlog",
        "fulfilment_rate_to_date",
        "dc_days_of_supply",
        "dc_inv_gap",
        "dc_urgent_air_needed",
        "total_cost_today",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV missing columns: {sorted(missing_columns)}"
        )

    return df


def get_inventory_summary(df: pd.DataFrame) -> dict:
    """inventory and service level"""
    return {
        "average_dc_inventory": round(float(df["dc_on_hand"].mean()), 2),
        "minimum_dc_inventory": int(df["dc_on_hand"].min()),
        "final_dc_inventory": int(df["dc_on_hand"].iloc[-1]),
        "final_backlog": int(df["cu_backlog"].iloc[-1]),
        "minimum_days_of_supply": round(
            float(df["dc_days_of_supply"].min()), 2
        ),
        "final_fulfilment_rate": round(
            float(df["fulfilment_rate_to_date"].iloc[-1]), 4
        ),
        "total_cost": round(float(df["total_cost_today"].sum()), 2),
    }


def get_demand_supply_summary(df: pd.DataFrame) -> pd.DataFrame:
    """compare daily demand and actual supply"""
    summary = df[
        [
            "day",
            "demand",
            "shipped_dc_to_cu",
            "dc_on_hand",
            "cu_backlog",
            "fulfilment_rate_to_date",
        ]
    ].copy()

    summary["supply_gap"] = (
        summary["demand"] - summary["shipped_dc_to_cu"]
    )

    summary["stockout_risk"] = (
        (summary["dc_on_hand"] <= 0)
        | (summary["cu_backlog"] > 0)
    )

    return summary


def get_procurement_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """find the error"""
    anomalies = df[
    (df["dc_urgent_air_needed"] == True)
    | (df["cu_backlog"] > 0)
    | (df["dc_days_of_supply"] < 7)
].copy()

    if anomalies.empty:
        return pd.DataFrame(
            columns=[
                "day",
                "severity",
                "anomaly_type",
                "backlog",
                "days_of_supply",
                "inventory_gap",
            ]
        )

    anomalies["severity"] = "medium"

    anomalies.loc[
        (anomalies["cu_backlog"] > 0)
        | (anomalies["dc_days_of_supply"] < 3),
        "severity",
    ] = "high"

    anomalies["anomaly_type"] = "inventory_or_supply_risk"

    return anomalies[
        [
            "day",
            "severity",
            "anomaly_type",
            "cu_backlog",
            "dc_days_of_supply",
            "dc_inv_gap",
        ]
    ].rename(
        columns={
            "cu_backlog": "backlog",
            "dc_days_of_supply": "days_of_supply",
            "dc_inv_gap": "inventory_gap",
        }
    )


def analyse_simulation(csv_path: PathLike) -> dict:
    """analysis"""
    df = load_daily_records(csv_path)

    return {
        "inventory_summary": get_inventory_summary(df),
        "demand_supply": get_demand_supply_summary(df),
        "procurement_anomalies": get_procurement_anomalies(df),
    }


if __name__ == "__main__":
    input_path = Path("data/demo_baseline_365/daily_records.csv")

    result = analyse_simulation(input_path)

    print("=== Inventory Summary ===")
    for key, value in result["inventory_summary"].items():
        print(f"{key}: {value}")

    print("\n=== Procurement Anomalies ===")
    print(result["procurement_anomalies"].head(10).to_string(index=False))
