from __future__ import annotations

import math
from typing import Dict


class LogisticsProcessMixin:
    def _process_logistics(
        self,
        logistics_decision: Dict[str, float | int | str],
        dc_total_replenishment_request: int,
        expected_daily_demand: float,
    ) -> Dict[str, float | int | str]:
        coordination_action = str(logistics_decision["action"])
        coordination_cost_multiplier = float(logistics_decision["cost_multiplier"])
        coordination_LT_multiplier = float(logistics_decision["LT_multiplier"])
        effective_transport_mode = {
            "no_transport_request": "none",
            "sea_standard": "sea",
            "split_air_sea": "air_sea_split",
            "air_expedite": "air",
            "constrained_sea": "sea_constrained",
        }.get(coordination_action, "none")

        air_cost_multiplier = (
            coordination_cost_multiplier
            if coordination_action in {"split_air_sea", "air_expedite"}
            else 1.0
        )
        air_LT_multiplier = (
            coordination_LT_multiplier
            if coordination_action in {"split_air_sea", "air_expedite"}
            else 1.0
        )
        sea_cost_multiplier = (
            coordination_cost_multiplier
            if coordination_action in {"sea_standard", "constrained_sea"}
            else 1.0
        )
        sea_LT_multiplier = (
            coordination_LT_multiplier
            if coordination_action in {"sea_standard", "constrained_sea"}
            else 1.0
        )

        urgent_air_cover_days = 3
        dc_air_request_qty = 0
        if (
            coordination_action == "split_air_sea"
            and dc_total_replenishment_request > 0
        ):
            dc_air_request_qty = min(
                dc_total_replenishment_request,
                int(math.ceil(expected_daily_demand * urgent_air_cover_days)),
            )
        elif coordination_action == "air_expedite":
            dc_air_request_qty = dc_total_replenishment_request
        elif coordination_action in {"sea_standard", "constrained_sea"}:
            dc_air_request_qty = 0
        elif coordination_action == "no_transport_request":
            dc_air_request_qty = 0

        if coordination_action == "no_transport_request":
            dc_sea_request_qty = 0
        else:
            dc_sea_request_qty = max(
                0, dc_total_replenishment_request - dc_air_request_qty
            )

        dc_air_offer, dc_air_cost_multiplier, dc_air_premium_cost = self.nego_order(
            requester="regional_dc_us",
            lane_name="hub_to_dc_air",
            requested_qty=dc_air_request_qty,
            priority=str(logistics_decision["priority"]),
            transport_mode="air",
            cost_multiplier_override=air_cost_multiplier,
        )
        shipped_hub_to_dc_air = self.create_shipment(
            "hub_to_dc_air",
            dc_air_offer,
            cost_multiplier=dc_air_cost_multiplier,
            transport_mode="air",
            LT_multiplier=air_LT_multiplier,
        )

        sea_mode = (
            "sea_constrained" if coordination_action == "constrained_sea" else "sea"
        )
        dc_sea_offer, dc_sea_cost_multiplier, dc_sea_premium_cost = self.nego_order(
            requester="regional_dc_us",
            lane_name="hub_to_dc_sea",
            requested_qty=dc_sea_request_qty,
            priority=str(logistics_decision["priority"]),
            transport_mode=sea_mode,
            cost_multiplier_override=sea_cost_multiplier,
        )
        shipped_hub_to_dc_sea = self.create_shipment(
            "hub_to_dc_sea",
            dc_sea_offer,
            cost_multiplier=dc_sea_cost_multiplier,
            transport_mode=sea_mode,
            LT_multiplier=sea_LT_multiplier,
        )

        return {
            "effective_transport_mode": effective_transport_mode,
            "air_cost_multiplier": air_cost_multiplier,
            "air_LT_multiplier": air_LT_multiplier,
            "sea_cost_multiplier": sea_cost_multiplier,
            "sea_LT_multiplier": sea_LT_multiplier,
            "dc_air_request_qty": dc_air_request_qty,
            "dc_sea_request_qty": dc_sea_request_qty,
            "dc_offer": dc_air_offer + dc_sea_offer,
            "dc_air_offer": dc_air_offer,
            "dc_sea_offer": dc_sea_offer,
            "dc_premium_cost": dc_air_premium_cost + dc_sea_premium_cost,
            "shipped_hub_to_dc": shipped_hub_to_dc_air + shipped_hub_to_dc_sea,
            "shipped_hub_to_dc_air": shipped_hub_to_dc_air,
            "shipped_hub_to_dc_sea": shipped_hub_to_dc_sea,
        }

    def _process_logistics_coordination(
        self,
        dc: Dict[str, float | int | bool],
    ) -> tuple[
        Dict[str, float | int | str],
        Dict[str, float | int | str],
    ]:
        dc_agent = self.nodes["regional_dc_us"]
        requested_qty = dc["dc_total_replenishment_request"]
        urgent_air_needed = bool(dc["urgent_air_needed"])
        self.logistics_coordination.update_beliefs(
            requested_qty=requested_qty,
            priority=(
                "high" if urgent_air_needed else str(dc_agent.intention["priority"])
            ),
        )
        self.logistics_coordination.evaluate_desires()
        self.logistics_coordination.select_intention()
        decision = self.logistics_coordination.execute_intention()
        logistics = self._process_logistics(
            decision,
            requested_qty,
            float(dc["expected_daily_demand"]),
        )
        return decision, logistics

    def _process_hub_replenishment(self) -> Dict[str, float | int | bool | str]:
        hub_agent = self.nodes["export_hub_tw"]
        hub_agent.update_beliefs()
        hub_agent.evaluate_desires()
        hub_agent.select_intention()
        hub_raw_order = hub_agent.execute_intention()
        hub_daily_request_cap = 800
        hub_order = min(hub_raw_order, hub_daily_request_cap)
        hub_inv_position = float(hub_agent.beliefs.get("inv_position", 0))
        hub_inv_gap = max(0.0, hub_agent.order_up_to - hub_inv_position)
        supplier_finished_days = float(
            self.production_planner.desires.get("supplier_finished_days", 0.0)
        )
        hub_gap_days = float(self.production_planner.desires.get("hub_gap_days", 0.0))
        supplier_to_hub_normal_capacity = int(
            self.lanes["supplier_to_hub"]["daily_capacity"]
        )
        supplier_to_hub_surge_capacity = int(
            self.lanes["supplier_to_hub"].get(
                "surge_capacity",
                supplier_to_hub_normal_capacity,
            )
        )
        use_supplier_to_hub_surge = (
            hub_agent.intention.get("priority") == "high"
            or hub_inv_position <= 1000
        )
        supplier_to_hub_capacity_today = (
            supplier_to_hub_surge_capacity
            if use_supplier_to_hub_surge
            else supplier_to_hub_normal_capacity
        )
        supplier_to_hub_mode = (
            "taiwan_local_surge"
            if use_supplier_to_hub_surge
            else "taiwan_local_normal"
        )
        hub_offer, hub_cost_multiplier, hub_premium_cost = self.nego_order(
            requester="export_hub_tw",
            lane_name="supplier_to_hub",
            requested_qty=hub_order,
            priority=str(hub_agent.intention["priority"]),
            transport_mode=supplier_to_hub_mode,
            capacity_override=supplier_to_hub_capacity_today,
        )
        shipped_supplier_to_hub = self.create_shipment(
            "supplier_to_hub",
            hub_offer,
            cost_multiplier=hub_cost_multiplier,
            transport_mode=supplier_to_hub_mode,
            capacity_override=supplier_to_hub_capacity_today,
        )

        return {
            "hub_raw_order": hub_raw_order,
            "hub_daily_request_cap": hub_daily_request_cap,
            "hub_order": hub_order,
            "hub_inv_position": hub_inv_position,
            "hub_inv_gap": hub_inv_gap,
            "supplier_finished_days": supplier_finished_days,
            "hub_gap_days": hub_gap_days,
            "supplier_to_hub_capacity_today": supplier_to_hub_capacity_today,
            "use_supplier_to_hub_surge": use_supplier_to_hub_surge,
            "supplier_to_hub_mode": supplier_to_hub_mode,
            "hub_offer": hub_offer,
            "hub_premium_cost": hub_premium_cost,
            "shipped_supplier_to_hub": shipped_supplier_to_hub,
        }
