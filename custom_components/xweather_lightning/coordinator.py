"""Data update coordinator for the Xweather Lightning integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    XWeatherAuthError,
    XWeatherError,
    XWeatherLightningClient,
    XWeatherQuotaError,
)
from .const import (
    ACTIVITY_ACTIVE,
    ACTIVITY_CLEAR,
    ACTIVITY_RECENT,
    CONF_ENABLE_THREATS,
    CONF_MAP_FRAMES,
    CONF_MAP_SIZE,
    CONF_MAP_STYLE,
    CONF_NEARBY_KM,
    CONF_RADIUS_KM,
    CONF_RETENTION_MINUTES,
    CONF_SCAN_INTERVAL,
    CONF_SKIP_WHEN_CLEAR,
    CONF_WINDOW_MINUTES,
    DEFAULT_ENABLE_THREATS,
    DEFAULT_MAP_FRAMES,
    DEFAULT_MAP_SIZE,
    DEFAULT_MAP_STYLE,
    DEFAULT_NEARBY_KM,
    DEFAULT_RADIUS_KM,
    DEFAULT_RETENTION_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SKIP_WHEN_CLEAR,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
)

if TYPE_CHECKING:
    from . import XWeatherLightningConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LightningData:
    """Snapshot of everything the entities need from one refresh."""

    summary: dict[str, Any] | None = None
    nearest: dict[str, Any] | None = None
    threat: dict[str, Any] | None = None
    # True when `nearest` is a retained strike from an earlier poll rather than
    # something detected in the current window.
    nearest_stale: bool = False
    # Recomputed every poll so the age keeps climbing while a strike is
    # retained. Also means the payload differs each poll, which lets
    # always_update=False still push state writes during the retention period.
    nearest_age_seconds: int | None = None
    activity: str = ACTIVITY_CLEAR
    # True when the expensive /lightning query was skipped because the cheap
    # summary reported nothing to find.
    nearest_skipped: bool = False
    # Cumulative HTTP requests per endpoint since the entry was loaded. Carried
    # in the payload so the diagnostic counter keeps ticking during long quiet
    # spells, when nothing else in the payload changes.
    requests_summary: int = 0
    requests_lightning: int = 0
    requests_threats: int = 0
    requests_maps: int = 0


class XWeatherLightningCoordinator(DataUpdateCoordinator[LightningData]):
    """Poll the Xweather lightning endpoints for a single location."""

    config_entry: XWeatherLightningConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: XWeatherLightningConfigEntry,
        client: XWeatherLightningClient,
    ) -> None:
        """Initialise the coordinator from the entry's options."""
        self.client = client
        # Last strike seen, kept across polls so the sky going quiet reads as
        # history rather than as a failure. Lost on restart; see README.
        self._retained_nearest: dict[str, Any] | None = None
        self._requests_summary = 0
        self._requests_lightning = 0
        self._requests_threats = 0
        self._requests_maps = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            # The payload is a plain dataclass of JSON, so equality comparison
            # is cheap and lets HA skip redundant state writes.
            always_update=False,
        )

    @property
    def latitude(self) -> float:
        """Return the monitored latitude."""
        return float(self.config_entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        """Return the monitored longitude."""
        return float(self.config_entry.data[CONF_LONGITUDE])

    @property
    def radius_km(self) -> int:
        """Return the search radius in kilometres."""
        return int(self.config_entry.options.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM))

    @property
    def window_minutes(self) -> int:
        """Return the lookback window in minutes."""
        return int(
            self.config_entry.options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)
        )

    @property
    def nearby_km(self) -> int:
        """Return the distance at which a strike counts as 'nearby'."""
        return int(self.config_entry.options.get(CONF_NEARBY_KM, DEFAULT_NEARBY_KM))

    @property
    def retention_minutes(self) -> int:
        """Return how long a strike keeps being reported after it clears."""
        return int(
            self.config_entry.options.get(
                CONF_RETENTION_MINUTES, DEFAULT_RETENTION_MINUTES
            )
        )

    @property
    def map_enabled(self) -> bool:
        """Return whether a map image entity should exist at all."""
        return self.map_frames > 0

    @property
    def map_style(self) -> str:
        """Return the map layer style."""
        return str(
            self.config_entry.options.get(CONF_MAP_STYLE, DEFAULT_MAP_STYLE)
        )

    @property
    def map_size(self) -> int:
        """Return the square map edge length in pixels."""
        return int(self.config_entry.options.get(CONF_MAP_SIZE, DEFAULT_MAP_SIZE))

    @property
    def map_frames(self) -> int:
        """Return the frame count: 0 no map, 1 a still, more an animation."""
        return max(
            0,
            int(self.config_entry.options.get(CONF_MAP_FRAMES, DEFAULT_MAP_FRAMES)),
        )

    def note_map_requests(self, count: int) -> None:
        """Record Raster Maps requests made outside the poll cycle.

        The image entity fetches lazily on view, so these land between polls
        and surface on the counter at the next refresh.
        """
        self._requests_maps += count

    @property
    def skip_when_clear(self) -> bool:
        """Return whether to skip /lightning when the summary reports nothing."""
        return bool(
            self.config_entry.options.get(
                CONF_SKIP_WHEN_CLEAR, DEFAULT_SKIP_WHEN_CLEAR
            )
        )

    @property
    def threats_enabled(self) -> bool:
        """Return whether the threats endpoint should be polled."""
        return bool(
            self.config_entry.options.get(CONF_ENABLE_THREATS, DEFAULT_ENABLE_THREATS)
        )

    async def _async_update_data(self) -> LightningData:
        """Fetch the current lightning picture for this location.

        Two phases. The cheap summary and the threat nowcast go out together;
        the expensive /lightning strike query only follows if the summary says
        there is something to find.

        Threats are deliberately NOT gated on the summary. A nowcast covers
        storms approaching from outside the search radius, so it can and should
        report a threat while the local pulse count is still zero. Gating it
        would defeat the early warning it exists to provide.
        """
        lat = self.latitude
        lon = self.longitude
        radius = self.radius_km
        window = self.window_minutes

        # --- Phase 1: cheap summary, plus the independent threat nowcast ---
        phase_one: list[Any] = [
            self.client.async_get_summary(lat, lon, radius, window)
        ]
        if self.threats_enabled:
            phase_one.append(self.client.async_get_threat(lat, lon, radius))

        try:
            phase_one_results = await asyncio.gather(*phase_one)
            self._requests_summary += 1
            if self.threats_enabled:
                self._requests_threats += 1

            summary = phase_one_results[0]
            threat = phase_one_results[1] if self.threats_enabled else None

            pulses = self._pulse_count(summary)

            # --- Phase 2: strike detail, only when phase 1 found activity ---
            skipped = self.skip_when_clear and pulses == 0
            if skipped:
                _LOGGER.debug(
                    "Summary reports 0 pulses within %s km over %s min; "
                    "skipping the /lightning query",
                    radius,
                    window,
                )
                live_nearest = None
            else:
                live_nearest = await self.client.async_get_nearest_pulse(
                    lat, lon, radius, window
                )
                self._requests_lightning += 1

        except XWeatherAuthError as err:
            # Triggers the reauth flow rather than an endless retry loop.
            raise ConfigEntryAuthFailed(str(err)) from err
        except XWeatherQuotaError as err:
            raise UpdateFailed(f"Xweather request allowance exhausted: {err}") from err
        except XWeatherError as err:
            raise UpdateFailed(f"Error fetching lightning data: {err}") from err

        nearest, stale = self._apply_retention(live_nearest)
        age = self._age_seconds(nearest)

        if pulses > 0 or (nearest is not None and not stale):
            activity = ACTIVITY_ACTIVE
        elif nearest is not None:
            activity = ACTIVITY_RECENT
        else:
            activity = ACTIVITY_CLEAR

        return LightningData(
            summary=summary,
            nearest=nearest,
            threat=threat,
            nearest_stale=stale,
            nearest_age_seconds=age,
            activity=activity,
            nearest_skipped=skipped,
            requests_summary=self._requests_summary,
            requests_lightning=self._requests_lightning,
            requests_threats=self._requests_threats,
            requests_maps=self._requests_maps,
        )

    @staticmethod
    def _pulse_count(summary: dict[str, Any] | None) -> int:
        """Total pulses reported by the summary, treating no data as zero."""
        if not summary:
            return 0
        # An explicit "pulse": null is a valid quiet-sky response, so this
        # cannot chain .get() straight through.
        pulse = summary.get("pulse")
        count = pulse.get("count") if isinstance(pulse, dict) else None
        return int(count) if isinstance(count, (int, float)) else 0

    def _apply_retention(
        self, live_nearest: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, bool]:
        """Return the strike to report and whether it is retained history.

        A quiet sky means the API returns nothing, which would otherwise blank
        every "Nearest ..." sensor to unknown and look indistinguishable from a
        broken poll. Instead the last strike is held for the retention period.
        """
        if live_nearest is not None:
            self._retained_nearest = live_nearest
            return live_nearest, False

        retention = self.retention_minutes
        if retention <= 0 or self._retained_nearest is None:
            self._retained_nearest = None
            return None, False

        age = self._age_seconds(self._retained_nearest)
        if age is None or age > retention * 60:
            # Older than the retention period: let it fall back to unknown.
            self._retained_nearest = None
            return None, False

        return self._retained_nearest, True

    @staticmethod
    def _age_seconds(pulse: dict[str, Any] | None) -> int | None:
        """Seconds between the pulse and now, recomputed each poll."""
        if pulse is None:
            return None
        timestamp = pulse.get("ob", {}).get("timestamp")
        if not isinstance(timestamp, (int, float)):
            return None
        return max(0, int(dt_util.utcnow().timestamp() - timestamp))
