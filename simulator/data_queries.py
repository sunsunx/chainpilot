"""Create a small, readable data summary for the AI assistant."""

import pandas as pd


ROUTE_NAMES = {
    "supplier_to_hub": "Taiwan supplier to Taiwan export hub",
    "hub_to_dc_sea": "Taiwan export hub to US distribution center by sea",
    "hub_to_dc_air": "Taiwan export hub to US distribution center by air",
    "dc_to_cu": "US distribution center to customer",
}

CHINESE_ROUTE_NAMES = {
    "supplier_to_hub": "台灣供應商到台灣出口中心",
    "hub_to_dc_sea": "台灣出口中心到美國配送中心（海運）",
    "hub_to_dc_air": "台灣出口中心到美國配送中心（空運）",
    "dc_to_cu": "美國配送中心到客戶",
}


def answer_data_question(
    question: str,
    daily_records: pd.DataFrame,
    shipments: pd.DataFrame,
) -> str | None:
    """Answer supported numeric questions without asking the LLM to calculate."""

    question_lower = question.lower()
    latest = daily_records.iloc[-1]
    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)

    asks_lead_time = (
        (
            ("lead time" in question_lower or "delivery time" in question_lower)
            and any(
                word in question_lower
                for word in (
                    "average",
                    "current",
                    "latest",
                    "what is",
                    "how many",
                )
            )
        )
        or "平均交期" in question
        or "平均交貨時間" in question
        or "目前交期" in question
        or "最新交期" in question
        or "交期是多少" in question
    )

    if asks_lead_time:
        grouped = shipments.groupby(
            ["lane", "transport_mode"],
            as_index=False,
        ).agg(
            average_lead_time=("lead_time_days", "mean"),
        )

        if is_chinese:
            lines = ["各運輸路線的平均交期如下："]
            for _, row in grouped.iterrows():
                route_name = CHINESE_ROUTE_NAMES.get(
                    row["lane"],
                    row["lane"],
                )
                lines.append(
                    f"- {route_name}：{row['average_lead_time']:.2f} 天"
                )
            return "\n".join(lines)

        lines = ["Average lead time by route:"]
        for _, row in grouped.iterrows():
            route_name = ROUTE_NAMES.get(row["lane"], row["lane"])
            lines.append(
                f"- {route_name}: {row['average_lead_time']:.2f} days"
            )
        return "\n".join(lines)

    question_no_space = question.replace(" ", "")

    asks_inventory = (
        (
            ("inventory" in question_lower or "stock" in question_lower)
            and any(
                word in question_lower
                for word in (
                    "current",
                    "latest",
                    "today",
                    "how much",
                    "what is",
                    "total",
                    "average",
                    "level",
                )
            )
        )
        or (
            "庫存" in question_no_space
            and any(
                word in question_no_space
                for word in (
                    "目前",
                    "現在",
                    "今天",
                    "最新",
                    "多少",
                    "數量",
                    "總量",
                    "平均",
                )
            )
        )
    )

    asks_inventory_action = (
        "7 days" in question_lower
        or "less than 7" in question_lower
        or "七天" in question
        or "7天" in question
        or "該怎麼做" in question
        or "應該怎麼做" in question
    )

    if asks_inventory and not asks_inventory_action:
        if is_chinese:
            return (
                "目前庫存如下：\n"
                f"- 美國配送中心：{latest['dc_on_hand']:.0f} 單位\n"
                f"- 台灣出口中心：{latest['hub_on_hand']:.0f} 單位\n"
                f"- 台灣供應商：{latest['supplier_on_hand']:.0f} 單位"
            )

        return (
            "Current inventory:\n"
            f"- US distribution center: {latest['dc_on_hand']:.0f} units\n"
            f"- Taiwan export hub: {latest['hub_on_hand']:.0f} units\n"
            f"- Taiwan supplier: {latest['supplier_on_hand']:.0f} units"
        )

    asks_cost = (
        "highest transport cost" in question_lower
        or "most expensive route" in question_lower
        or "成本最高" in question
        or "運輸成本最高" in question
    )

    asks_average_cost = (
        "average transport cost" in question_lower
        or "average cost per shipment" in question_lower
        or "平均運輸成本" in question
        or "平均每批" in question
    )

    if asks_cost:
        grouped = shipments.groupby(
            "lane",
            as_index=False,
        ).agg(
            total_transport_cost=("transport_cost", "sum"),
            average_transport_cost=("transport_cost", "mean"),
            shipment_count=("transport_cost", "count"),
        )
        highest = grouped.sort_values(
            "average_transport_cost" if asks_average_cost else "total_transport_cost",
            ascending=False,
        ).iloc[0]
        route_name = (
            CHINESE_ROUTE_NAMES.get(highest["lane"], highest["lane"])
            if is_chinese
            else ROUTE_NAMES.get(highest["lane"], highest["lane"])
        )

        if is_chinese:
            metric = "平均每批運輸成本" if asks_average_cost else "總運輸成本"
            return (
                "運輸成本最高的路線是：\n"
                f"- {route_name}\n"
                f"- 比較指標：{metric}\n"
                f"- 總運輸成本：{highest['total_transport_cost']:.2f}\n"
                f"- 平均每批運輸成本：{highest['average_transport_cost']:.2f}\n"
                f"- 運輸批次：{int(highest['shipment_count'])}"
            )

        metric = (
            "average transport cost per shipment"
            if asks_average_cost
            else "total transport cost"
        )
        return (
            "The route with the highest transport cost is:\n"
            f"- {route_name}\n"
            f"- Compared metric: {metric}\n"
            f"- Total transport cost: {highest['total_transport_cost']:.2f}\n"
            f"- Average cost per shipment: {highest['average_transport_cost']:.2f}\n"
            f"- Shipments: {int(highest['shipment_count'])}"
        )

    return None


def answer_chinese_policy_question(question: str) -> str | None:
    """Provide a safe Traditional Chinese fallback for common policy questions."""

    if not any("\u4e00" <= character <= "\u9fff" for character in question):
        return None

    if "快速運輸" in question or "快運" in question:
        return (
            "當服務風險高時，可以考慮使用快速運輸。\n\n"
            "建議行動：\n"
            "1. 檢查客戶延遲的影響。\n"
            "2. 比較快速運輸的額外費用與客戶延遲成本。\n"
            "3. 重新評估供應鏈和運輸方式。"
        )

    if "交期" in question and ("變長" in question or "增加" in question):
        return (
            "供應商交期變長時，應先檢查庫存和供應風險。\n\n"
            "建議行動：\n"
            "1. 檢查安全庫存是否足夠。\n"
            "2. 向供應商確認新的交期承諾。\n"
            "3. 評估替代供應商或替代運輸方式。"
        )

    if "庫存" in question and (
        "七天" in question
        or "7天" in question
        or "7 天" in question
    ):
        return (
            "當庫存少於七天的需求量時，應升級供應風險。\n\n"
            "建議行動：\n"
            "1. 檢查進貨中的貨物。\n"
            "2. 確認供應商產能。\n"
            "3. 評估運輸方式和客戶延遲。"
        )

    if "安全庫存" in question:
        return (
            "安全庫存應反映需求變化、供應商交期變化和服務要求。\n\n"
            "建議行動：\n"
            "1. 檢查需求波動。\n"
            "2. 檢查交期波動。\n"
            "3. 不要在沒有分析前直接增加庫存。"
        )

    return None


def build_data_context(
    daily_records: pd.DataFrame,
    shipments: pd.DataFrame,
) -> str:
    """Return current simulation data in a format that an LLM can use."""

    latest = daily_records.iloc[-1]

    lines = [
        "Simulation data for the selected scenario:",
        f"Latest simulated day: {int(latest['day'])}",
        f"Current US distribution center inventory: {latest['dc_on_hand']:.0f} units",
        f"Current Taiwan export hub inventory: {latest['hub_on_hand']:.0f} units",
        f"Current Taiwan supplier inventory: {latest['supplier_on_hand']:.0f} units",
        f"Current customer backlog: {latest['cu_backlog']:.0f} units",
        f"Current US distribution center days of supply: {latest['dc_on_hand_days_of_supply']:.2f} days",
        f"Current service rate: {latest['fulfilment_rate_to_date']:.1%}",
        "",
        "Lead-time and transport-cost summary:",
    ]

    grouped = shipments.groupby(
        ["lane", "transport_mode"],
        as_index=False,
    ).agg(
        shipment_count=("lead_time_days", "count"),
        average_lead_time_days=("lead_time_days", "mean"),
        lead_time_std_days=("lead_time_days", "std"),
        total_transport_cost=("transport_cost", "sum"),
        average_transport_cost=("transport_cost", "mean"),
    )

    for _, row in grouped.iterrows():
        variation = row["lead_time_std_days"]
        if pd.isna(variation):
            variation = 0.0

        route_name = ROUTE_NAMES.get(
            row["lane"],
            str(row["lane"]),
        )

        lines.append(
            f"- Route {route_name}: "
            f"average lead time {row['average_lead_time_days']:.2f} days; "
            f"variation {variation:.2f} days; "
            f"average transport cost {row['average_transport_cost']:.2f}; "
            f"total transport cost {row['total_transport_cost']:.2f}; "
            f"shipments {int(row['shipment_count'])}."
        )

    lines.extend(
        [
            "",
            "Data limitation:",
            "The simulation data has transport costs, but it does not have supplier purchase prices.",
            "Do not call a transport cost a supplier purchase price.",
        ]
    )

    return "\n".join(lines)
