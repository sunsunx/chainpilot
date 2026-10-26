from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProductionLot:
    stage: str
    qty: int
    remaining_days: int


@dataclass
class Shipment:
    created_day: int
    arrival_day: int
    source: str
    destination: str
    product: str
    qty: int
    lane: str
    transport_mode: str
    lead_time_days: int
    transport_cost: float


@dataclass
class NegoRecord:
    day: int
    requester: str
    responder: str
    lane: str
    requested_qty: int
    offered_qty: int
    priority: str
    transport_mode: str
    unit_transport_cost: float
    production_premium_per_unit: float
    accepted: bool
    decision: str
