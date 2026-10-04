"""Sample data for the CLI, the offline demo and manual testing.

The OFFLINE_ROUTES numbers below are ILLUSTRATIVE values chosen to demonstrate the
"farther company wins" scenario without network access. They are not real
measurements; in live mode openrouteservice supplies real road routes.
"""
from __future__ import annotations

from datetime import datetime

from config import TIMEZONE
from routing import RouteResult, RoutingNoRouteError

# Fixed "now" for the reproducible demo: Friday 2026-10-02, 14:00 Cairo time.
SAMPLE_NOW = datetime(2026, 10, 2, 14, 0, tzinfo=TIMEZONE)

SAMPLE_CUSTOMER = {"id": "C001", "latitude": 31.2001, "longitude": 29.9187}  # Alexandria

SAMPLE_COMPANIES = [
    {"id": "L001", "name": "Logistic A (Cairo)", "latitude": 30.0444, "longitude": 31.2357,
     "truck_schedule": ["09:00", "22:00"]},
    {"id": "L002", "name": "Logistic B (Port Said)", "latitude": 31.2653, "longitude": 32.3019,
     "truck_schedule": ["09:00", "17:00"]},
    {"id": "L003", "name": "Logistic C (Damanhur, nearest)", "latitude": 31.0341, "longitude": 30.4682,
     "truck_schedule": ["06:00"]},
    {"id": "L004", "name": "Logistic D (Tanta, no trucks)", "latitude": 30.7865, "longitude": 31.0004,
     "truck_schedule": []},
    {"id": "L005", "name": "Logistic E (Mansoura)", "latitude": 31.0409, "longitude": 31.3785,
     "truck_schedule": ["15:00"]},
    {"id": "L006", "name": "Logistic F (Giza, bad schedule)", "latitude": 30.0131, "longitude": 31.2089,
     "truck_schedule": ["9 PM", "18:00"]},
]

# Offline routes keyed by company (latitude, longitude): company -> Alexandria customer.
OFFLINE_ROUTES = {
    (30.0444, 31.2357): RouteResult(distance_km=210.0, travel_time_hours=2.5),
    (31.2653, 32.3019): RouteResult(distance_km=330.0, travel_time_hours=3.5),
    (31.0341, 30.4682): RouteResult(distance_km=65.0, travel_time_hours=1.0),
    (31.0409, 31.3785): RoutingNoRouteError("simulated failure: destination unreachable"),
}


# --------------------------------------------------------------------------- #
# V2 demo: customer in Cairo orders an iPhone 17; only A and B have stock.
# --------------------------------------------------------------------------- #
V2_CUSTOMER = {"id": "C002", "latitude": 30.0626, "longitude": 31.3300}  # Cairo (Nasr City)
V2_ORDER = {"id": "O-1001", "lines": [{"sku": "IPHONE17-256-BLK", "quantity": 1}]}

V2_COMPANIES = [
    {"id": "A", "name": "Logistic A (Alexandria)", "latitude": 31.2001, "longitude": 29.9187,
     "truck_schedule": ["15:00", "23:00"], "warehouse_ids": ["W-ALX"]},
    {"id": "B", "name": "Logistic B (Suez)", "latitude": 29.9668, "longitude": 32.5498,
     "truck_schedule": ["19:00"], "warehouse_ids": ["W-SUZ"]},
    {"id": "C", "name": "Logistic C (Giza, nearest)", "latitude": 30.0131, "longitude": 31.2089,
     "truck_schedule": ["15:00"], "warehouse_ids": ["W-GIZ"]},
    {"id": "D", "name": "Logistic D (Tanta)", "latitude": 30.7865, "longitude": 31.0004,
     "truck_schedule": ["14:30"], "warehouse_ids": ["W-TNT"]},
]

V2_WAREHOUSES = [
    {"id": "W-ALX", "name": "Alexandria DC", "stock": {"IPHONE17-256-BLK": {"on_hand": 5, "reserved": 1},
                                                      "IPHONE16-128-BLK": 3}},
    {"id": "W-SUZ", "name": "Suez DC", "stock": {"IPHONE17-256-BLK": 3}},
    {"id": "W-GIZ", "name": "Giza DC", "stock": {"IPHONE17-256-BLK": {"on_hand": 2, "reserved": 2}}},  # all reserved
    {"id": "W-TNT", "name": "Tanta DC", "stock": {"IPHONE16-128-BLK": 10}},                          # no iPhone 17
]

# Routes only for A and B on purpose: if the stock filter ever failed, C/D would
# show up as route_error instead of silently passing.
V2_OFFLINE_ROUTES = {
    (31.2001, 29.9187): RouteResult(distance_km=220.0, travel_time_hours=2.5),
    (29.9668, 32.5498): RouteResult(distance_km=130.0, travel_time_hours=1.8),
}
