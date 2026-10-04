"""Core selection logic.

    total_expected_time = waiting_time_for_next_truck + road_travel_time

The company with the MINIMUM total_expected_time wins - NOT the nearest one.

Pipeline per company (each step is its own small function):
    parse/validate  ->  scheduler.next_departure  ->  route_fn  ->  CandidateResult
then `select_best` picks the winner and `explain_selection` says why.

TIE-BREAKING RULE (deterministic, never random). Candidates are ordered by:
    1. total expected time   (compared in whole seconds)
    2. road distance         (shorter wins; compared in whole metres)
    3. company id            (alphabetical)
    4. company name          (alphabetical)

Times are compared in whole seconds and distances in whole metres so tiny
floating-point noise from a routing API cannot turn a true tie into a fake win.

Delivery-time interpretation (V1): the clock starts at `now`; we wait for the
next truck, and the truck then drives the road route company -> customer
without stops or handling time.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Iterable, Mapping

from config import TIMEZONE
from inventory import WarehouseIndex, check_availability
from models import Customer, LogisticsCompany, Order, ValidationError, Warehouse
from routing import RouteResult, RoutingError, get_route
from scheduler import next_departure

logger = logging.getLogger(__name__)

RouteFn = Callable[..., RouteResult]  # (origin: Coordinates, destination: Coordinates) -> RouteResult


class CandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    NO_SCHEDULE = "unavailable_no_schedule"
    OUT_OF_STOCK = "unavailable_out_of_stock"
    INVALID_DATA = "invalid_data"
    ROUTE_ERROR = "route_error"


@dataclass(frozen=True)
class CandidateResult:
    company_id: str
    company_name: str
    status: CandidateStatus
    reason: str | None = None            # why a company is unavailable
    distance_km: float | None = None
    next_departure: datetime | None = None
    waiting_seconds: int | None = None
    travel_seconds: int | None = None
    warehouse_id: str | None = None      # V2: warehouse the order ships from

    @property
    def is_candidate(self) -> bool:
        return self.status is CandidateStatus.CANDIDATE

    @property
    def total_seconds(self) -> int | None:
        if not self.is_candidate:
            return None
        return self.waiting_seconds + self.travel_seconds  # type: ignore[operator]

    @property
    def waiting_hours(self) -> float | None:
        return None if self.waiting_seconds is None else self.waiting_seconds / 3600

    @property
    def travel_hours(self) -> float | None:
        return None if self.travel_seconds is None else self.travel_seconds / 3600

    @property
    def total_hours(self) -> float | None:
        return None if self.total_seconds is None else self.total_seconds / 3600

    @property
    def distance_m(self) -> int | None:
        return None if self.distance_km is None else round(self.distance_km * 1000)

    def sort_key(self) -> tuple:
        """Selection order: time, then distance, then id, then name (see module docstring)."""
        return (self.total_seconds, self.distance_m, self.company_id, self.company_name)


@dataclass(frozen=True)
class OptimizationResult:
    customer_id: str
    evaluated_at: datetime
    candidates: tuple[CandidateResult, ...]   # every company, in input order
    selected: CandidateResult
    explanation: tuple[str, ...] = field(default_factory=tuple)
    order: Order | None = None


class NoViableLogisticsError(Exception):
    """No company could be evaluated. Carries the per-company reasons."""

    def __init__(self, message: str, candidates: Iterable[CandidateResult] = ()) -> None:
        super().__init__(message)
        self.candidates = tuple(candidates)


# --------------------------------------------------------------------------- #
# Step functions
# --------------------------------------------------------------------------- #
def evaluate_company(customer: Customer, company_input: LogisticsCompany | Mapping,
                     now: datetime, route_fn: RouteFn = get_route,
                     order: Order | None = None, index: WarehouseIndex | None = None) -> CandidateResult:
    """Evaluate ONE company. Never raises for bad data or routing failures."""
    # 1. validate
    if isinstance(company_input, LogisticsCompany):
        company = company_input
    else:
        raw_id = company_input.get("id") if isinstance(company_input, Mapping) else None
        raw_name = company_input.get("name") if isinstance(company_input, Mapping) else None
        try:
            company = LogisticsCompany.from_dict(company_input)
        except ValidationError as exc:
            cid = str(raw_id) if raw_id not in (None, "") else "<unknown>"
            return CandidateResult(cid, str(raw_name or cid), CandidateStatus.INVALID_DATA, reason=str(exc))

    # 1b. V2 stock check (only when an order is given) - BEFORE schedule/routing,
    #     so companies that cannot fulfil the order cost no routing calls.
    warehouse_id = None
    if order is not None:
        availability = check_availability(company, order, index)
        if not availability.ok:
            return CandidateResult(company.id, company.name, CandidateStatus.OUT_OF_STOCK,
                                   reason=availability.reason)
        warehouse_id = availability.warehouse_id

    # 2. schedule: next truck + waiting time
    departure = next_departure(company.truck_schedule, now)
    if departure is None:
        return CandidateResult(company.id, company.name, CandidateStatus.NO_SCHEDULE,
                               reason="company has no truck departures (empty schedule)")

    # 3. road route (isolated in routing.py)
    try:
        route = route_fn(company.coordinates, customer.coordinates)
    except RoutingError as exc:
        return CandidateResult(company.id, company.name, CandidateStatus.ROUTE_ERROR,
                               reason=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # one broken company must never crash the whole run
        logger.warning("Unexpected routing failure for %s", company.id, exc_info=True)
        return CandidateResult(company.id, company.name, CandidateStatus.ROUTE_ERROR,
                               reason=f"unexpected {type(exc).__name__}: {exc}")

    # 4. combine
    return CandidateResult(
        company.id, company.name, CandidateStatus.CANDIDATE,
        distance_km=route.distance_km,
        next_departure=departure.departure,
        waiting_seconds=round(departure.waiting.total_seconds()),
        travel_seconds=round(route.travel_time_hours * 3600),
        warehouse_id=warehouse_id,
    )


def select_best(candidates: Iterable[CandidateResult]) -> CandidateResult | None:
    """Minimum total expected time, with the documented deterministic tie-breaks."""
    valid = [c for c in candidates if c.is_candidate]
    return min(valid, key=CandidateResult.sort_key) if valid else None


def _h(hours: float) -> str:
    return f"{hours:.1f} h"


def explain_selection(selected: CandidateResult, candidates: Iterable[CandidateResult]) -> tuple[str, ...]:
    """Human-readable reasons, making it obvious WHY this company won."""
    valid = [c for c in candidates if c.is_candidate]
    lines = [f"Lowest expected delivery time among {len(valid)} candidate(s): "
             f"{_h(selected.total_hours)} "
             f"(waiting {_h(selected.waiting_hours)} + road travel {_h(selected.travel_hours)})."]

    nearest = min(valid, key=lambda c: (c.distance_m, c.company_id))
    if selected.distance_m <= nearest.distance_m:
        lines.append("It is also the geographically nearest candidate.")
    else:
        lines.append(
            f"It is {selected.distance_km - nearest.distance_km:.1f} km FARTHER than the nearest "
            f"candidate ({nearest.company_name}, {nearest.distance_km:.1f} km), but arrives "
            f"{_h(nearest.total_hours - selected.total_hours)} sooner: the nearest one would take "
            f"{_h(nearest.total_hours)} (waiting {_h(nearest.waiting_hours)} + travel "
            f"{_h(nearest.travel_hours)}).")

    if selected.warehouse_id:
        lines.append(f"Stock confirmed: every ordered item is available in warehouse {selected.warehouse_id}.")
    out = [c.company_name for c in candidates if c.status is CandidateStatus.OUT_OF_STOCK]
    if out:
        lines.append("Excluded before the time comparison (cannot fulfil the order from stock): "
                     + ", ".join(out) + ".")

    ties = [c for c in valid if c is not selected and c.total_seconds == selected.total_seconds]
    if ties:
        names = ", ".join(c.company_name for c in ties)
        if any(c.distance_m == selected.distance_m for c in ties):
            lines.append(f"Tied on total time with {names} and on distance; "
                         "chosen by company id (deterministic tie-break).")
        else:
            lines.append(f"Tied on total time with {names}; chosen for the shorter road distance "
                         "(tie-break rule).")
    return tuple(lines)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def choose_best_logistics(customer: Customer | Mapping, companies: Iterable[LogisticsCompany | Mapping],
                          now: datetime | None = None,
                          route_fn: RouteFn = get_route, order: Order | Mapping | None = None,
                          warehouses: Iterable[Warehouse | Mapping] | None = None) -> OptimizationResult:
    """Evaluate every company and pick the one with the minimum total expected time.

    * `customer` / `companies` may be model objects or raw dicts (validated here).
    * Invalid customer -> ValidationError (nothing can be computed without it).
    * Bad/unroutable companies are marked unavailable; the others are still evaluated.
    * No company usable -> NoViableLogisticsError (never a fabricated answer).
    * V2: if `order` is given, `warehouses` is required and only companies whose linked
      warehouses can fulfil the whole order from stock are compared. No order = V1 behaviour.
    * `now` defaults to the current time in Africa/Cairo; it is read ONCE so every
      company is judged against the same instant.
    """
    if not isinstance(customer, Customer):
        customer = Customer.from_dict(customer)
    now = now if now is not None else datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("`now` must be a timezone-aware datetime")

    index = None
    if order is not None:
        if not isinstance(order, Order):
            order = Order.from_dict(order)
        if warehouses is None:
            raise ValueError("`warehouses` must be provided when an order is given")
        index = WarehouseIndex(warehouses)

    results = tuple(evaluate_company(customer, c, now, route_fn, order, index) for c in companies)
    if not results:
        raise NoViableLogisticsError("No logistics companies were provided.")

    best = select_best(results)
    if best is None:
        details = "; ".join(f"{r.company_name} [{r.status.value}]: {r.reason}" for r in results)
        if all(r.status is CandidateStatus.OUT_OF_STOCK for r in results):
            head = "The order cannot be fulfilled: no partner warehouse has all the items in stock."
        else:
            head = f"No logistics company could be evaluated for customer {customer.id}."
        raise NoViableLogisticsError(f"{head} {details}", results)

    return OptimizationResult(customer.id, now, results, best, explain_selection(best, results), order)
