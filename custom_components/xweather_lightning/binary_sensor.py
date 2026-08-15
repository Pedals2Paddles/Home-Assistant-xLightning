"""Binary sensor platform for the Xweather Lightning integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XWeatherLightningConfigEntry
from .coordinator import LightningData, XWeatherLightningCoordinator
from .entity import XWeatherLightningEntity, nested_get

PARALLEL_UPDATES = 0


def _any_activity(data: LightningData, _coordinator) -> bool:
    """True when the summary reports at least one pulse in the window."""
    count = nested_get(data.summary, "pulse.count")
    return bool(count)


def _nearby(data: LightningData, coordinator: XWeatherLightningCoordinator) -> bool:
    """True when the closest strike falls inside the alert distance.

    Deliberately ignores retained strikes: this drives "seek shelter" alerts,
    so it must reflect the current window only. Otherwise the retention period
    would hold the alert on for an hour after the storm had passed.
    """
    if data.nearest_stale:
        return False
    distance = nested_get(data.nearest, "relativeTo.distanceKM")
    if not isinstance(distance, (int, float)):
        return False
    return distance <= coordinator.nearby_km


@dataclass(frozen=True, kw_only=True)
class LightningBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a lightning binary sensor."""

    value_fn: Callable[[LightningData, XWeatherLightningCoordinator], bool]


BINARY_SENSORS: tuple[LightningBinarySensorDescription, ...] = (
    LightningBinarySensorDescription(
        key="lightning_detected",
        translation_key="lightning_detected",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=_any_activity,
    ),
    LightningBinarySensorDescription(
        key="lightning_nearby",
        translation_key="lightning_nearby",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=_nearby,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XWeatherLightningConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lightning binary sensors."""
    coordinator = entry.runtime_data

    async_add_entities(
        XWeatherLightningBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class XWeatherLightningBinarySensor(XWeatherLightningEntity, BinarySensorEntity):
    """Boolean view over the lightning data."""

    entity_description: LightningBinarySensorDescription

    def __init__(
        self,
        coordinator: XWeatherLightningCoordinator,
        description: LightningBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return whether the condition is currently met."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data, self.coordinator)
