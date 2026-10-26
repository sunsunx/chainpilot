from pathlib import Path

import pandas as pd


def load_summary(path):
    return pd.read_csv(path)


if __name__ == "__main__":
    baseline_path = Path(
        "data/demo_baseline_365/service_summary.csv"
    )

    geopolitical_path = Path(
        "data/demo_geopolitical/service_summary.csv"
    )

    baseline = load_summary(baseline_path)
    geopolitical = load_summary(geopolitical_path)

    comparison = pd.concat(
        [baseline, geopolitical],
        ignore_index=True,
    )

    columns = [
        "scenario",
        "total_demand",
        "final_cu_backlog",
        "final_fulfilment_rate_to_date",
        "cml_total_cost",
        "cost_per_unit_demand",
    ]

    print("=== Scenario Comparison ===")
    print(comparison[columns].to_string(index=False))
