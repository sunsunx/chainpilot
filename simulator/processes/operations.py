from __future__ import annotations

import math
from typing import Dict


class OperationsProcessMixin:
    def _process_arrivals(self) -> tuple[dict[str, int], int]:
        arrival_totals = self.receive_arrivals()
        arrived_units = sum(arrival_totals.values())
        return arrival_totals, arrived_units

    def _process_production(self) -> Dict[str, float | int]:
        supplier = self.nodes["supplier_tw"]
        completed_production_units = supplier.advance_production_pipeline(
            self.scenario_config
        )
        self.production_planner.update_beliefs()
        self.production_planner.evaluate_desires()
        self.production_planner.select_intention()
        plan_wafer_starts, production_overtime_multiplier = (
            self.production_planner.execute_intention()
        )
        wafer_started_units = supplier.start_production(
            self.scenario_config,
            plan_qty=plan_wafer_starts,
            overtime_multiplier=production_overtime_multiplier,
        )
        production_cost_today = wafer_started_units * self.production_cost_per_unit
        production_priority_cost = 0.0
        if self.production_planner.intention["priority"] == "high":
            production_priority_cost = wafer_started_units * 0.75
        self.cml_production_cost += production_cost_today
        self.cml_production_priority_cost += production_priority_cost

        return {
            "completed_production_units": completed_production_units,
            "plan_wafer_starts": plan_wafer_starts,
            "production_overtime_multiplier": production_overtime_multiplier,
            "wafer_started_units": wafer_started_units,
            "production_cost_today": production_cost_today,
            "production_priority_cost": production_priority_cost,
        }

    def _process_market_demand(self, day: int) -> Dict[str, int]:
        demand = self.cu.generate_demand(day)
        self.cu.backlog += demand

        market_ship_request = max(0, self.cu.backlog)
        shipped_to_market = self.create_shipment("dc_to_cu", market_ship_request)
        self.cu.backlog = max(0, self.cu.backlog - shipped_to_market)
        self.cml_demand += demand
        self.cml_shipped_to_market += shipped_to_market

        return {
            "demand": demand,
            "shipped_to_market": shipped_to_market,
        }

    def _process_dc_replenishment(
        self,
        day: int,
    ) -> Dict[str, float | int | bool]:
        dc_agent = self.nodes["regional_dc_us"]
        dc_agent.update_beliefs(cu_backlog=self.cu.backlog)
        dc_agent.evaluate_desires()
        dc_agent.select_intention()
        dc_order = dc_agent.execute_intention()
        expected_daily_demand = (
            self.cu.base_daily_demand * self.scenario_config.demand_multiplier
        )

        dc_inv_position = dc_agent.inv_position()
        dc_inv_gap = max(0, dc_agent.order_up_to - dc_inv_position)
        periodic_review_days = 7
        scheduled_sea_replenishment_qty = 0
        if day % periodic_review_days == 0:
            scheduled_sea_replenishment_qty = min(
                int(math.ceil(expected_daily_demand * periodic_review_days)),
                dc_inv_gap,
            )
        dc_total_replenishment_request = min(
            max(dc_order, scheduled_sea_replenishment_qty),
            dc_inv_gap,
        )
        dc_on_hand_days_of_supply = dc_agent.on_hand / max(
            1.0, expected_daily_demand
        )
        dc_inv_position_days_of_supply = dc_inv_position / max(
            1.0, expected_daily_demand
        )
        dc_days_of_supply = dc_inv_position_days_of_supply
        dc_backlog_pressure = self.cu.backlog / max(1.0, expected_daily_demand)
        urgent_air_needed = (
            dc_backlog_pressure >= 7
            or dc_days_of_supply <= 7
            or dc_agent.intention["action"] == "nego_expedite"
        )

        return {
            "dc_order": dc_order,
            "expected_daily_demand": expected_daily_demand,
            "dc_inv_position": dc_inv_position,
            "dc_inv_gap": dc_inv_gap,
            "scheduled_sea_replenishment_qty": scheduled_sea_replenishment_qty,
            "dc_total_replenishment_request": dc_total_replenishment_request,
            "dc_on_hand_days_of_supply": dc_on_hand_days_of_supply,
            "dc_inv_position_days_of_supply": (
                dc_inv_position_days_of_supply
            ),
            "dc_days_of_supply": dc_days_of_supply,
            "dc_backlog_pressure": dc_backlog_pressure,
            "urgent_air_needed": urgent_air_needed,
        }
