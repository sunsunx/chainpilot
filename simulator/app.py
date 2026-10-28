from pathlib import Path
import re
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import altair as alt
import streamlit as st

from simulator.analytics import (
    get_inventory_summary,
    get_procurement_anomalies,
    load_daily_records,
)
from simulator.prediction import (
    get_lead_time_summary,
    load_shipments,
    predict_lead_time,
)
from simulator.langchain_rag import answer_question
from simulator.data_queries import (
    answer_chinese_policy_question,
    answer_data_question,
    answer_policy_question,
    build_data_context,
)


SCENARIO_DIRS = {
    "baseline": ROOT_DIR / "data/demo_baseline_365",
    "geopolitical": ROOT_DIR / "data/demo_geopolitical",
}


st.set_page_config(
    page_title="ChainPilot",
    layout="wide",
)

st.title("ChainPilot")
st.write(
    "A simple AI assistant for stock, suppliers, and delivery."
)

scenario_col, _ = st.columns([1, 4])

with scenario_col:
    scenario = st.selectbox(
        "Scenario",
        list(SCENARIO_DIRS.keys()),
    )

output_dir = SCENARIO_DIRS[scenario]
daily_path = output_dir / "daily_records.csv"
shipments_path = output_dir / "shipments.csv"

if not daily_path.exists():
    st.error(f"cannot find file: {daily_path}")
    st.stop()

if not shipments_path.exists():
    st.error(f"cannot find file: {shipments_path}")
    st.stop()


daily_records = load_daily_records(daily_path)
shipments = load_shipments(shipments_path)

inventory_summary = get_inventory_summary(daily_records)
lead_time_summary = get_lead_time_summary(shipments)
anomalies = get_procurement_anomalies(daily_records)


st.subheader(f"Scenario: {scenario}")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Average US Distribution Center Inventory",
    f"{inventory_summary['average_dc_inventory']:,.0f}",
)

col2.metric(
    "Final Customer Backlog",
    f"{inventory_summary['final_backlog']:,.0f}",
)

col3.metric(
    "Service Rate",
    f"{inventory_summary['final_fulfilment_rate']:.1%}",
)

col4.metric(
    "Total Cost",
    f"{inventory_summary['total_cost']:,.0f}",
)

st.divider()

st.header("Ask ChainPilot")

st.write(
    "Ask about stock, suppliers, or delivery."
)

with st.expander("Suggested questions", expanded=True):
    st.markdown(
        """
| English | 繁體中文 |
|---|---|
| How should we respond to a longer delivery time? | 供應商交期變長時，我們該怎麼做？ |
| What should we do when stock covers less than 7 days? | 庫存只剩不到 7 天時，我們該怎麼做？ |
| When should we use fast transport? | 什麼時候該使用快速運輸？ |
| How should we set safety stock? | 我們該如何設定安全庫存？ |
| What is the latest US distribution center inventory? | 目前美國配送中心有多少庫存？ |
| What is the average lead time for each route? | 每條運輸路線的平均交期是多少？ |
| Which route has the highest transport cost? | 哪條運輸路線的運輸成本最高？ |
"""
    )

question = st.text_area(
    "Question",
    placeholder="Example: What is the latest US distribution center inventory?",
)

if st.button("Ask AI"):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner(
            "Searching policy documents and generating an answer..."
        ):
            data_answer = answer_data_question(
                question,
                daily_records,
                shipments,
            )

            if data_answer is not None:
                answer = data_answer
                sources = ["simulation_data.csv"]
            else:
                policy_answer = answer_policy_question(question)

                if policy_answer is not None:
                    answer = policy_answer

                    question_lower = question.lower()

                    if "安全庫存" in question or "safety stock" in question_lower:
                        sources = ["safety_stock_policy.txt"]
                    elif (
                        "快速運輸" in question
                        or "快運" in question
                        or "fast transport" in question_lower
                        or "expedited transport" in question_lower
                        or "faster transport" in question_lower
                    ):
                        sources = ["procurement_policy.txt"]
                    elif "交期" in question and (
                        "變長" in question or "增加" in question
                    ) or (
                        ("delivery time" in question_lower or "lead time" in question_lower)
                        and any(
                            word in question_lower
                            for word in ("longer", "increase", "increases", "increased")
                        )
                    ):
                        sources = ["supplier_lead_time_policy.txt"]
                    elif (
                        "七天" in question
                        or "7天" in question
                        or "7 天" in question
                        or "less than 7" in question_lower
                        or "below 7" in question_lower
                    ):
                        sources = ["inventory_policy.txt"]
                    else:
                        sources = ["policy_documents"]
                else:
                    data_context = build_data_context(
                        daily_records,
                        shipments,
                    )
                    try:
                        answer, sources = answer_question(
                            question,
                            data_context=data_context,
                        )
                    except Exception:
                        answer = (
                            "The online demo cannot connect to the local Ollama model. "
                            "Try one of the suggested questions or run the app locally "
                            "with Ollama enabled."
                        )
                        sources = []

                    has_thai = any(
                        "\u0e00" <= character <= "\u0e7f"
                        for character in answer
                    )

                    if has_thai:
                        safe_answer = answer_chinese_policy_question(question)
                        if safe_answer is not None:
                            answer = safe_answer

        st.subheader("AI Answer")

        display_answer = re.sub(
            r"\s*[•●]\s*",
            "\n- ",
            answer,
        )
        display_answer = re.sub(
            r"\s+(?=\d+\.\s)",
            "\n",
            display_answer,
        )

        st.markdown(display_answer)

        st.subheader("Sources")
        st.text("\n".join(f"- {source}" for source in sources))

st.subheader("Customer Backlog Over Time")

backlog_data = daily_records[["day", "cu_backlog"]].rename(
    columns={"cu_backlog": "Customer Backlog"}
)

max_backlog = max(1, int(backlog_data["Customer Backlog"].max()))
max_day = int(backlog_data["day"].max())

backlog_chart = (
    alt.Chart(backlog_data)
    .mark_line()
    .encode(
        x=alt.X(
            "day:Q",
            title="Simulation Day",
            scale=alt.Scale(domain=[0, max_day]),
        ),
        y=alt.Y(
            "Customer Backlog:Q",
            title="Customer Backlog (units)",
            scale=alt.Scale(domain=[0, max_backlog]),
        ),
        tooltip=["day:Q", "Customer Backlog:Q"],
    )
    .properties(height=320)
)

st.altair_chart(backlog_chart, width="stretch")

if int(daily_records["cu_backlog"].max()) > 0:
    st.warning("Customer backlog is present in this scenario.")
else:
    st.success("No customer backlog was found in this scenario.")


st.subheader("Delivery Time Summary")

lead_time_display = lead_time_summary.copy()
lead_time_display["risk_level"] = lead_time_display.apply(
    lambda row: predict_lead_time(
        shipments,
        row["lane"],
        row["transport_mode"],
    )["risk_level"],
    axis=1,
)

route_names = {
    "supplier_to_hub": "Supplier to Export Hub",
    "hub_to_dc_sea": "Export Hub to Distribution Center",
    "dc_to_cu": "Distribution Center to Customer",
}

lead_time_display["route"] = lead_time_display["lane"].map(
    route_names
).fillna(lead_time_display["lane"])

lead_time_table = lead_time_display[
    [
        "route",
        "transport_mode",
        "shipment_count",
        "average_lead_time",
        "lead_time_std",
        "risk_level",
    ]
].rename(
    columns={
        "route": "Route",
        "transport_mode": "Transport Mode",
        "shipment_count": "Shipments",
        "average_lead_time": "Average Days",
        "lead_time_std": "Variation Days",
        "risk_level": "Risk Level",
    }
)

st.dataframe(
    lead_time_table,
    width="stretch",
)


st.subheader("Supply Risk Alerts")

if anomalies.empty:
    st.success("No supply risk alerts found.")
else:
    st.warning(
        f"{len(anomalies)} supply risk alerts found."
    )
    st.dataframe(
        anomalies,
        width="stretch",
    )


st.subheader("Download Daily Data")

csv_data = daily_records.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download Daily Data",
    data=csv_data,
    file_name=f"{scenario}_daily_records.csv",
    mime="text/csv",
)
