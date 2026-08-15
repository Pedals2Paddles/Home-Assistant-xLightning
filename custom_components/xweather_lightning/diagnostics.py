"""Diagnostics support for the Xweather Lightning integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from . import XWeatherLightningConfigEntry
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

TO_REDACT = {CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: XWeatherLightningConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else None

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "radius_km": coordinator.radius_km,
            "window_minutes": coordinator.window_minutes,
            "nearby_km": coordinator.nearby_km,
        },
        "data": async_redact_data(data, {"relativeTo", "loc"}) if data else None,
    }
