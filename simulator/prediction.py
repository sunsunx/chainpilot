from pathlib import Path

import pandas as pd


def load_shipments(csv_path):
    """read shipment CSV。"""
    df = pd.read_csv(csv_path)

    required_columns = {
        "lane",
        "transport_mode",
        "lead_time_days",
        "qty",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV missing columns: {sorted(missing_columns)}"
        )

    return df


def get_lead_time_summary(df):
    """calculate shipment statics"""
    summary = (
        df.groupby(["lane", "transport_mode"])["lead_time_days"]
        .agg(
            shipment_count="count",
            average_lead_time="mean",
            minimum_lead_time="min",
            maximum_lead_time="max",
            lead_time_std="std",
        )
        .reset_index()
    )

    summary["lead_time_std"] = summary[
        "lead_time_std"
    ].fillna(0)

    summary["average_lead_time"] = summary[
        "average_lead_time"
    ].round(2)

    summary["lead_time_std"] = summary[
        "lead_time_std"
    ].round(2)

    return summary


def predict_lead_time(df, lane, transport_mode):
    """use shipment mean to predict next shipment lead time"""
    filtered = df[
        (df["lane"] == lane)
        & (df["transport_mode"] == transport_mode)
    ]

    if filtered.empty:
        raise ValueError(
            f"can not find the lane: {lane}, {transport_mode}"
        )

    predicted_days = filtered["lead_time_days"].mean()
    lead_time_std = filtered["lead_time_days"].std()

    if pd.isna(lead_time_std):
        lead_time_std = 0.0

    if predicted_days >= 20:
        risk_level = "high"
    elif predicted_days >= 7:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "lane": lane,
        "transport_mode": transport_mode,
        "predicted_lead_time_days": round(
            predicted_days, 2
        ),
        "lead_time_variability": round(
            lead_time_std, 2
        ),
        "risk_level": risk_level,
        "historical_shipments": len(filtered),
    }


if __name__ == "__main__":
    input_path = Path(
        "data/demo_baseline_365/shipments.csv"
    )

    shipments = load_shipments(input_path)

    print("=== Lead Time Summary ===")
    summary = get_lead_time_summary(shipments)
    print(summary.to_string(index=False))

    print("\n=== Lead Time Predictions ===")

    for _, row in summary.iterrows():
        prediction = predict_lead_time(
            shipments,
            row["lane"],
            row["transport_mode"],
        )
        print(prediction)
