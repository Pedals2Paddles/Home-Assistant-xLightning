"""Xweather Raster Maps URL construction.

Reference:
  https://www.xweather.com/docs/maps/getting-started/static-maps
  https://www.xweather.com/docs/maps/getting-started/time-offsets

Kept separate from the image entity so the geometry can be tested without
Home Assistant.
"""

from __future__ import annotations

import math

MAPS_BASE_URL = "https://maps.api.xweather.com"

# Mean length of a degree of latitude, in km. Longitude degrees shrink by
# cos(latitude), which is applied below.
KM_PER_DEGREE_LAT = 111.32

# Web Mercator cannot render beyond roughly +/- 85 degrees.
MAX_MERCATOR_LAT = 85.0

# Fraction of extra area beyond the search radius, so strikes sitting exactly
# on the edge are not clipped by the frame.
MAP_PADDING = 1.1

# Base and boundary layers per style. The lightning layer is appended
# separately because its code depends on the configured lookback window.
MAP_STYLES: dict[str, tuple[str, ...]] = {
    # (layers before lightning, layers after lightning)
    "icons": ("flat-dk", "admin-dk,counties-dk"),
    "circles": ("flat-dk", "admin-dk,counties-dk"),
    "radar": ("flat-dk,radar:80", "admin-dk,counties-dk"),
}


def bounding_box(
    latitude: float, longitude: float, radius_km: float, padding: float = MAP_PADDING
) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) covering the radius plus padding.

    The API derives centre and zoom from the box, so this is the whole of the
    "centre on the coordinates, zoom to fit" requirement.
    """
    reach_km = radius_km * padding

    delta_lat = reach_km / KM_PER_DEGREE_LAT

    # Longitude degrees converge toward the poles. Clamp the cosine so a
    # location very near a pole widens the box instead of dividing by zero.
    cos_lat = max(math.cos(math.radians(latitude)), 0.01)
    delta_lon = reach_km / (KM_PER_DEGREE_LAT * cos_lat)

    south = max(latitude - delta_lat, -MAX_MERCATOR_LAT)
    north = min(latitude + delta_lat, MAX_MERCATOR_LAT)

    # Clamping can invert the box for a location beyond the renderable
    # latitude range. Slide the band back inside the limit instead.
    if south >= north:
        if latitude > 0:
            north = MAX_MERCATOR_LAT
            south = MAX_MERCATOR_LAT - 2 * delta_lat
        else:
            south = -MAX_MERCATOR_LAT
            north = -MAX_MERCATOR_LAT + 2 * delta_lat

    west = longitude - delta_lon
    east = longitude + delta_lon

    # A box wider than the world is meaningless; pin it to full width.
    if east - west >= 360:
        west, east = -180.0, 180.0
    else:
        west = _wrap_longitude(west)
        east = _wrap_longitude(east)

    return (round(south, 4), round(west, 4), round(north, 4), round(east, 4))


def _wrap_longitude(value: float) -> float:
    """Normalise a longitude into [-180, 180]."""
    return ((value + 180) % 360) - 180


def lightning_layer(window_minutes: int, style: str) -> str:
    """Pick the lightning layer whose timeframe best matches the data window.

    Raster Maps offers 5 minute and 15 minute lightning layers. Matching the
    map to the configured lookback keeps the picture and the sensor counts
    telling the same story.
    """
    timeframe = "5m" if window_minutes <= 5 else "15m"
    if style == "circles":
        return f"lightning-strikes-{timeframe}"
    return f"lightning-strikes-{timeframe}-icons"


def build_layers(window_minutes: int, style: str) -> str:
    """Assemble the comma separated layer stack, drawn in order."""
    before, after = MAP_STYLES.get(style, MAP_STYLES["icons"])
    return f"{before},{lightning_layer(window_minutes, style)},{after}"


def frame_offsets(frames: int, step_minutes: int = 5) -> list[str]:
    """Return time offsets oldest to newest, ending at the current frame.

    Offsets must use whole numbers; the API rejects decimals.
    """
    if frames <= 1:
        return ["current"]
    offsets = [
        f"-{(frames - 1 - index) * step_minutes}minutes" for index in range(frames - 1)
    ]
    offsets.append("current")
    return offsets


def static_map_url(
    client_id: str,
    client_secret: str,
    latitude: float,
    longitude: float,
    radius_km: float,
    window_minutes: int,
    size: int,
    style: str,
    offset: str = "current",
    image_format: str = "png",
) -> str:
    """Build one Raster Maps static image URL using the bounding box form."""
    south, west, north, east = bounding_box(latitude, longitude, radius_km)
    layers = build_layers(window_minutes, style)
    return (
        f"{MAPS_BASE_URL}/{client_id}_{client_secret}/{layers}"
        f"/{size}x{size}/{south},{west},{north},{east}/{offset}.{image_format}"
    )


def redact(url: str) -> str:
    """Strip credentials from a URL so it is safe to log."""
    parts = url.split("/")
    if len(parts) > 3:
        parts[3] = "***_***"
    return "/".join(parts)
