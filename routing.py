"""Road routing, isolated behind a tiny provider interface.

The rest of the project only ever calls:

    get_route(origin, destination) -> RouteResult(distance_km, travel_time_hours)

and only knows the exceptions defined here. All openrouteservice specifics
(URL, auth header, JSON shape, status codes) live in `OpenRouteServiceProvider`.
To switch provider, write another `RoutingProvider` subclass; nothing else changes.

Travel time always comes from ROAD routing, never from straight-line distance.
(The haversine helper below is used ONLY to detect "same location".)
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

import requests

import config
from models import Coordinates


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RoutingError(Exception):
    """Base class for every routing failure."""


class RoutingTimeoutError(RoutingError):
    """The routing service did not answer in time."""


class RoutingNetworkError(RoutingError):
    """Could not reach the routing service."""


class RoutingAuthError(RoutingError):
    """API key rejected (HTTP 401/403)."""


class RoutingRateLimitError(RoutingError):
    """Quota / rate limit exceeded (HTTP 429)."""


class RoutingNoRouteError(RoutingError):
    """No drivable route exists (or a point cannot be snapped to the road network)."""


class RoutingResponseError(RoutingError):
    """The service answered, but the response was invalid or malformed."""


class RoutingServerError(RoutingError):
    """The routing service had an internal error (HTTP 5xx)."""


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RouteResult:
    distance_km: float
    travel_time_hours: float

    def __post_init__(self) -> None:
        for name in ("distance_km", "travel_time_hours"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
                raise RoutingResponseError(f"Invalid {name} in route result: {value!r}")

    def as_dict(self) -> dict[str, float]:
        return {"distance_km": self.distance_km, "travel_time_hours": self.travel_time_hours}


# --------------------------------------------------------------------------- #
# Provider interface + implementations
# --------------------------------------------------------------------------- #
class RoutingProvider(ABC):
    @abstractmethod
    def fetch_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        """Return the road route; raise a RoutingError subclass on any failure."""


class OpenRouteServiceProvider(RoutingProvider):
    """openrouteservice (OpenStreetMap data) - free development tier available."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 profile: str | None = None, timeout: float | None = None) -> None:
        self._api_key = api_key if api_key is not None else config.get_ors_api_key()
        self._base_url = (base_url or config.ORS_BASE_URL).rstrip("/")
        self._profile = profile or config.ORS_PROFILE
        self._timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT_SECONDS

    def fetch_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        url = f"{self._base_url}/v2/directions/{self._profile}"
        body = {"coordinates": [  # ORS wants [longitude, latitude]
            [origin.longitude, origin.latitude],
            [destination.longitude, destination.latitude],
        ]}
        headers = {"Authorization": self._api_key, "Content-Type": "application/json"}
        try:
            response = requests.post(url, json=body, headers=headers, timeout=self._timeout)
        except requests.Timeout:
            raise RoutingTimeoutError(f"routing request timed out after {self._timeout}s") from None
        except requests.RequestException as exc:
            raise RoutingNetworkError(f"could not reach routing service: {exc}") from None

        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError:
            raise RoutingResponseError("routing service returned invalid JSON") from None
        return self._parse(payload)

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _error_message(response) -> str:
        try:
            error = response.json().get("error")
            if isinstance(error, dict):
                return str(error.get("message", error))
            if error:
                return str(error)
        except (ValueError, AttributeError):
            pass
        return (getattr(response, "text", "") or "")[:200] or "no details"

    def _raise_for_status(self, response) -> None:
        status = response.status_code
        if status == 200:
            return
        detail = self._error_message(response)
        if status in (401, 403):
            raise RoutingAuthError(f"authentication failed (HTTP {status}): {detail}")
        if status == 429:
            raise RoutingRateLimitError(f"rate limit / quota exceeded (HTTP 429): {detail}")
        if status == 404:
            raise RoutingNoRouteError(f"no route found (HTTP 404): {detail}")
        if status >= 500:
            raise RoutingServerError(f"routing service error (HTTP {status}): {detail}")
        raise RoutingResponseError(f"unexpected response (HTTP {status}): {detail}")

    @staticmethod
    def _parse(payload) -> RouteResult:
        if not isinstance(payload, dict) or "routes" not in payload:
            raise RoutingResponseError("malformed response: missing 'routes'")
        routes = payload["routes"]
        if not isinstance(routes, list):
            raise RoutingResponseError("malformed response: 'routes' is not a list")
        if not routes:
            raise RoutingNoRouteError("no route found between the two points")
        try:
            summary = routes[0]["summary"]
            distance_m, duration_s = summary["distance"], summary["duration"]
        except (KeyError, TypeError, IndexError):
            raise RoutingResponseError("malformed response: missing route summary") from None
        for value in (distance_m, duration_s):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RoutingResponseError(f"malformed response: non-numeric summary value {value!r}")
        return RouteResult(distance_km=distance_m / 1000.0, travel_time_hours=duration_s / 3600.0)


class StaticRoutingProvider(RoutingProvider):
    """Offline provider backed by a lookup table, keyed by ORIGIN (lat, lon).

    Values are a RouteResult (success) or a RoutingError instance (simulated failure).
    Used by the offline demo and the tests; never contacts the network.
    """

    def __init__(self, table: Mapping[tuple[float, float], RouteResult | RoutingError]) -> None:
        self._table = dict(table)

    def fetch_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        try:
            entry = self._table[(origin.latitude, origin.longitude)]
        except KeyError:
            raise RoutingNoRouteError("no offline route defined for this origin") from None
        if isinstance(entry, RoutingError):
            raise entry
        return entry


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def approx_distance_m(a: Coordinates, b: Coordinates) -> float:
    """Straight-line (haversine) metres. ONLY used to detect identical locations."""
    r = 6_371_000.0
    p1, p2 = math.radians(a.latitude), math.radians(b.latitude)
    dphi = p2 - p1
    dlmb = math.radians(b.longitude - a.longitude)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


_default_provider: RoutingProvider | None = None


def get_route(origin: Coordinates, destination: Coordinates,
              provider: RoutingProvider | None = None) -> RouteResult:
    """Road distance (km) and driving time (hours) from `origin` to `destination`.

    * Effectively identical locations (<= SAME_LOCATION_THRESHOLD_M) return
      0 km / 0 h WITHOUT calling the provider.
    * Otherwise delegates to `provider` (default: openrouteservice, created lazily
      so a missing API key only matters when a real route is needed).
    * Raises a RoutingError subclass on any failure.
    """
    if approx_distance_m(origin, destination) <= config.SAME_LOCATION_THRESHOLD_M:
        return RouteResult(distance_km=0.0, travel_time_hours=0.0)
    global _default_provider
    if provider is None:
        if _default_provider is None:
            _default_provider = OpenRouteServiceProvider()
        provider = _default_provider
    return provider.fetch_route(origin, destination)
