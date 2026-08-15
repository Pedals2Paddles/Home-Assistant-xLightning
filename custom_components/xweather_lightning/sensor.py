"""Sensor platform for the Xweather Lightning integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import XWeatherLightningConfigEntry
from .const import ACTIVITY_STATES, PULSE_TYPE_CG, PULSE_TYPE_IC
from .coordinator import LightningData, XWeatherLightningCoordinator
from .entity import XWeatherLightningEntity, nested_get, sync_gated_visibility

PARALLEL_UPDATES = 0

PULSE_TYPE_MAP = {
    PULSE_TYPE_CG: "cloud_to_ground",
    PULSE_TYPE_IC: "intracloud",
}

# Explicit "nothing to report" state. Text and enum sensors can carry this, so
# they read as None rather than the ambiguous Unknown. Numeric sensors cannot:
# a non-numeric state breaks their statistics and unit conversion.
STATE_NONE = "none"


def _timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 string from the API into an aware datetime."""
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


def _count(data: LightningData, path: str) -> int:
    """Read a count from the summary, treating a quiet sky as zero.

    Xweather returns no summary record at all when nothing struck, which is
    semantically a count of zero rather than an unknown value. Reporting zero
    keeps long-term statistics and charts continuous.
    """
    if data.summary is None:
        return 0
    value = nested_get(data.summary, path)
    return int(value) if isinstance(value, (int, float)) else 0


@dataclass(frozen=True, kw_only=True)
class LightningSensorDescription(SensorEntityDescription):
    """Describes a lightning sensor and how to derive its value."""

    value_fn: Callable[[LightningData], StateType | datetime]
    attrs_fn: Callable[[LightningData], dict[str, Any]] | None = None
    # True for sensors whose value can only ever come from /lightning. Hidden
    # by default (not disabled) while detailed polling is off, since the
    # entity still exists and has no state to show, but re-enabling the
    # option should make it reappear without a new entity ID.
    requires_detailed_polling: bool = False


def _nearest_attrs(data: LightningData) -> dict[str, Any]:
    """Expose the strike's own coordinates so it can be plotted."""
    if data.nearest is None:
        return {}
    return {
        # True means this strike is outside the current lookback window and is
        # being retained as history, not detected right now.
        "retained": data.nearest_stale,
        "strike_latitude": nested_get(data.nearest, "loc.lat"),
        "strike_longitude": nested_get(data.nearest, "loc.long"),
        "detecting_sensors": nested_get(data.nearest, "ob.pulse.numSensors"),
        "chi_square": nested_get(data.nearest, "ob.pulse.chiSquare"),
    }


def _request_attrs(data: LightningData) -> dict[str, Any]:
    """Break requests down by endpoint so cost can be worked out per plan.

    Deliberately reports raw request counts rather than a currency-like
    "units" figure: the 10x multiplier on /lightning is documented for
    standard access and drops to 1x with the Lightning Enterprise add-on, so
    only the caller knows their real multiplier.
    """
    return {
        "summary_requests": data.requests_summary,
        "lightning_requests": data.requests_lightning,
        "map_requests": data.requests_maps,
        "lightning_skipped_last_poll": data.nearest_skipped,
        "counted_since": "integration load (resets on restart or reload)",
    }


SENSORS: tuple[LightningSensorDescription, ...] = (
    # Always has a value while the integration is running, so "nothing is
    # happening" never looks like "something failed".
    LightningSensorDescription(
        key="activity_status",
        translation_key="activity_status",
        device_class=SensorDeviceClass.ENUM,
        options=ACTIVITY_STATES,
        value_fn=lambda data: data.activity,
    ),
    # --- Aggregate counts over the lookback window (/lightning/summary) ---
    LightningSensorDescription(
        key="pulse_count",
        translation_key="pulse_count",
        icon="mdi:flash",
        native_unit_of_measurement="pulses",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, "pulse.count"),
    ),
    LightningSensorDescription(
        key="cloud_to_ground_count",
        translation_key="cloud_to_ground_count",
        icon="mdi:flash-alert",
        native_unit_of_measurement="pulses",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, "pulse.cg"),
    ),
    LightningSensorDescription(
        key="intracloud_count",
        translation_key="intracloud_count",
        icon="mdi:weather-lightning",
        native_unit_of_measurement="pulses",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, "pulse.ic"),
    ),
    LightningSensorDescription(
        key="positive_count",
        translation_key="positive_count",
        icon="mdi:plus-circle-outline",
        native_unit_of_measurement="pulses",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, "pulse.positive"),
    ),
    LightningSensorDescription(
        key="negative_count",
        translation_key="negative_count",
        icon="mdi:minus-circle-outline",
        native_unit_of_measurement="pulses",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, "pulse.negative"),
    ),
    LightningSensorDescription(
        key="peak_amplitude_max",
        translation_key="peak_amplitude_max",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: nested_get(data.summary, "peakAmp.all.max"),
    ),
    LightningSensorDescription(
        key="peak_amplitude_avg",
        translation_key="peak_amplitude_avg",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: nested_get(data.summary, "peakAmp.all.avg"),
    ),
    LightningSensorDescription(
        key="last_pulse_time",
        translation_key="last_pulse_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: _timestamp(
            nested_get(data.summary, "range.maxDateTimeISO")
        ),
    ),
    # --- Closest individual strike (/lightning with the closest action) ---
    LightningSensorDescription(
        key="nearest_distance",
        translation_key="nearest_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        requires_detailed_polling=True,
        value_fn=lambda data: nested_get(data.nearest, "relativeTo.distanceKM"),
        attrs_fn=_nearest_attrs,
    ),
    LightningSensorDescription(
        key="nearest_bearing",
        translation_key="nearest_bearing",
        icon="mdi:compass-outline",
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=0,
        requires_detailed_polling=True,
        value_fn=lambda data: nested_get(data.nearest, "relativeTo.bearing"),
    ),
    LightningSensorDescription(
        key="nearest_direction",
        translation_key="nearest_direction",
        icon="mdi:compass-rose",
        device_class=SensorDeviceClass.ENUM,
        # Enum options must be slugs, so the API's uppercase bearing is
        # lowercased here and the compass letters come back via translation.
        options=[
            "n", "nne", "ne", "ene", "e", "ese", "se", "sse",
            "s", "ssw", "sw", "wsw", "w", "wnw", "nw", "nnw", STATE_NONE,
        ],
        requires_detailed_polling=True,
        value_fn=lambda data: str(
            nested_get(data.nearest, "relativeTo.bearingENG") or ""
        ).lower()
        or STATE_NONE,
    ),
    LightningSensorDescription(
        key="nearest_type",
        translation_key="nearest_type",
        device_class=SensorDeviceClass.ENUM,
        options=[*PULSE_TYPE_MAP.values(), STATE_NONE],
        requires_detailed_polling=True,
        value_fn=lambda data: PULSE_TYPE_MAP.get(
            str(nested_get(data.nearest, "ob.pulse.type") or "").lower(), STATE_NONE
        ),
    ),
    LightningSensorDescription(
        key="nearest_peak_amplitude",
        translation_key="nearest_peak_amplitude",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        requires_detailed_polling=True,
        value_fn=lambda data: nested_get(data.nearest, "ob.pulse.peakamp"),
    ),
    LightningSensorDescription(
        key="nearest_time",
        translation_key="nearest_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert-outline",
        requires_detailed_polling=True,
        value_fn=lambda data: _timestamp(nested_get(data.nearest, "ob.dateTimeISO")),
    ),
    LightningSensorDescription(
        key="nearest_age",
        translation_key="nearest_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        requires_detailed_polling=True,
        value_fn=lambda data: data.nearest_age_seconds,
    ),
    # --- Diagnostics ---
    LightningSensorDescription(
        key="api_requests",
        translation_key="api_requests",
        icon="mdi:cloud-download-outline",
        native_unit_of_measurement="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            data.requests_summary + data.requests_lightning + data.requests_maps
        ),
        attrs_fn=_request_attrs,
    ),
    LightningSensorDescription(
        key="search_radius",
        translation_key="search_radius",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: None,  # replaced below by the coordinator option
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XWeatherLightningConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lightning sensors for a configured location."""
    coordinator = entry.runtime_data

    sync_gated_visibility(
        hass,
        entry,
        "sensor",
        [d.key for d in SENSORS if d.requires_detailed_polling],
        coordinator.enable_detailed_polling,
    )
    async_add_entities(
        XWeatherLightningSensor(coordinator, description) for description in SENSORS
    )


class XWeatherLightningSensor(XWeatherLightningEntity, SensorEntity):
    """A single data point derived from the lightning API."""

    entity_description: LightningSensorDescription

    def __init__(
        self,
        coordinator: XWeatherLightningCoordinator,
        description: LightningSensorDescription,
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if (
            description.requires_detailed_polling
            and not coordinator.enable_detailed_polling
        ):
            self._attr_entity_registry_visible_default = False

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value."""
        if self.entity_description.key == "search_radius":
            return self.coordinator.radius_km
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra detail for the sensors that carry it."""
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None or self.coordinator.data is None:
            return None
        attrs = {
            k: v for k, v in attrs_fn(self.coordinator.data).items() if v is not None
        }
        return attrs or None
