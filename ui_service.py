"""Glue between the Streamlit UI and the optimizer. No Streamlit imports here.

Reuses choose_best_logistics / scheduler / stock check unchanged. The only new piece is
`CityRoadProvider`, an offline RoutingProvider (approximate road-km table between cities)
so the demo runs without internet. Swap it for OpenRouteServiceProvider for live routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import partial

import pandas as pd

import ui_data
from config import TIMEZONE
from models import Coordinates, Warehouse
from optimizer import (CandidateResult, CandidateStatus, NoViableLogisticsError, OptimizationResult,
                       choose_best_logistics)
from routing import RouteResult, RoutingNoRouteError, RoutingProvider, approx_distance_m, get_route

AVG_SPEED_KMH = 80.0     # assumed average driving speed
CITY_OVERHEAD_H = 0.25   # assumed city entry/exit time added to every trip
INTRA_CITY_KM = 12.0     # hub -> customer inside the same city
MAX_SNAP_KM = 60.0       # coordinates farther than this from every known city are "off network"

COLUMNS = ["Company", "Location", "Product availability", "Next truck", "Waiting (h)", "Distance (km)",
           "Travel time (h)", "Total expected (h)", "Status"]


class CityRoadProvider(RoutingProvider):
    """Offline provider: snaps each point to its nearest city, looks up road-km, converts to hours."""

    def __init__(self) -> None:
        self._centers = {n: Coordinates(*c) for n, c in ui_data.CITIES.items()}
        self._roads = {frozenset(pair): km for pair, km in ui_data.ROAD_KM.items()}

    def _city(self, point: Coordinates) -> str:
        name, dist_m = min(((n, approx_distance_m(point, c)) for n, c in self._centers.items()),
                           key=lambda item: item[1])
        if dist_m / 1000 > MAX_SNAP_KM:
            raise RoutingNoRouteError("location is outside the demo road network")
        return name

    def fetch_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        a, b = self._city(origin), self._city(destination)
        km = INTRA_CITY_KM if a == b else self._roads.get(frozenset((a, b)))
        if km is None:
            raise RoutingNoRouteError(f"no road data between {a} and {b}")
        return RouteResult(distance_km=float(km), travel_time_hours=km / AVG_SPEED_KMH + CITY_OVERHEAD_H)


_WAREHOUSES = {w.id: w for w in (Warehouse.from_dict(d) for d in ui_data.WAREHOUSES)}
_COMPANY = {c["id"]: c for c in ui_data.COMPANIES}


def fmt_hours(hours: float) -> str:
    minutes = round(hours * 60)
    return f"{hours:.1f} h ({minutes // 60}h {minutes % 60:02d}m)"


def _availability(company_id: str, sku: str, quantity: int) -> str:
    best = 0
    for wid in _COMPANY[company_id]["warehouse_ids"]:
        level = _WAREHOUSES[wid].stock.get(sku)
        best = max(best, level.available if level else 0)
    return f"In stock ({best} units)" if best >= quantity else "Out of stock"


def _next_truck(c: CandidateResult, now: datetime) -> str:
    days = (c.next_departure.date() - now.astimezone(TIMEZONE).date()).days
    day = "Today" if days == 0 else "Tomorrow" if days == 1 else f"{c.next_departure:%a %d %b}"
    return f"{day} {c.next_departure:%H:%M}"


_EXCLUDED = {CandidateStatus.OUT_OF_STOCK: "Excluded - out of stock",
             CandidateStatus.NO_SCHEDULE: "Excluded - no truck schedule",
             CandidateStatus.ROUTE_ERROR: "Excluded - no route",
             CandidateStatus.INVALID_DATA: "Excluded - invalid data"}


def build_table(candidates, selected_id: str | None, sku: str, quantity: int, now: datetime) -> pd.DataFrame:
    rows = []
    for c in candidates:
        meta = _COMPANY.get(c.company_id, {})
        row = {"Company": c.company_name, "Location": meta.get("city", "-"),
               "Product availability": _availability(c.company_id, sku, quantity) if meta else "-"}
        if c.is_candidate:
            row.update({"Next truck": _next_truck(c, now), "Waiting (h)": c.waiting_hours,
                        "Distance (km)": c.distance_km, "Travel time (h)": c.travel_hours,
                        "Total expected (h)": c.total_hours,
                        "Status": "✅ Selected" if c.company_id == selected_id else "Valid"})
        else:
            row.update({"Next truck": None, "Waiting (h)": None, "Distance (km)": None,
                        "Travel time (h)": None, "Total expected (h)": None, "Status": _EXCLUDED[c.status]})
        rows.append(row)
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.sort_values("Total expected (h)", na_position="last", kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class Analysis:
    result: OptimizationResult | None
    candidates: tuple[CandidateResult, ...]
    error: str | None
    table: pd.DataFrame

    @property
    def selected(self) -> CandidateResult | None:
        return self.result.selected if self.result else None

    @property
    def selected_city(self) -> str | None:
        return _COMPANY[self.selected.company_id]["city"] if self.selected else None

    def chart_frame(self) -> pd.DataFrame:
        valid = [c for c in self.candidates if c.is_candidate]
        return pd.DataFrame({"Waiting (h)": [c.waiting_hours for c in valid],
                             "Travel (h)": [c.travel_hours for c in valid]},
                            index=[c.company_name for c in valid]).sort_values("Waiting (h)")


def analyze(city_name: str, sku: str, quantity: int, now: datetime) -> Analysis:
    """Run the real V2 optimizer for a customer in `city_name` ordering `quantity` x `sku`."""
    lat, lon = ui_data.CITIES[city_name]
    customer = {"id": "CUSTOMER", "latitude": lat, "longitude": lon}
    order = {"id": "ORDER", "lines": [{"sku": sku, "quantity": quantity}]}
    route_fn = partial(get_route, provider=CityRoadProvider())
    try:
        result = choose_best_logistics(customer, ui_data.COMPANIES, now=now, route_fn=route_fn,
                                       order=order, warehouses=ui_data.WAREHOUSES)
        candidates, selected_id, error = result.candidates, result.selected.company_id, None
    except NoViableLogisticsError as exc:
        result, candidates, selected_id = None, exc.candidates, None
        if candidates and all(c.status is CandidateStatus.OUT_OF_STOCK for c in candidates):
            error = "The order cannot be fulfilled: no partner warehouse has this product in stock."
        else:
            error = "No logistics company could be evaluated for this order."
    return Analysis(result, tuple(candidates), error, build_table(candidates, selected_id, sku, quantity, now))
