"""Base entity for the Xweather Lightning integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER, MODEL
from .coordinator import XWeatherLightningCoordinator


def nested_get(source: Any, path: str) -> Any:
    """Read a dotted path out of nested dicts, returning None on any miss."""
    current = source
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


class XWeatherLightningEntity(CoordinatorEntity[XWeatherLightningCoordinator]):
    """Common wiring so every entity lands on the same device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: XWeatherLightningCoordinator, key: str
    ) -> None:
        """Bind the entity to the coordinator's config entry."""
        super().__init__(coordinator)
        entry = coordinator.config_entry

        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # One device per configured location. entry_id keeps the identifier
        # stable even if the user renames the location later.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://account.xweather.com/",
        )
