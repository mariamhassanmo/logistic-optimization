"""Configuration and environment variables.

Nothing secret is ever hard-coded here: the routing API key is read from the
environment (optionally loaded from a local `.env` file).
"""
from __future__ import annotations

import os
from zoneinfo import ZoneInfo

try:  # python-dotenv is optional; plain environment variables work without it.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# All schedule maths is done in this timezone, never in the machine's local one.
TIMEZONE_NAME = "Africa/Cairo"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

# openrouteservice settings (all overridable through the environment).
ORS_BASE_URL = os.getenv("ORS_BASE_URL", "https://api.openrouteservice.org")
# "driving-car" = normal driving time (V1 spec). "driving-hgv" is the heavy-truck profile.
ORS_PROFILE = os.getenv("ORS_PROFILE", "driving-car")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "10"))

# Two points closer than this are treated as the same place (no routing call).
SAME_LOCATION_THRESHOLD_M = float(os.getenv("SAME_LOCATION_THRESHOLD_M", "50"))


class ConfigError(RuntimeError):
    """Raised when required configuration (e.g. the API key) is missing."""


def get_ors_api_key() -> str:
    key = os.getenv("ORS_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "ORS_API_KEY is not set. Copy .env.example to .env and add your "
            "openrouteservice key, or run with --demo for the offline demo."
        )
    return key
