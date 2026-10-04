"""Data models and input validation.

Everything that enters the system (coordinates, schedules, companies, customers)
is validated here, so the scheduler, router and optimizer can trust their inputs.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import time
from typing import Any, Mapping, Sequence


class ValidationError(ValueError):
    """Input data is invalid. The message says exactly what is wrong."""


# --------------------------------------------------------------------------- #
# Coordinates
# --------------------------------------------------------------------------- #
def parse_coordinate(value: Any, label: str, low: float, high: float) -> float:
    """Return `value` as a finite float within [low, high] or raise ValidationError.

    Numeric strings such as "31.2" are accepted (CSV/JSON friendliness);
    None, blanks, bools, NaN/inf and anything non-numeric are rejected.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{label} is missing")
    if isinstance(value, bool):
        raise ValidationError(f"{label} is not numeric: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} is not numeric: {value!r}") from None
    if not math.isfinite(number):
        raise ValidationError(f"{label} must be a finite number, got {value!r}")
    if not low <= number <= high:
        raise ValidationError(f"{label} {number} is out of range [{low}, {high}]")
    return number


@dataclass(frozen=True)
class Coordinates:
    """A validated latitude/longitude pair. Invalid values can never be constructed."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "latitude", parse_coordinate(self.latitude, "latitude", -90, 90))
        object.__setattr__(self, "longitude", parse_coordinate(self.longitude, "longitude", -180, 180))

    @classmethod
    def from_values(cls, latitude: Any, longitude: Any) -> "Coordinates":
        """Like the constructor, but reports *all* coordinate problems at once."""
        errors: list[str] = []
        for value, label, low, high in (
            (latitude, "latitude", -90, 90),
            (longitude, "longitude", -180, 180),
        ):
            try:
                parse_coordinate(value, label, low, high)
            except ValidationError as exc:
                errors.append(str(exc))
        if errors:
            raise ValidationError("; ".join(errors))
        return cls(latitude, longitude)


# --------------------------------------------------------------------------- #
# Schedules
# --------------------------------------------------------------------------- #
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_departure_time(value: Any) -> time:
    """Parse a 24-hour "HH:MM" string (or a datetime.time) into a naive `time`."""
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        raise ValidationError(
            f'Invalid departure time {value!r}: expected a 24-hour "HH:MM" string'
        )
    match = _TIME_RE.match(value.strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise ValidationError(
            f'Invalid departure time {value!r}: expected 24-hour "HH:MM" between 00:00 and 23:59'
        )
    return time(int(match.group(1)), int(match.group(2)))


def parse_schedule(value: Any) -> tuple[time, ...]:
    """Validate a daily schedule. Returns sorted, de-duplicated times of day.

    An empty list is valid (the company simply has no trucks); None is not.
    """
    if value is None:
        raise ValidationError("truck_schedule is missing (use [] for a company with no trucks)")
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        raise ValidationError(f"truck_schedule must be a list of HH:MM strings, got {value!r}")
    errors: list[str] = []
    parsed: set[time] = set()
    for item in value:
        try:
            parsed.add(parse_departure_time(item))
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValidationError("; ".join(errors))
    return tuple(sorted(parsed))


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
def _require_id(data: Mapping[str, Any], errors: list[str]) -> str | None:
    raw = data.get("id")
    if raw is None or not str(raw).strip():
        errors.append("id is missing")
        return None
    return str(raw).strip()


@dataclass(frozen=True)
class Customer:
    id: str
    coordinates: Coordinates

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Customer":
        if not isinstance(data, Mapping):
            raise ValidationError(f"customer must be a mapping, got {type(data).__name__}")
        errors: list[str] = []
        cid = _require_id(data, errors)
        coords = None
        try:
            coords = Coordinates.from_values(data.get("latitude"), data.get("longitude"))
        except ValidationError as exc:
            errors.append(str(exc))
        if errors:
            raise ValidationError("; ".join(errors))
        return cls(id=cid, coordinates=coords)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LogisticsCompany:
    """A logistics company with ONE location and a DAILY truck schedule.

    `truck_schedule` holds times of day (Africa/Cairo) at which a truck leaves
    every day; it may be empty (company unavailable).
    """

    id: str
    name: str
    coordinates: Coordinates
    truck_schedule: tuple[time, ...]
    warehouse_ids: tuple[str, ...] = ()   # V2: warehouses this partner ships from

    @property
    def latitude(self) -> float:
        return self.coordinates.latitude

    @property
    def longitude(self) -> float:
        return self.coordinates.longitude

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LogisticsCompany":
        if not isinstance(data, Mapping):
            raise ValidationError(f"company must be a mapping, got {type(data).__name__}")
        errors: list[str] = []
        cid = _require_id(data, errors)
        coords = None
        schedule: Sequence[time] = ()
        try:
            coords = Coordinates.from_values(data.get("latitude"), data.get("longitude"))
        except ValidationError as exc:
            errors.append(str(exc))
        try:
            schedule = parse_schedule(data.get("truck_schedule"))
        except ValidationError as exc:
            errors.append(str(exc))
        warehouse_ids: tuple[str, ...] = ()
        try:
            warehouse_ids = parse_warehouse_ids(data.get("warehouse_ids"))
        except ValidationError as exc:
            errors.append(str(exc))
        if errors:
            raise ValidationError("; ".join(errors))
        name = str(data.get("name") or cid).strip()
        return cls(id=cid, name=name, coordinates=coords, truck_schedule=tuple(schedule),  # type: ignore[arg-type]
                   warehouse_ids=warehouse_ids)


# --------------------------------------------------------------------------- #
# V2: orders, warehouses, stock
# --------------------------------------------------------------------------- #
def parse_count(value: Any, label: str, minimum: int = 0) -> int:
    """Whole-number quantity (ints, integral floats, numeric strings); rejects bools/NaN/fractions."""
    if value is None or isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number, got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number, got {value!r}") from None
    if not math.isfinite(number) or number != int(number):
        raise ValidationError(f"{label} must be a whole number, got {value!r}")
    if int(number) < minimum:
        raise ValidationError(f"{label} must be >= {minimum}, got {int(number)}")
    return int(number)


def parse_warehouse_ids(value: Any) -> tuple[str, ...]:
    """Optional list of warehouse ids a company ships from (missing -> none linked)."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        raise ValidationError(f"warehouse_ids must be a list of warehouse ids, got {value!r}")
    bad = [v for v in value if not isinstance(v, str) or not v.strip()]
    if bad:
        raise ValidationError(f"warehouse_ids contains invalid ids: {bad!r}")
    return tuple(sorted({v.strip() for v in value}))


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int


@dataclass(frozen=True)
class Order:
    """What the customer ordered: one or more SKU lines (same SKU lines are merged)."""

    id: str
    lines: tuple[OrderLine, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Order":
        if not isinstance(data, Mapping):
            raise ValidationError(f"order must be a mapping, got {type(data).__name__}")
        errors: list[str] = []
        merged: dict[str, int] = {}
        raw_lines = data.get("lines")
        if not isinstance(raw_lines, (list, tuple)) or not raw_lines:
            errors.append("order must contain at least one line")
        else:
            for i, line in enumerate(raw_lines, 1):
                if not isinstance(line, Mapping):
                    errors.append(f"order line {i} must be a mapping")
                    continue
                sku = line.get("sku")
                if not isinstance(sku, str) or not sku.strip():
                    errors.append(f"order line {i}: sku is missing")
                    continue
                try:
                    qty = parse_count(line.get("quantity"), f"order line {i} quantity", minimum=1)
                except ValidationError as exc:
                    errors.append(str(exc))
                    continue
                merged[sku.strip()] = merged.get(sku.strip(), 0) + qty
        if errors:
            raise ValidationError("; ".join(errors))
        oid = str(data.get("id") or "ORDER").strip()
        return cls(id=oid, lines=tuple(OrderLine(k, v) for k, v in merged.items()))


@dataclass(frozen=True)
class StockLevel:
    on_hand: int
    reserved: int = 0   # already promised to other orders

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)


@dataclass(frozen=True)
class Warehouse:
    """A stock-holding site. `stock` maps SKU -> StockLevel."""

    id: str
    name: str
    stock: Mapping[str, StockLevel]
    active: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Warehouse":
        """stock values: an int (on hand) or {"on_hand": n, "reserved": m}."""
        if not isinstance(data, Mapping):
            raise ValidationError(f"warehouse must be a mapping, got {type(data).__name__}")
        errors: list[str] = []
        wid = _require_id(data, errors)
        active = data.get("active", True)
        if not isinstance(active, bool):
            errors.append(f"active must be true/false, got {active!r}")
        raw_stock = data.get("stock")
        stock: dict[str, StockLevel] = {}
        if not isinstance(raw_stock, Mapping):
            errors.append("stock must be a mapping of SKU -> quantity")
        else:
            for sku, level in raw_stock.items():
                label = f"stock[{sku!r}]"
                if not isinstance(sku, str) or not sku.strip():
                    errors.append(f"{label}: SKU must be a non-empty string")
                    continue
                try:
                    if isinstance(level, Mapping):
                        stock[sku.strip()] = StockLevel(parse_count(level.get("on_hand"), f"{label}.on_hand"),
                                                        parse_count(level.get("reserved", 0), f"{label}.reserved"))
                    else:
                        stock[sku.strip()] = StockLevel(parse_count(level, label))
                except ValidationError as exc:
                    errors.append(str(exc))
        if errors:
            raise ValidationError("; ".join(errors))
        return cls(id=wid, name=str(data.get("name") or wid).strip(), stock=stock, active=active)  # type: ignore[arg-type]
