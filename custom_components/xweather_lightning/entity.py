"""Base entity for the Xweather Lightning integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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


def sync_gated_visibility(
    hass: HomeAssistant,
    entry: ConfigEntry,
    platform_domain: str,
    keys: Iterable[str],
    visible: bool,
) -> None:
    """Hide or unhide already-registered entities to match a runtime option.

    `entity_registry_visible_default` on an entity only seeds `hidden_by` the
    first time that entity is ever registered; Home Assistant does not
    re-apply it on later setups. A reload alone is not enough to make
    already-existing entities react to an option flip, so this reconciles
    `hidden_by` directly. Entities the user has hidden or shown themselves
    (`RegistryEntryHider.USER`) are left alone.
    """
    registry = er.async_get(hass)
    desired = None if visible else er.RegistryEntryHider.INTEGRATION
    for key in keys:
        entity_id = registry.async_get_entity_id(
            platform_domain, DOMAIN, f"{entry.entry_id}_{key}"
        )
        if entity_id is None:
            continue
        current = registry.async_get(entity_id)
        if current is None or current.hidden_by not in (
            None,
            er.RegistryEntryHider.INTEGRATION,
        ):
            continue
        if current.hidden_by != desired:
            registry.async_update_entity(entity_id, hidden_by=desired)


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
