"""Diagnostics support for Indego integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _serialize_dt(value: Any) -> Any:
    """Return ISO formatted date for datetimes."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub = hass.data[DOMAIN][entry.entry_id]
    client = hub.client

    state = getattr(client, "state", None)
    state_data = None
    if state is not None:
        state_data = getattr(state, "__dict__", str(state))

    request_attrs = [
        "last_state_request",
        "last_generic_data_request",
        "last_operating_data_request",
        "last_alerts_request",
        "last_predictive_calendar_request",
    ]
    last_requests = {
        attr: _serialize_dt(getattr(client, attr, None)) for attr in request_attrs
    }

    error_counts = {
        "update_failures": getattr(hub, "_update_fail_count", None),
        "request_errors": getattr(client, "error_counter", None),
    }

    return {
        "state": state_data,
        "last_request_times": last_requests,
        "error_counts": error_counts,
    }
