from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from mesa import Agent

from .config import DECISION_MODE_BASIC_BASELINE, PRODUCT_ID, ScenarioConfig
from .entities import ProductionLot

if TYPE_CHECKING:
    from .model import SemiSCM


class SupplyChainNode(Agent):
    def __init__(
        self,
        model: "SemiSCM",
        node: str,
        initial_inv: int,
        reorder_point: int,
        order_up_to: int,
        daily_capacity: int = 0,
        handling_days: int = 0,
    ) -> None:
        super().__init__(model)
        self.node = node
        self.inv = {PRODUCT_ID: initial_inv}
        self.reorder_point = reorder_point
        self.order_up_to = order_up_to
        self.daily_capacity = daily_capacity
        self.handling_days = handling_days
        self.production_wip: List[ProductionLot] = []
        self.beliefs: Dict[str, float | int | str] = {}
        self.desires: Dict[str, float | int | str] = {}
        self.intention: Dict[str, float | int | str] = {"action": "hold", "qty": 0}

    @property
    def on_hand(self) -> int:
        return int(self.inv.get(PRODUCT_ID, 0))

    def add_inv(self, qty: int) -> None:
        self.inv[PRODUCT_ID] = self.on_hand + int(qty)

    def remove_inv(self, qty: int) -> int:
        shipped = min(self.on_hand, max(0, int(qty)))
        self.inv[PRODUCT_ID] = self.on_hand - shipped
        return shipped

    # production pipeline
    def start_production(
        self,
        scenario: ScenarioConfig,
        plan_qty: int | None = None,
        overtime_multiplier: float = 1.0,
    ) -> int:
        if self.daily_capacity <= 0:
            return 0
        normal_capacity = int(
            round(self.daily_capacity * scenario.supplier_capacity_factor)
        )
        bounded_overtime = max(1.0, min(1.20, overtime_multiplier))
        capacity = int(math.ceil(normal_capacity * bounded_overtime))
        if plan_qty is None:
            started = normal_capacity
        else:
            started = min(max(0, int(plan_qty)), capacity)
        fab_days = self.model.random.randint(
            scenario.wafer_fab_min_days,
            scenario.wafer_fab_max_days,
        )
        fab_days = int(math.ceil(fab_days * scenario.production_leadtime_multiplier))
        self.production_wip.append(
            ProductionLot(
                stage="wafer_fab",
                qty=started,
                remaining_days=max(1, fab_days),
            )
        )
        return started

    def advance_production_pipeline(self, scenario: ScenarioConfig) -> int:
        completed = 0
        next_wip: List[ProductionLot] = []
        for lot in self.production_wip:
            lot.remaining_days -= 1
            if lot.remaining_days > 0:
                next_wip.append(lot)
                continue

            if lot.stage == "wafer_fab":
                package_days = int(
                    math.ceil(
                        scenario.packaging_test_days
                        * scenario.production_leadtime_multiplier
                    )
                )
                next_wip.append(
                    ProductionLot(
                        stage="packaging_test",
                        qty=lot.qty,
                        remaining_days=max(1, package_days),
                    )
                )
            else:
                completed += lot.qty

        self.production_wip = next_wip
        if completed > 0:
            self.add_inv(completed)
        return completed

    def wip_units(self, stage: str | None = None) -> int:
        return sum(
            lot.qty
            for lot in self.production_wip
            if stage is None or lot.stage == stage
        )

    def inv_position(self) -> int:
        return self.on_hand + self.model.inbound_qty(self.node)

    def update_beliefs(self, cu_backlog: int = 0) -> None:
        expected_demand = (
            self.model.cu.base_daily_demand
            * self.model.scenario_config.demand_multiplier
        )
        self.beliefs = {
            "on_hand": self.on_hand,
            "inbound": self.model.inbound_qty(self.node),
            "inv_position": self.inv_position(),
            "cu_backlog": cu_backlog,
            "expected_daily_demand": expected_demand,
        }

    def evaluate_desires(self) -> None:
        inv_position = float(self.beliefs["inv_position"])
        expected_demand = max(1.0, float(self.beliefs["expected_daily_demand"]))
        cu_backlog = float(self.beliefs["cu_backlog"])
        self.desires = {
            "inv_gap": max(0.0, self.order_up_to - inv_position),
            "days_of_supply": inv_position / expected_demand,
            "backlog_pressure": cu_backlog / expected_demand,
            "cost_priority": "normal",
        }

    def select_intention(self) -> None:
        inv_position = float(self.beliefs["inv_position"])
        inv_gap = int(round(float(self.desires["inv_gap"])))
        backlog_pressure = float(self.desires["backlog_pressure"])

        basic_baseline_mode = self.model.decision_mode == DECISION_MODE_BASIC_BASELINE
        if inv_position >= self.reorder_point:
            rule_intention = {"action": "hold", "qty": 0, "priority": "normal"}
        elif backlog_pressure >= 7 and not basic_baseline_mode:
            rule_intention = {
                "action": "nego_expedite",
                "qty": inv_gap,
                "priority": "high",
            }
        else:
            rule_intention = {
                "action": "replenish",
                "qty": inv_gap,
                "priority": "normal",
            }
        self.intention = self.model.choose_llm_intention(
            agent_name=self.node,
            beliefs=self.beliefs,
            desires=self.desires,
            rule_intention=rule_intention,
            schema={
                "allowed": {
                    "action": ["hold", "replenish", "nego_expedite"],
                    "priority": ["normal", "high"],
                },
                "numeric_bounds": {
                    "qty": [0, max(0, inv_gap)],
                },
            },
        )

        # LLM intention selection.

    def execute_intention(self) -> int:
        max_replenishment = max(
            0,
            int(self.order_up_to - self.inv_position()),
        )
        if self.intention.get("action") == "hold":
            return 0
        requested_qty = max(0, int(self.intention.get("qty", 0)))
        return min(requested_qty, max_replenishment)


# CU market: demand Agent
class OEMDemandAgent(Agent):
    def __init__(
        self,
        model: "SemiSCM",
        base_daily_demand: int,
        demand_sequence: Optional[Sequence[int]] = None,
    ) -> None:
        super().__init__(model)
        self.base_daily_demand = base_daily_demand
        self.demand_sequence = (
            list(demand_sequence) if demand_sequence is not None else None
        )
        self.backlog = 0

    def generate_demand(self, day: int) -> int:
        if self.demand_sequence is not None:
            if day >= len(self.demand_sequence):
                raise ValueError(
                    f"Demand sequence has {len(self.demand_sequence)} days, "
                    f"but day {day} was requested."
                )
            return int(self.demand_sequence[day])
        scenario = self.model.scenario_config
        weekly = 1.0 + 0.08 * math.sin(2 * math.pi * day / 7)
        quarterly = 1.0 + 0.12 * math.sin(2 * math.pi * day / 91)
        mean = self.base_daily_demand * scenario.demand_multiplier
        sampled = self.model.random.normalvariate(
            mean * weekly * quarterly,
            mean * scenario.demand_cv,
        )
        demand = max(0, int(round(sampled)))
        if self.model.random.random() < scenario.spike_probability:
            demand += self.model.random.randint(scenario.spike_min, scenario.spike_max)
        return demand


# BDI agent
class ProductionPlanningAgent(Agent):
    def __init__(self, model: "SemiSCM") -> None:
        super().__init__(model)
        self.node = "production_planning_agent"
        self.beliefs: Dict[str, float | int | str] = {}
        self.desires: Dict[str, float | int | str] = {}
        self.intention: Dict[str, float | int | str] = {
            "action": "normal_release",
            "plan_qty": 0,
            "priority": "normal",
        }

    def update_beliefs(self) -> None:
        supplier = self.model.nodes["supplier_tw"]
        hub = self.model.nodes["export_hub_tw"]
        expected_demand = (
            self.model.cu.base_daily_demand
            * self.model.scenario_config.demand_multiplier
        )
        self.beliefs = {
            "supplier_FG": supplier.on_hand,
            "supplier_wafer_wip": supplier.wip_units("wafer_fab"),
            "supplier_packaging_wip": supplier.wip_units("packaging_test"),
            "hub_inv_position": hub.inv_position(),
            "hub_reorder_point": hub.reorder_point,
            "expected_daily_demand": expected_demand,
            "available_capacity": int(
                round(
                    supplier.daily_capacity
                    * self.model.scenario_config.supplier_capacity_factor
                )
            ),
        }

    def evaluate_desires(self) -> None:
        expected_demand = max(1.0, float(self.beliefs["expected_daily_demand"]))
        hub_gap = max(
            0.0,
            float(self.beliefs["hub_reorder_point"])
            - float(self.beliefs["hub_inv_position"]),
        )
        finished_days = float(self.beliefs["supplier_FG"]) / expected_demand
        self.desires = {
            "keep_pipeline_loaded": True,
            "hub_gap_days": hub_gap / expected_demand,
            "supplier_finished_days": finished_days,
            "avoid_upstream_overstock": finished_days >= 120,
        }

    def select_intention(self) -> None:
        capacity = int(self.beliefs["available_capacity"])
        hub_gap_days = float(self.desires["hub_gap_days"])
        finished_days = float(self.desires["supplier_finished_days"])

        basic_baseline_mode = self.model.decision_mode == DECISION_MODE_BASIC_BASELINE
        if basic_baseline_mode:
            rule_intention = {
                "action": "normal_release",
                "plan_qty": capacity,
                "priority": "normal",
            }
        elif finished_days >= 120 and hub_gap_days <= 2:
            rule_intention = {
                "action": "reduce_release",
                "plan_qty": int(math.ceil(capacity * 0.50)),
                "priority": "low",
            }
        elif hub_gap_days >= 7 or finished_days <= 14:
            rule_intention = {
                "action": "priority_release",
                "plan_qty": capacity,
                "priority": "high",
            }
        else:
            rule_intention = {
                "action": "normal_release",
                "plan_qty": capacity,
                "priority": "normal",
            }
        self.intention = self.model.choose_llm_intention(
            agent_name=self.node,
            beliefs=self.beliefs,
            desires=self.desires,
            rule_intention=rule_intention,
            schema={
                "allowed": {
                    "action": [
                        "normal_release",
                        "priority_release",
                        "reduce_release",
                    ],
                    "priority": ["low", "normal", "high"],
                },
                "numeric_bounds": {"plan_qty": [0, math.ceil(capacity * 1.20)]},
            },
        )

    def execute_intention(self) -> tuple[int, float]:
        capacity = int(self.beliefs["available_capacity"])
        if self.intention["priority"] == "high":
            overtime_multiplier = 1.15
            max_qty = int(math.ceil(capacity * overtime_multiplier))
            qty = min(
                int(self.intention["plan_qty"]),
                max_qty,
            )
        elif self.intention["action"] == "reduce_release":
            overtime_multiplier = 1.0
            qty = min(
                int(self.intention["plan_qty"]),
                int(math.ceil(capacity * 0.50)),
            )
        else:
            overtime_multiplier = 1.0
            qty = int(self.intention["plan_qty"])
        return qty, overtime_multiplier


# BDI agent: transport, capacity, cost, and lead time
class LogisticsCoordinationAgent(Agent):
    def __init__(self, model: "SemiSCM") -> None:
        super().__init__(model)
        self.node = "logistics_coordination_agent"
        self.beliefs: Dict[str, float | int | str] = {}
        self.desires: Dict[str, float | int | str] = {}
        self.intention: Dict[str, float | int | str] = {
            "action": "sea_standard",
            "priority": "normal",
        }

    def update_beliefs(self, requested_qty: int, priority: str) -> None:
        expected_demand = (
            self.model.cu.base_daily_demand
            * self.model.scenario_config.demand_multiplier
        )
        self.beliefs = {
            "requested_qty": requested_qty,
            "priority": priority,
            "cu_backlog": self.model.cu.backlog,
            "expected_daily_demand": expected_demand,
            "hub_to_dc_air_capacity": self.model.lane_capacity("hub_to_dc_air"),
            "hub_to_dc_sea_capacity": self.model.lane_capacity("hub_to_dc_sea"),
            "scenario": self.model.scenario_config.name,
        }

    def evaluate_desires(self) -> None:
        expected_demand = max(1.0, float(self.beliefs["expected_daily_demand"]))
        backlog_pressure = float(self.beliefs["cu_backlog"]) / expected_demand
        self.desires = {
            "backlog_pressure": backlog_pressure,
            "minimize_cost": backlog_pressure < 7,
            "minimize_delay": backlog_pressure >= 7,
        }

    def select_intention(self) -> None:
        requested_qty = int(self.beliefs["requested_qty"])
        priority = str(self.beliefs["priority"])
        backlog_pressure = float(self.desires["backlog_pressure"])
        scenario_name = str(self.beliefs["scenario"])

        basic_baseline_mode = self.model.decision_mode == DECISION_MODE_BASIC_BASELINE
        if requested_qty <= 0:
            rule_intention = {
                "action": "no_transport_request",
                "priority": "normal",
            }
        elif basic_baseline_mode:
            rule_intention = {
                "action": "sea_standard",
                "priority": "normal",
            }
        elif priority == "high" or backlog_pressure >= 7:
            rule_intention = {
                "action": "split_air_sea",
                "priority": "high",
            }
        elif scenario_name == "geopolitical":
            rule_intention = {
                "action": "constrained_sea",
                "priority": "normal",
            }
        else:
            rule_intention = {
                "action": "sea_standard",
                "priority": "normal",
            }
        self.intention = self.model.choose_llm_intention(
            agent_name=self.node,
            beliefs=self.beliefs,
            desires=self.desires,
            rule_intention=rule_intention,
            schema={
                "allowed": {
                    "action": [
                        "no_transport_request",
                        "sea_standard",
                        "split_air_sea",
                        "air_expedite",
                        "constrained_sea",
                    ],
                    "priority": ["normal", "high"],
                },
            },
        )

    def execute_intention(self) -> Dict[str, float | int | str]:
        action = str(self.intention["action"])
        parameters = {
            "no_transport_request": (1.0, 1.0),
            "sea_standard": (1.0, 1.0),
            "constrained_sea": (1.15, 1.80),
            "split_air_sea": (2.20, 0.35),
            "air_expedite": (2.20, 0.35),
        }
        cost_multiplier, LT_multiplier = parameters[action]
        return {
            "action": action,
            "priority": str(self.intention["priority"]),
            "cost_multiplier": cost_multiplier,
            "LT_multiplier": LT_multiplier,
        }
