"""Image platform for the Xweather Lightning integration.

Renders a Raster Maps static image centred on the configured coordinates and
framed to the search radius plus padding. Optionally assembles several
time-offset stills into an animated GIF.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import XWeatherLightningConfigEntry
from .const import (
    ACTIVITY_ACTIVE,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DEFAULT_MAP_FRAMES,
    GIF_FRAME_DURATION_MS,
    MAP_FRAME_STEP_MINUTES,
)
from .coordinator import XWeatherLightningCoordinator
from .entity import XWeatherLightningEntity
from .map import MAP_PADDING, bounding_box, build_layers, frame_offsets, redact, static_map_url

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
FETCH_TIMEOUT = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XWeatherLightningConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lightning map image entity."""
    coordinator = entry.runtime_data
    if not coordinator.map_enabled:
        return
    async_add_entities([XWeatherLightningMap(coordinator)])


class XWeatherLightningMap(XWeatherLightningEntity, ImageEntity):
    """A map of recent strikes around the configured location.

    Imagery is fetched lazily: the entity marks itself stale when there is
    something new worth seeing, but bytes are only requested when something
    actually asks for the image. If no dashboard is open, no map requests are
    made at all.
    """

    _attr_translation_key = "lightning_map"

    def __init__(self, coordinator: XWeatherLightningCoordinator) -> None:
        """Initialise the map entity."""
        XWeatherLightningEntity.__init__(self, coordinator, "lightning_map")
        ImageEntity.__init__(self, coordinator.hass)

        self._session = async_get_clientsession(coordinator.hass)
        self._cached_bytes: bytes | None = None
        self._last_activity: str | None = None
        self._attr_content_type = (
            "image/gif" if coordinator.map_frames > 1 else "image/png"
        )
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the framing so the map can be reasoned about."""
        coordinator = self.coordinator
        south, west, north, east = bounding_box(
            coordinator.latitude, coordinator.longitude, coordinator.radius_km
        )
        return {
            "bounding_box": {
                "south": south,
                "west": west,
                "north": north,
                "east": east,
            },
            "covers_km": round(coordinator.radius_km * MAP_PADDING, 1),
            "padding_pct": round((MAP_PADDING - 1) * 100),
            "layers": build_layers(
                coordinator.window_minutes, coordinator.map_style
            ),
            "frames": coordinator.map_frames,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate the image only when there is something new to show.

        Refreshes on: the first update, any poll reporting active lightning,
        and the transition out of active so the final frame is accurate.
        Steady quiet does not refresh, which is what keeps map requests near
        zero on an ordinary day.
        """
        data = self.coordinator.data
        activity = data.activity if data else None

        should_refresh = (
            self._last_activity is None
            # With the skip option off the user has asked for freshness over
            # thrift, so refresh every poll regardless of activity.
            or not self.coordinator.skip_when_clear
            or activity == ACTIVITY_ACTIVE
            or activity != self._last_activity
        )

        if should_refresh:
            self._cached_bytes = None
            self._attr_image_last_updated = dt_util.utcnow()

        self._last_activity = activity
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return the map bytes, fetching only when the cache is empty."""
        if self._cached_bytes is not None:
            return self._cached_bytes

        try:
            self._cached_bytes = await self._async_render()
        except Exception:  # noqa: BLE001 - never let a map failure break the entity
            _LOGGER.exception("Failed to render the lightning map")
            return None

        return self._cached_bytes

    async def _async_render(self) -> bytes | None:
        """Fetch one still, or several and assemble them into a GIF."""
        coordinator = self.coordinator
        frames = coordinator.map_frames
        offsets = frame_offsets(frames, MAP_FRAME_STEP_MINUTES)

        blobs = await asyncio.gather(
            *(self._async_fetch(offset) for offset in offsets)
        )
        usable = [blob for blob in blobs if blob]
        coordinator.note_map_requests(len(usable))

        if not usable:
            return None
        if len(usable) == 1:
            self._attr_content_type = "image/png"
            return usable[0]

        animated = await self.hass.async_add_executor_job(_assemble_gif, usable)
        if animated is None:
            # Pillow unavailable or assembly failed; the newest still is a
            # perfectly good fallback.
            self._attr_content_type = "image/png"
            return usable[-1]

        self._attr_content_type = "image/gif"
        return animated

    async def _async_fetch(self, offset: str) -> bytes | None:
        """Fetch a single Raster Maps still."""
        coordinator = self.coordinator
        entry = coordinator.config_entry

        url = static_map_url(
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=entry.data[CONF_CLIENT_SECRET],
            latitude=coordinator.latitude,
            longitude=coordinator.longitude,
            radius_km=coordinator.radius_km,
            window_minutes=coordinator.window_minutes,
            size=coordinator.map_size,
            style=coordinator.map_style,
            offset=offset,
        )

        try:
            async with self._session.get(url, timeout=FETCH_TIMEOUT) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Raster Maps returned HTTP %s for %s",
                        response.status,
                        redact(url),
                    )
                    return None
                return await response.read()
        except (TimeoutError, asyncio.TimeoutError):
            _LOGGER.warning("Timeout fetching %s", redact(url))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Error fetching %s: %s", redact(url), err)
        return None


def _assemble_gif(blobs: list[bytes]) -> bytes | None:
    """Combine stills into an animated GIF. Runs in an executor (blocking).

    Pillow is imported here rather than declared as a requirement: it is
    present on essentially every Home Assistant install, and importing it
    lazily avoids pinning a version that could conflict with core's own.
    """
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning(
            "Pillow is not available, so the animated map cannot be assembled. "
            "Falling back to a single still; set frames to 1 to silence this"
        )
        return None

    try:
        frames = [Image.open(BytesIO(blob)).convert("RGB") for blob in blobs]
        first, *rest = frames
        buffer = BytesIO()
        first.save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=rest,
            duration=GIF_FRAME_DURATION_MS,
            loop=0,
            optimize=True,
        )
        return buffer.getvalue()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not assemble the animated map: %s", err)
        return None
