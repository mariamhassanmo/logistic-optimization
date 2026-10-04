"""Plain-text rendering of optimizer results."""
from __future__ import annotations

from datetime import datetime

from config import TIMEZONE, TIMEZONE_NAME
from optimizer import CandidateResult, NoViableLogisticsError, OptimizationResult

RULE = "-" * 50


def _departure_label(departure: datetime, now: datetime) -> str:
    days = (departure.date() - now.astimezone(TIMEZONE).date()).days
    clock = departure.strftime("%H:%M")
    if days == 0:
        return f"{clock} today"
    if days == 1:
        return f"{clock} tomorrow"
    return f"{departure:%Y-%m-%d} {clock}"


def _format_candidate(c: CandidateResult, now: datetime) -> list[str]:
    lines = [RULE, f"{c.company_name} [{c.company_id}]"]
    if c.is_candidate:
        lines += [
            f"Distance: {c.distance_km:.1f} km",
            f"Next truck: {_departure_label(c.next_departure, now)}",
            f"Waiting time: {c.waiting_hours:.1f} hours",
            f"Road travel time: {c.travel_hours:.1f} hours",
            f"Total expected time: {c.total_hours:.1f} hours",
            "Status: Candidate",
        ]
        if c.warehouse_id:
            lines.insert(2, f"Warehouse: {c.warehouse_id}")
    else:
        lines += [f"Status: Unavailable ({c.status.value})", f"Reason: {c.reason}"]
    return lines


def format_report(result: OptimizationResult) -> str:
    now = result.evaluated_at
    lines = [f"Customer: {result.customer_id}",
             f"Evaluated at: {now.astimezone(TIMEZONE):%Y-%m-%d %H:%M} ({TIMEZONE_NAME})", ""]
    if result.order:
        lines.insert(1, "Order: " + ", ".join(f"{l.sku} x{l.quantity}" for l in result.order.lines))
    for c in result.candidates:
        lines += _format_candidate(c, now) + [""]
    sel = result.selected
    lines += [RULE, "SELECTED LOGISTICS COMPANY", f"{sel.company_name} [{sel.company_id}]", "", "Reason:"]
    lines += [f"  - {line}" for line in result.explanation]
    lines += ["", f"Total expected time: {sel.total_hours:.1f} hours", RULE]
    return "\n".join(lines)


def format_failure(error: NoViableLogisticsError) -> str:
    lines = ["ERROR: no logistics company could be selected."]
    if not error.candidates:
        lines.append(str(error))
    elif all(c.status.value == "unavailable_out_of_stock" for c in error.candidates):
        lines.append("The order cannot be fulfilled: no partner warehouse has all the items in stock.")
    for c in error.candidates:
        lines.append(f"  - {c.company_name} [{c.company_id}]: {c.status.value} - {c.reason}")
    return "\n".join(lines)
