from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence

from mesa import Model

from .agents import (
    LogisticsCoordinationAgent,
    OEMDemandAgent,
    ProductionPlanningAgent,
    SupplyChainNode,
)
from .config import (
    DECISION_MODE_LLM,
    DECISION_MODE_RULE_BASED_BDI,
    PRODUCT_ID,
    SCENARIOS,
    validate_decision_mode,
)
from .entities import NegoRecord, ProductionLot, Shipment
from .llm import LLMDecisionEngine
from .processes import LogisticsProcessMixin, OperationsProcessMixin, ReportingProcessMixin


class SemiSCM(
    OperationsProcessMixin,
    LogisticsProcessMixin,
    ReportingProcessMixin,
    Model,
):
    def __init__(
        self,
        scenario_name: str,
        days: int,
        seed: int = 2025,
        decision_mode: str = DECISION_MODE_RULE_BASED_BDI,
        llm_model: str = "llama3.2:3b",
        demand_sequence: Optional[Sequence[int]] = None,
    ) -> None:
        super().__init__(seed=seed)
        if scenario_name not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        self.scenario_config = SCENARIOS[scenario_name]
        self.decision_mode = validate_decision_mode(decision_mode)
        llm_enabled = self.decision_mode == DECISION_MODE_LLM
        self.llm_model = llm_model if llm_enabled else ""
        self.llm_provider = "ollama" if llm_enabled else "none"
        self.llm_decision_engine = LLMDecisionEngine(
            decision_mode=self.decision_mode,
            model_name=llm_model,
        )
        self.decision_trace: Dict[str, Dict[str, str]] = {}
        self.days = days
        self.current_day = 0
        self.shipments: List[Shipment] = []
        self.daily_records: List[dict] = []
        self.shipment_records: List[dict] = []
        self.nego_records: List[dict] = []
        self.cml_production_cost = 0.0
        self.cml_transport_cost = 0.0
        self.cml_holding_cost = 0.0
        self.cml_backlog_cost = 0.0
        self.cml_nego_premium_cost = 0.0
        self.cml_production_priority_cost = 0.0
        self.cml_demand = 0
        self.cml_shipped_to_market = 0

        self.nodes: Dict[str, SupplyChainNode] = {
            "supplier_tw": SupplyChainNode(
                self,
                node="supplier_tw",
                initial_inv=5000,
                reorder_point=0,
                order_up_to=0,
                daily_capacity=180,
                handling_days=2,
            ),
            "export_hub_tw": SupplyChainNode(
                self,
                node="export_hub_tw",
                initial_inv=3500,
                reorder_point=3000,
                order_up_to=7000,
                handling_days=1,
            ),
            "regional_dc_us": SupplyChainNode(
                self,
                node="regional_dc_us",
                initial_inv=6000,
                reorder_point=3500,
                order_up_to=8000,
                handling_days=1,
            ),
        }
        self.cu = OEMDemandAgent(
            self,
            base_daily_demand=120,
            demand_sequence=demand_sequence,
        )

        self.lanes = {
            "supplier_to_hub": {
                "source": "supplier_tw",
                "destination": "export_hub_tw",
                "base_LT": 3,
                "daily_capacity": 200,
                "surge_capacity": 800,
                "kind": "international",
                "cost_per_unit": 0.40,
            },
            "hub_to_dc_air": {
                "source": "export_hub_tw",
                "destination": "regional_dc_us",
                "base_LT": 5,
                "daily_capacity": 180,
                "kind": "international",
                "cost_per_unit": 5.00,
            },
            "hub_to_dc_sea": {
                "source": "export_hub_tw",
                "destination": "regional_dc_us",
                "base_LT": 25,
                "daily_capacity": 900,
                "kind": "international",
                "cost_per_unit": 1.20,
            },
            "dc_to_cu": {
                "source": "regional_dc_us",
                "destination": "oem_cu",
                "base_LT": 2,
                "daily_capacity": 500,
                "kind": "domestic",
                "cost_per_unit": 0.65,
            },
        }

        self.production_cost_per_unit = 12.0
        self.holding_cost_per_unit_day = {
            "supplier_tw": 0.020,
            "export_hub_tw": 0.025,
            "regional_dc_us": 0.035,
        }
        self.backlog_penalty_per_unit_day = 4.0

        self.seed_initial_supplier_wip()

        self.production_planner = ProductionPlanningAgent(self)
        self.logistics_coordination = LogisticsCoordinationAgent(self)

        self._lane_used_today: Dict[str, int] = {}

    def seed_initial_supplier_wip(self) -> None:
        supplier = self.nodes["supplier_tw"]
        daily_lot_size = supplier.daily_capacity
        for remaining_days in range(1, self.scenario_config.packaging_test_days + 1):
            supplier.production_wip.append(
                ProductionLot(
                    stage="packaging_test",
                    qty=daily_lot_size,
                    remaining_days=remaining_days,
                )
            )
        for remaining_days in range(1, self.scenario_config.wafer_fab_min_days + 1):
            supplier.production_wip.append(
                ProductionLot(
                    stage="wafer_fab",
                    qty=daily_lot_size,
                    remaining_days=remaining_days,
                )
            )

    def choose_llm_intention(
        self,
        agent_name: str,
        beliefs: Dict[str, Any],
        desires: Dict[str, Any],
        rule_intention: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        intention = self.llm_decision_engine.choose_intention(
            agent_name=agent_name,
            beliefs=beliefs,
            desires=desires,
            rule_intention=rule_intention,
            schema=schema,
        )
        self.decision_trace[agent_name] = {
            "source": self.llm_decision_engine.last_source,
            "reason": self.llm_decision_engine.last_reason,
        }
        return intention

    def inbound_qty(self, node: str) -> int:
        return sum(s.qty for s in self.shipments if s.destination == node)

    def lane_capacity(
        self,
        lane_name: str,
        capacity_override: int | None = None,
    ) -> int:
        lane = self.lanes[lane_name]
        scenario = self.scenario_config
        base_capacity = (
            int(capacity_override)
            if capacity_override is not None
            else int(lane["daily_capacity"])
        )
        if lane_name in {"hub_to_dc_air", "hub_to_dc_sea"}:
            factor = scenario.hub_to_dc_capacity_factor
        elif lane_name == "dc_to_cu":
            factor = scenario.dc_to_cu_capacity_factor
        else:
            factor = 1.0

        if (
            scenario.disruption_start is not None
            and scenario.disruption_end is not None
            and scenario.disruption_start <= self.current_day <= scenario.disruption_end
        ):
            if lane_name in {"hub_to_dc_air", "hub_to_dc_sea"}:
                factor *= scenario.disruption_capacity_factor

        return max(0, int(round(base_capacity * factor)))

    def lane_LT(
        self,
        lane_name: str,
        source_node: SupplyChainNode,
        LT_multiplier: float = 1.0,
    ) -> int:
        lane = self.lanes[lane_name]
        scenario = self.scenario_config
        if lane["kind"] == "international":
            multiplier = scenario.international_leadtime_multiplier
        else:
            multiplier = scenario.domestic_leadtime_multiplier
        noisy = self.random.normalvariate(
            lane["base_LT"] * multiplier * LT_multiplier,
            max(0.4, lane["base_LT"] * multiplier * LT_multiplier * 0.12),
        )
        return max(1, int(math.ceil(noisy + source_node.handling_days)))

    def nego_order(
        self,
        requester: str,
        lane_name: str,
        requested_qty: int,
        priority: str,
        transport_mode: str = "standard",
        cost_multiplier_override: float | None = None,
        capacity_override: int | None = None,
    ) -> tuple[int, float, float]:
        lane = self.lanes[lane_name]
        responder = lane["source"]
        source = self.nodes[responder]
        used = self._lane_used_today.get(lane_name, 0)
        lane_remaining = max(
            0,
            self.lane_capacity(lane_name, capacity_override=capacity_override) - used,
        )
        offered_qty = min(requested_qty, source.on_hand, lane_remaining)

        expedite = priority == "high"
        cost_multiplier = (
            cost_multiplier_override
            if cost_multiplier_override is not None
            else (1.45 if expedite else 1.0)
        )
        production_premium = 1.50 if expedite and responder == "supplier_tw" else 0.0
        accepted = offered_qty > 0
        if requested_qty <= 0:
            decision = "no_request"
        elif not accepted:
            decision = "rejected_no_capacity_or_inv"
        elif expedite:
            decision = "accepted_expedite"
        else:
            decision = "accepted_normal"

        unit_transport_cost = float(lane["cost_per_unit"]) * cost_multiplier
        record = NegoRecord(
            day=self.current_day,
            requester=requester,
            responder=responder,
            lane=lane_name,
            requested_qty=requested_qty,
            offered_qty=offered_qty,
            priority=priority,
            transport_mode=transport_mode,
            unit_transport_cost=unit_transport_cost,
            production_premium_per_unit=production_premium,
            accepted=accepted,
            decision=decision,
        )
        self.nego_records.append(asdict(record))
        premium_cost = offered_qty * production_premium
        self.cml_nego_premium_cost += premium_cost
        return offered_qty, cost_multiplier, premium_cost

    def create_shipment(
        self,
        lane_name: str,
        requested_qty: int,
        cost_multiplier: float = 1.0,
        transport_mode: str = "standard",
        LT_multiplier: float = 1.0,
        capacity_override: int | None = None,
    ) -> int:
        lane = self.lanes[lane_name]
        source_id = lane["source"]
        destination_id = lane["destination"]
        source = self.nodes[source_id]

        used = self._lane_used_today.get(lane_name, 0)
        remaining_capacity = max(
            0,
            self.lane_capacity(lane_name, capacity_override=capacity_override) - used,
        )
        qty = min(requested_qty, remaining_capacity)
        qty = source.remove_inv(qty)
        if qty <= 0:
            return 0

        LT = self.lane_LT(
            lane_name,
            source,
            LT_multiplier=LT_multiplier,
        )
        transport_cost = qty * float(lane["cost_per_unit"]) * cost_multiplier
        shipment = Shipment(
            created_day=self.current_day,
            arrival_day=self.current_day + LT,
            source=source_id,
            destination=destination_id,
            product=PRODUCT_ID,
            qty=qty,
            lane=lane_name,
            transport_mode=transport_mode,
            lead_time_days=LT,
            transport_cost=transport_cost,
        )
        self.shipments.append(shipment)
        self.shipment_records.append(asdict(shipment))
        self.cml_transport_cost += transport_cost
        self._lane_used_today[lane_name] = used + qty
        return qty

    def holding_cost_today(self) -> float:
        return sum(
            node.on_hand * self.holding_cost_per_unit_day[node_id]
            for node_id, node in self.nodes.items()
        )

    def receive_arrivals(self) -> Dict[str, int]:
        arrived = [s for s in self.shipments if s.arrival_day <= self.current_day]
        self.shipments = [s for s in self.shipments if s.arrival_day > self.current_day]
        arrival_totals = {
            "arrived_to_hub": 0,
            "arrived_to_dc": 0,
            "arrived_to_cu": 0,
        }
        for shipment in arrived:
            if shipment.destination == "oem_cu":
                arrival_totals["arrived_to_cu"] += shipment.qty
            else:
                if shipment.destination == "export_hub_tw":
                    arrival_totals["arrived_to_hub"] += shipment.qty
                elif shipment.destination == "regional_dc_us":
                    arrival_totals["arrived_to_dc"] += shipment.qty
                self.nodes[shipment.destination].add_inv(shipment.qty)
        return arrival_totals

    def _reset_day(self) -> tuple[float, float]:
        self._lane_used_today = {}
        self.decision_trace = {}
        transport_cost_bf = self.cml_transport_cost
        nego_premium_bf = self.cml_nego_premium_cost

        return (
            transport_cost_bf, nego_premium_bf
        )

    def step(self) -> None:
        day = self.current_day
        transport_cost_bf, nego_premium_bf = self._reset_day()

        arrival_totals, arrived_units = self._process_arrivals()
        production_state = self._process_production()

        market_state = self._process_market_demand(day)

        dc_state = self._process_dc_replenishment(day)
        logistics_decision, logistics_state = (
            self._process_logistics_coordination(dc_state)
        )

        hub_state = self._process_hub_replenishment()

        cost_state = self._calculate_daily_costs(
            float(production_state["production_cost_today"]),
            float(production_state["production_priority_cost"]),
            transport_cost_bf,
            nego_premium_bf,
        )

        self._record_daily_metrics(
            day,
            arrival_totals,
            arrived_units,
            production_state,
            market_state,
            dc_state,
            logistics_decision,
            logistics_state,
            hub_state,
            cost_state,
        )
        self.current_day += 1

    def run_model(self) -> None:
        for _ in range(self.days):
            self.step()
