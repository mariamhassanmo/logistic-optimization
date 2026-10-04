"""V2 stock check: can a company fulfil the order from a warehouse it works with?

Rules (single-source fulfilment):
  * A company can fulfil the order if ONE of its linked warehouses is active and has
    enough AVAILABLE stock (on_hand - reserved) for EVERY order line. No split shipments.
  * If several linked warehouses qualify, the lowest warehouse id is used (deterministic).
  * Unknown / inactive / corrupted warehouses are never used and are explained in the reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from models import LogisticsCompany, Order, ValidationError, Warehouse


@dataclass(frozen=True)
class Availability:
    ok: bool
    warehouse_id: str | None = None
    reason: str | None = None


class WarehouseIndex:
    """Validated warehouses by id. One bad record never breaks the others."""

    def __init__(self, warehouses: Iterable[Warehouse | Mapping]) -> None:
        self.warehouses: dict[str, Warehouse] = {}
        self.errors: dict[str, str] = {}   # warehouse id -> why it cannot be used
        for i, raw in enumerate(warehouses, 1):
            try:
                wh = raw if isinstance(raw, Warehouse) else Warehouse.from_dict(raw)
            except ValidationError as exc:
                rid = raw.get("id") if isinstance(raw, Mapping) else None
                key = str(rid).strip() if rid not in (None, "") else f"<warehouse #{i}>"
                self.errors[key] = f"invalid warehouse data: {exc}"
                continue
            if wh.id in self.errors:
                continue
            if wh.id in self.warehouses:  # ambiguous inventory: trust neither record
                del self.warehouses[wh.id]
                self.errors[wh.id] = "duplicate warehouse id (inventory is ambiguous)"
                continue
            self.warehouses[wh.id] = wh


def check_availability(company: LogisticsCompany, order: Order, index: WarehouseIndex) -> Availability:
    if not company.warehouse_ids:
        return Availability(False, reason="company is not linked to any warehouse")
    problems: list[str] = []
    for wid in sorted(company.warehouse_ids):
        if wid in index.errors:
            problems.append(f"{wid}: {index.errors[wid]}")
            continue
        wh = index.warehouses.get(wid)
        if wh is None:
            problems.append(f"{wid}: unknown warehouse")
            continue
        if not wh.active:
            problems.append(f"{wid}: warehouse is inactive")
            continue
        short = []
        for line in order.lines:
            level = wh.stock.get(line.sku)
            have = level.available if level else 0
            if have < line.quantity:
                short.append(f"{line.sku} needs {line.quantity}, available {have}")
        if not short:
            return Availability(True, warehouse_id=wid)
        problems.append(f"{wid}: " + ", ".join(short))
    return Availability(False, reason="no linked warehouse can fulfil the whole order from stock ("
                                      + "; ".join(problems) + ")")
