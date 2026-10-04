"""Sample data for the Streamlit demo (Egypt). Illustrative, not live data.

Road distances are approximate road-km between city centres; they feed a small
offline road model (see ui_service.CityRoadProvider) so the demo works without internet.
"""
from datetime import date, time

CITIES = {  # city centres (lat, lon) - used for customer locations
    "Cairo": (30.0444, 31.2357), "Giza": (29.9870, 31.2118), "Alexandria": (31.2001, 29.9187),
    "Tanta": (30.7865, 31.0004), "Mansoura": (31.0409, 31.3785),
    "Ismailia": (30.5965, 32.2715), "Suez": (29.9668, 32.5498),
}

ROAD_KM = {
    ("Cairo", "Giza"): 15, ("Cairo", "Alexandria"): 220, ("Cairo", "Tanta"): 95, ("Cairo", "Mansoura"): 125,
    ("Cairo", "Ismailia"): 120, ("Cairo", "Suez"): 135,
    ("Giza", "Alexandria"): 205, ("Giza", "Tanta"): 105, ("Giza", "Mansoura"): 135,
    ("Giza", "Ismailia"): 135, ("Giza", "Suez"): 150,
    ("Alexandria", "Tanta"): 125, ("Alexandria", "Mansoura"): 175, ("Alexandria", "Ismailia"): 290,
    ("Alexandria", "Suez"): 350, ("Tanta", "Mansoura"): 40, ("Tanta", "Ismailia"): 165,
    ("Tanta", "Suez"): 215, ("Mansoura", "Ismailia"): 120, ("Mansoura", "Suez"): 215, ("Ismailia", "Suez"): 90,
}

PRODUCTS = {  # SKU -> label
    "IPHONE17-256-BLK": "iPhone 17 - 256 GB, Black",
    "S25-256-GRY": "Samsung Galaxy S25 - 256 GB, Grey",
    "PS5-SLIM": "PlayStation 5 Slim - Disc Edition",
}

# Logistics partners: hub location (slightly off-centre), daily truck departures, linked warehouse.
COMPANIES = [
    {"id": "L-GIZ", "name": "Giza QuickShip", "city": "Giza", "latitude": 29.9950, "longitude": 31.2000,
     "truck_schedule": ["08:00", "20:00"], "warehouse_ids": ["W-GIZ"]},
    {"id": "L-TNT", "name": "Delta Express", "city": "Tanta", "latitude": 30.7900, "longitude": 30.9900,
     "truck_schedule": ["09:00", "15:00", "21:00"], "warehouse_ids": ["W-TNT"]},
    {"id": "L-ALX", "name": "Alex Freight", "city": "Alexandria", "latitude": 31.1850, "longitude": 29.9500,
     "truck_schedule": ["11:00", "23:00"], "warehouse_ids": ["W-ALX"]},
    {"id": "L-ISM", "name": "Canal Logistics", "city": "Ismailia", "latitude": 30.6100, "longitude": 32.2600,
     "truck_schedule": ["12:00", "18:00"], "warehouse_ids": ["W-ISM"]},
    {"id": "L-SUZ", "name": "Suez Cargo", "city": "Suez", "latitude": 29.9800, "longitude": 32.5300,
     "truck_schedule": ["07:00", "17:00"], "warehouse_ids": ["W-SUZ"]},
    {"id": "L-MNS", "name": "Mansoura Trans", "city": "Mansoura", "latitude": 31.0500, "longitude": 31.3600,
     "truck_schedule": ["10:00", "16:00"], "warehouse_ids": ["W-MNS"]},
]

WAREHOUSES = [  # stock: SKU -> units on hand (or {"on_hand", "reserved"})
    {"id": "W-GIZ", "name": "Giza DC", "stock": {"IPHONE17-256-BLK": 4, "S25-256-GRY": 6,
                                                 "PS5-SLIM": {"on_hand": 3, "reserved": 3}}},  # all reserved
    {"id": "W-TNT", "name": "Tanta DC", "stock": {"IPHONE17-256-BLK": 6, "S25-256-GRY": 0, "PS5-SLIM": 5}},
    {"id": "W-ALX", "name": "Alexandria DC", "stock": {"IPHONE17-256-BLK": 3, "S25-256-GRY": 8, "PS5-SLIM": 2}},
    {"id": "W-ISM", "name": "Ismailia DC", "stock": {"IPHONE17-256-BLK": 0, "S25-256-GRY": 4, "PS5-SLIM": 4}},
    {"id": "W-SUZ", "name": "Suez DC", "stock": {"IPHONE17-256-BLK": 2, "S25-256-GRY": 3, "PS5-SLIM": 0}},
    {"id": "W-MNS", "name": "Mansoura DC", "stock": {"IPHONE17-256-BLK": 0, "S25-256-GRY": 5, "PS5-SLIM": 7}},
]

_D = date(2026, 10, 5)

