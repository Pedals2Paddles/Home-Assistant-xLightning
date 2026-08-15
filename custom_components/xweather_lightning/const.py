"""Constants for the Xweather Lightning integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "xweather_lightning"

# Config entry data keys
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"

# Options keys
CONF_RADIUS_KM: Final = "radius_km"
CONF_WINDOW_MINUTES: Final = "window_minutes"
CONF_NEARBY_KM: Final = "nearby_km"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_RETENTION_MINUTES: Final = "retention_minutes"
CONF_ENABLE_DETAILED_POLLING: Final = "enable_detailed_polling"
CONF_MAP_STYLE: Final = "map_style"
CONF_MAP_SIZE: Final = "map_size"
CONF_MAP_FRAMES: Final = "map_frames"

# Defaults.
#
# The /lightning endpoint carries a 10x request multiplier and, on standard
# (non-Enterprise) access, caps the radius at 100 km and the lookback at the
# past 5 minutes. A 5 minute poll with a 5 minute window means no gaps and no
# double counting, which is why these are the defaults.
DEFAULT_RADIUS_KM: Final = 50
DEFAULT_WINDOW_MINUTES: Final = 5
DEFAULT_NEARBY_KM: Final = 16  # ~10 miles, a common "seek shelter" threshold
DEFAULT_SCAN_INTERVAL: Final = 300  # seconds
# How long to keep reporting the last strike after the sky goes quiet, so the
# "Nearest ..." sensors read as history rather than as unknown. 0 disables.
DEFAULT_RETENTION_MINUTES: Final = 60
MAX_RETENTION_MINUTES: Final = 1440

# /lightning/summary is 1x; /lightning is 10x. Detailed polling is an
# opt-in tier on top of the summary, not a separate always-on query: when
# enabled, it still only fires on polls where the summary reports at least
# one pulse in the same radius and window, since the strike query provably
# has nothing to return otherwise. There is no mode that polls it
# unconditionally.
DEFAULT_ENABLE_DETAILED_POLLING: Final = True

# Raster Maps. Lightning map layers carry the same 10x multiplier as the data
# endpoint, so imagery is fetched lazily and only when something new is worth
# seeing. Animation multiplies the cost by the frame count, hence 1 by default.
DEFAULT_MAP_STYLE: Final = "icons"
DEFAULT_MAP_SIZE: Final = 640
# Frame count doubles as the on/off switch: 0 creates no image entity at all,
# 1 is a single still, and anything higher assembles that many time-offset
# stills into an animated GIF.
DEFAULT_MAP_FRAMES: Final = 0
MAP_SIZES: Final = [480, 640, 800, 1000]
MAP_STYLE_OPTIONS: Final = ["icons", "circles", "radar"]
MAX_MAP_FRAMES: Final = 24
# Lightning map layers refresh every 5 minutes, so finer steps add cost
# without adding detail.
MAP_FRAME_STEP_MINUTES: Final = 5
GIF_FRAME_DURATION_MS: Final = 600

# Internal activity state, not user-facing. Drives the lightning map's
# refresh gating in image.py: it refreshes while active and on every
# transition between these three, but not on repeated polls that stay clear.
ACTIVITY_ACTIVE: Final = "active"
ACTIVITY_RECENT: Final = "recent"
ACTIVITY_CLEAR: Final = "clear"

MIN_SCAN_INTERVAL: Final = 60
MAX_RADIUS_KM: Final = 100  # standard access ceiling
MAX_WINDOW_MINUTES: Final = 1440  # Enterprise add-on ceiling

ATTRIBUTION: Final = "Data provided by Vaisala Xweather"
MANUFACTURER: Final = "Vaisala Xweather"
MODEL: Final = "Lightning monitoring location"

# Pulse type codes returned by the API
PULSE_TYPE_CG: Final = "cg"
PULSE_TYPE_IC: Final = "ic"
