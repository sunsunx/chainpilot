from __future__ import annotations

from typing import Dict

from ..config import DECISION_MODE_RULE_BASED_BDI, PRODUCT_ID


class ReportingProcessMixin:
    def _calculate_daily_costs(
        self,
        production_cost_today: float,
        production_priority_cost: float,
        transport_cost_bf: float,
        nego_premium_bf: float,
    ) -> Dict[str, float]:
        holding_cost_today = self.holding_cost_today()
        backlog_cost_today = self.cu.backlog * self.backlog_penalty_per_unit_day
        self.cml_holding_cost += holding_cost_today
        self.cml_backlog_cost += backlog_cost_today
        transport_cost_today = self.cml_transport_cost - transport_cost_bf
        nego_premium_cost_today = self.cml_nego_premium_cost - nego_premium_bf
        total_cost_today = (
            production_cost_today
            + production_priority_cost
            + holding_cost_today
            + backlog_cost_today
            + transport_cost_today
            + nego_premium_cost_today
        )
        cml_total_cost = (
            self.cml_production_cost
            + self.cml_transport_cost
            + self.cml_holding_cost
            + self.cml_backlog_cost
            + self.cml_nego_premium_cost
            + self.cml_production_priority_cost
        )

        fulfilment_rate = 1.0
        if self.cml_demand > 0:
            fulfilment_rate = self.cml_shipped_to_market / self.cml_demand
            fulfilment_rate = max(0.0, min(1.0, fulfilment_rate))

        return {
            "holding_cost_today": holding_cost_today,
            "backlog_cost_today": backlog_cost_today,
            "transport_cost_today": transport_cost_today,
            "nego_premium_cost_today": nego_premium_cost_today,
            "total_cost_today": total_cost_today,
            "cml_total_cost": cml_total_cost,
            "fulfilment_rate": fulfilment_rate,
        }

    def _record_daily_metrics(
        self,
        day: int,
        arrival_totals: Dict[str, int],
        arrived_units: int,
        production: Dict[str, float | int],
        market: Dict[str, int],
        dc: Dict[str, float | int | bool],
        logistics_decision: Dict[str, float | int | str],
        logistics: Dict[str, float | int | str],
        hub: Dict[str, float | int | bool | str],
        costs: Dict[str, float],
    ) -> None:
        supplier = self.nodes["supplier_tw"]
        dc_agent = self.nodes["regional_dc_us"]
        hub_agent = self.nodes["export_hub_tw"]

        self.daily_records.append(
            {
                "day": day,
                "scenario": self.scenario_config.name,
                "product": PRODUCT_ID,
                "demand": market["demand"],
                "expected_daily_demand": dc["expected_daily_demand"],
                "arrived_units": arrived_units,
                "arrived_to_hub": arrival_totals["arrived_to_hub"],
                "arrived_to_dc": arrival_totals["arrived_to_dc"],
                "arrived_to_cu": arrival_totals["arrived_to_cu"],
                "wafer_started_units": production["wafer_started_units"],
                "production_planner_intention": self.production_planner.intention[
                    "action"
                ],
                "production_planner_decision_source": self.decision_trace.get(
                    "production_planning_agent", {}
                ).get("source", DECISION_MODE_RULE_BASED_BDI),
                "production_planner_decision_reason": self.decision_trace.get(
                    "production_planning_agent", {}
                ).get("reason", ""),
                "planned_wafer_starts": production["plan_wafer_starts"],
                "production_overtime_multiplier": production[
                    "production_overtime_multiplier"
                ],
                "production_priority_cost_today": production[
                    "production_priority_cost"
                ],
                "completed_production_units": production[
                    "completed_production_units"
                ],
                "produced_units": production["completed_production_units"],
                "shipped_supplier_to_hub": hub["shipped_supplier_to_hub"],
                "shipped_hub_to_dc": logistics["shipped_hub_to_dc"],
                "shipped_hub_to_dc_air": logistics["shipped_hub_to_dc_air"],
                "shipped_hub_to_dc_sea": logistics["shipped_hub_to_dc_sea"],
                "shipped_dc_to_cu": market["shipped_to_market"],
                "dc_intention": dc_agent.intention["action"],
                "dc_decision_source": self.decision_trace.get(
                    "regional_dc_us", {}
                ).get("source", DECISION_MODE_RULE_BASED_BDI),
                "dc_decision_reason": self.decision_trace.get(
                    "regional_dc_us", {}
                ).get("reason", ""),
                "dc_intended_order_qty": dc["dc_order"],
                "dc_scheduled_sea_replenishment_qty": dc[
                    "scheduled_sea_replenishment_qty"
                ],
                "dc_total_replenishment_request": dc[
                    "dc_total_replenishment_request"
                ],
                "dc_inv_position": dc["dc_inv_position"],
                "dc_inv_gap": dc["dc_inv_gap"],
                "dc_backlog_pressure": dc["dc_backlog_pressure"],
                "dc_days_of_supply": dc["dc_days_of_supply"],
                "dc_on_hand_days_of_supply": dc["dc_on_hand_days_of_supply"],
                "dc_inv_position_days_of_supply": dc[
                    "dc_inv_position_days_of_supply"
                ],
                "dc_urgent_air_needed": bool(dc["urgent_air_needed"]),
                "dc_air_request_qty": logistics["dc_air_request_qty"],
                "dc_sea_request_qty": logistics["dc_sea_request_qty"],
                "dc_negod_offer_qty": logistics["dc_offer"],
                "dc_air_negod_offer_qty": logistics["dc_air_offer"],
                "dc_sea_negod_offer_qty": logistics["dc_sea_offer"],
                "dc_nego_premium_cost": logistics["dc_premium_cost"],
                "logistics_coordination_intention": logistics_decision["action"],
                "logistics_coordination_decision_source": self.decision_trace.get(
                    "logistics_coordination_agent", {}
                ).get("source", DECISION_MODE_RULE_BASED_BDI),
                "logistics_coordination_decision_reason": self.decision_trace.get(
                    "logistics_coordination_agent", {}
                ).get("reason", ""),
                "hub_to_dc_transport_mode": logistics["effective_transport_mode"],
                "hub_to_dc_cost_multiplier": logistics_decision["cost_multiplier"],
                "hub_to_dc_lead_time_multiplier": logistics_decision["LT_multiplier"],
                "hub_to_dc_air_cost_multiplier": logistics["air_cost_multiplier"],
                "hub_to_dc_air_lead_time_multiplier": logistics[
                    "air_LT_multiplier"
                ],
                "hub_to_dc_sea_cost_multiplier": logistics["sea_cost_multiplier"],
                "hub_to_dc_sea_lead_time_multiplier": logistics[
                    "sea_LT_multiplier"
                ],
                "hub_to_dc_air_capacity": self.lane_capacity("hub_to_dc_air"),
                "hub_to_dc_sea_capacity": self.lane_capacity("hub_to_dc_sea"),
                "hub_intention": hub_agent.intention["action"],
                "hub_decision_source": self.decision_trace.get(
                    "export_hub_tw", {}
                ).get("source", DECISION_MODE_RULE_BASED_BDI),
                "hub_decision_reason": self.decision_trace.get(
                    "export_hub_tw", {}
                ).get("reason", ""),
                "hub_raw_intended_order_qty": hub["hub_raw_order"],
                "hub_daily_request_cap": hub["hub_daily_request_cap"],
                "hub_intended_order_qty": hub["hub_order"],
                "hub_inv_position": hub["hub_inv_position"],
                "hub_inv_gap": hub["hub_inv_gap"],
                "hub_negod_offer_qty": hub["hub_offer"],
                "hub_nego_premium_cost": hub["hub_premium_cost"],
                "supplier_to_hub_transport_mode": str(hub["supplier_to_hub_mode"]),
                "supplier_to_hub_capacity_today": hub[
                    "supplier_to_hub_capacity_today"
                ],
                "supplier_to_hub_surge_used": bool(
                    hub["use_supplier_to_hub_surge"]
                ),
                "cu_backlog": self.cu.backlog,
                "cu_in_transit": self.inbound_qty("oem_cu"),
                "fulfilment_rate_to_date": costs["fulfilment_rate"],
                "supplier_on_hand": self.nodes["supplier_tw"].on_hand,
                "supplier_finished_days": hub["supplier_finished_days"],
                "hub_gap_days": hub["hub_gap_days"],
                "supplier_wafer_wip": supplier.wip_units("wafer_fab"),
                "supplier_packaging_wip": supplier.wip_units("packaging_test"),
                "supplier_total_wip": supplier.wip_units(),
                "hub_on_hand": self.nodes["export_hub_tw"].on_hand,
                "dc_on_hand": self.nodes["regional_dc_us"].on_hand,
                "in_transit_total": sum(s.qty for s in self.shipments),
                "hub_to_dc_capacity": (
                    self.lane_capacity("hub_to_dc_air")
                    + self.lane_capacity("hub_to_dc_sea")
                ),
                "dc_to_cu_capacity": self.lane_capacity("dc_to_cu"),
                "production_cost_today": production["production_cost_today"],
                "holding_cost_today": costs["holding_cost_today"],
                "transport_cost_today": costs["transport_cost_today"],
                "transport_cost_to_date": self.cml_transport_cost,
                "backlog_cost_today": costs["backlog_cost_today"],
                "nego_premium_cost_today": costs["nego_premium_cost_today"],
                "total_cost_today": costs["total_cost_today"],
                "cml_production_cost": self.cml_production_cost,
                "cml_transport_cost": self.cml_transport_cost,
                "cml_holding_cost": self.cml_holding_cost,
                "cml_backlog_cost": self.cml_backlog_cost,
                "cml_nego_premium_cost": self.cml_nego_premium_cost,
                "cml_production_priority_cost": self.cml_production_priority_cost,
                "cml_total_cost": costs["cml_total_cost"],
            }
        )
