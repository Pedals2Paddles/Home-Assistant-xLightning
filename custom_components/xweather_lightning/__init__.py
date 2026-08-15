"""The Xweather Lightning integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import XWeatherLightningClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from .coordinator import XWeatherLightningCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.SENSOR,
]

type XWeatherLightningConfigEntry = ConfigEntry[XWeatherLightningCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: XWeatherLightningConfigEntry
) -> bool:
    """Set up a monitored location from a config entry."""
    client = XWeatherLightningClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )

    coordinator = XWeatherLightningCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: XWeatherLightningConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: XWeatherLightningConfigEntry
) -> None:
    """Reload the entry so new options (radius, interval) take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
