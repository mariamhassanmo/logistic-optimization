"""CLI for the Logistics Company Selection & Delivery-Time Optimization System (V1 + V2 stock check).

Examples:
    python main.py --demo                      # V1 offline demo (no order)
    python main.py --demo-v2                   # V2 offline demo: iPhone order, stock check first
    python main.py                             # live routing via openrouteservice (needs ORS_API_KEY)
    python main.py --data scenario.json        # {"customer", "companies", optional "order" + "warehouses"}
    python main.py --now 2026-10-02T14:00      # pretend it is this Cairo time
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from functools import partial

import data
from config import TIMEZONE, ConfigError
from models import ValidationError
from optimizer import NoViableLogisticsError, choose_best_logistics
from report import format_failure, format_report
from routing import OpenRouteServiceProvider, StaticRoutingProvider, get_route


def parse_now(text: str) -> datetime:
    """ISO-8601 string; naive values are interpreted as Africa/Cairo time."""
    moment = datetime.fromisoformat(text)
    return moment.replace(tzinfo=TIMEZONE) if moment.tzinfo is None else moment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select the logistics company with the lowest expected delivery time.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="V1 offline demo: sample data, canned routes, fixed time")
    source.add_argument("--demo-v2", action="store_true", help="V2 offline demo: iPhone order from Cairo with stock check")
    source.add_argument("--data", metavar="FILE",
                        help='JSON file: {"customer": {...}, "companies": [...], "order": {...}, "warehouses": [...]}')
    parser.add_argument("--now", metavar="ISO", help="override current time (naive = Africa/Cairo)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    offline = args.demo or args.demo_v2
    try:
        order = warehouses = None
        if args.data:
            with open(args.data, encoding="utf-8") as handle:
                payload = json.load(handle)
            customer, companies = payload["customer"], payload["companies"]
            order, warehouses = payload.get("order"), payload.get("warehouses")
        elif args.demo_v2:
            customer, companies = data.V2_CUSTOMER, data.V2_COMPANIES
            order, warehouses = data.V2_ORDER, data.V2_WAREHOUSES
        else:
            customer, companies = data.SAMPLE_CUSTOMER, data.SAMPLE_COMPANIES

        now = parse_now(args.now) if args.now else (data.SAMPLE_NOW if offline else datetime.now(TIMEZONE))

        if offline:
            provider = StaticRoutingProvider(data.V2_OFFLINE_ROUTES if args.demo_v2 else data.OFFLINE_ROUTES)
        else:
            provider = OpenRouteServiceProvider()
        result = choose_best_logistics(customer, companies, now=now, order=order, warehouses=warehouses,
                                       route_fn=partial(get_route, provider=provider))
    except NoViableLogisticsError as exc:
        print(format_failure(exc))
        return 1
    except (ConfigError, ValidationError, ValueError, KeyError, OSError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
