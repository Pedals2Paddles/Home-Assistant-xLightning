# Changelog

All notable changes to this project are documented here.

This project follows [Semantic Versioning](https://semver.org/).

> **On this repository's git history.** The integration was developed before
> this repository existed, and no snapshots of the intermediate states were
> kept — only the final tree. Reconstructing per-version commits would mean
> committing file contents that never actually existed, so the repository
> starts from a single commit of the real code at 0.7.0. This changelog is the
> accurate record of how it got here; git history from 0.7.0 forward is real.

## [0.12.0]

### Changed
- **Search radius** and **Nearby alert distance** in the options form now
  display in Home Assistant's configured distance unit (km, mi, or whatever
  the "Distance" preference in General Settings is set to) instead of always
  showing km. Both are still stored internally in km — everything else in
  the integration, including the Xweather API calls themselves, is
  unaffected. Conversion happens only at the edges of the options form, via
  `homeassistant.util.unit_conversion.DistanceConverter`.

## [0.11.0]

### Removed
- **The `Lightning activity` sensor.** It existed to keep something readable
  while the "Nearest ..." sensors blank to `unknown`, but the sensor's own
  three states (`Active` / `Recently cleared` / `Clear`) needed their own
  explanation on top of retention's — a second thing to understand in
  service of un-confusing the first. Removed rather than reworded; retention
  is documented directly in the README's Retention section without it.
- The internal three-state activity value it exposed (`active` / `recent` /
  `clear`) is **not** gone — it still drives the lightning map's refresh
  gating in `image.py`, which refreshes on activity transitions rather than
  every poll. Only the user-facing sensor and its now-unused `ACTIVITY_STATES`
  enum-options constant were removed.

## [0.10.1]

### Fixed
- **The `/lightning`-dependent entities did not actually hide when detailed
  polling was off.** 0.10.0's fix relied on `entity_registry_visible_default`
  alone, which Home Assistant's entity registry only ever consults the first
  time an entity is registered — it is never re-applied on a later reload, so
  toggling the option after initial setup had no visible effect on entities
  that already existed. Fixed by explicitly reconciling each entity's
  `hidden_by` state against the current option value on every setup
  (`entity.py`'s new `sync_gated_visibility()`), while leaving alone any
  entity the user has manually hidden or shown themselves.
- **Enable Detailed Strike Polling could persist as off on entries that
  predate the option**, with no stored value to read a fallback from.
  `async_setup_entry` now backfills the option explicitly to its default the
  first time it finds an entry missing it, rather than relying on `.get()`
  fallbacks at every read site.

## [0.10.0]

### Changed
- **The `/lightning`-dependent entities hide themselves, rather than showing
  `unknown`, while Enable Detailed Strike Polling is off.** The seven
  "Nearest ..." sensors and the `Lightning nearby` binary sensor are hidden
  (not disabled) whenever they have no possible value to show — the entities
  still exist and can be manually unhidden, but stay out of the default
  dashboard and area views. Turning detailed polling back on unhides them
  automatically, without a new entity ID. The always-available sensors
  (activity, aggregate counts, diagnostics) are unaffected.
- The lightning map image entity is deliberately **not** given the same
  treatment: it stays fully uncreated (not just hidden) when map frames is 0.
  A hidden-but-present map entity could still be manually surfaced and
  trigger a real 10x-multiplier Raster Maps fetch on a map explicitly turned
  off, which the current not-created behavior makes impossible.

## [0.9.0]

### Changed
- **`skip_when_clear` is now `enable_detailed_polling`, with a different
  meaning.** The old toggle only gated whether a poll skipped the 10x
  `/lightning` query when the summary reported nothing — turning it off made
  the integration query `/lightning` on every poll regardless, including
  polls the summary had already proven were empty. That mode is gone: there
  is no longer any way to poll `/lightning` unconditionally. The toggle now
  simply enables or disables the individual-strike `Nearest ...` sensors.
  When enabled, the 10x query still only fires on polls where the summary
  found at least one pulse, exactly as before. When disabled, only the 1x
  summary is polled and the `Nearest ...` sensors stay unknown — useful if
  you only want the aggregate counts and never need strike-level detail.
- **Lightning map refresh cadence is no longer tied to this option.**
  Previously, turning the toggle off also made the map image refresh on
  every poll instead of only on activity changes, as a freshness escape
  hatch. That coupling is removed: the map now always refreshes only on
  activity transitions, regardless of the detailed-polling setting.

## [0.8.0]

### Removed
- **Storm threat nowcasts.** The `/lightning/threats` endpoint carries the
  same 10x request multiplier as `/lightning`, so polling it on top of the
  main strike query was too expensive for the free tier's request allowance.
  The nowcast data was also of limited use without a map to show it against,
  which is a further expense on its own. Removed the `enable_threats` option,
  the `threat_active` / `threat_severe` binary sensors, the `threat_speed` /
  `threat_heading` / `threat_expires` sensors, and the `threats_requests`
  diagnostics field.

## [0.7.0]

### Fixed
- **Map size dropdown rejected its own default** with `expected str`. The
  `SelectSelector` options were strings but the default was the stored
  integer, so the form failed validation until the field was reselected.
- Map refreshes now honour **Skip Detailed API Calls When Clear**. Previously
  the toggle governed only the strike query while map refresh was gated
  separately on activity, making the setting's description untrue.

### Changed
- Renamed and rewrote the option labels and descriptions for
  `skip_when_clear` and `map_frames` to explain the 10x request multiplier and
  its effect on the free tier's request allowance.
- **Nearest strike type** and **Nearest strike direction** now report an
  explicit `None` rather than `unknown` once retention expires. Numeric and
  timestamp sensors cannot do this — a non-numeric state breaks their
  statistics and unit conversion — so they still report `unknown`. Use
  **Lightning activity** as the "is this working?" indicator.
- Every entity is now enabled by default except **Search radius**.

## [0.6.0]

### Changed
- Collapsed the separate map on/off toggle into the frame count: `0` creates
  no image entity, `1` a still, `2`–`24` an animated GIF.

### Documented
- Why Raster Maps rather than MapsGL: MapsGL renders client-side in WebGL and
  produces no server-fetchable URL, so it cannot back an `image` entity.

## [0.5.0]

### Added
- **Lightning map** image entity using Xweather Raster Maps, framed by the
  bounding-box request form to the search radius plus 10% padding.
- Lightning layer timeframe follows the configured lookback window (5m or 15m).
- Optional animated GIF assembled locally from time-offset stills, since
  Raster Maps animation is a client-side SDK feature with no GIF endpoint.
- Map imagery is fetched lazily on view, so a closed dashboard costs nothing.

## [0.4.0]

### Added
- **Skip Detailed API Calls When Clear**: the 1x summary gates the 10x
  `/lightning` query. Both use the same radius and window, so a zero pulse
  count means the strike query provably has nothing to return. Cuts a quiet
  poll from 11 request units to 1.
- **API requests** diagnostic sensor with a per-endpoint breakdown.

### Notes
- Threat nowcasts are deliberately **not** gated: they cover storms
  approaching from outside the search radius and can legitimately fire while
  the local pulse count is zero.

## [0.3.0]

### Added
- **Lightning activity** enum sensor (`Active` / `Recently cleared` / `Clear`)
  that always has a value, so a quiet sky is never confused with a failure.
- **Retention**: the last strike keeps being reported for a configurable
  period after the sky clears, with the age recomputed each poll.

### Fixed
- **Lightning nearby** explicitly ignores retained strikes. Without this,
  retention would have latched the proximity alert on for the whole retention
  period after a storm had passed.

## [0.2.0]

### Added
- **Reconfigure flow** for editing coordinates, name, and credentials after
  setup. Entity unique IDs derive from the config entry ID rather than the
  coordinates, so moving the location preserves all entities and history.

### Fixed
- A failed setup submission no longer discards what was typed.

## [0.1.0]

### Added
- Initial release. Config flow with map-picker coordinates and the
  client ID / secret key pair, one device per monitored location.
- Sensors from `/lightning/summary` (pulse counts by type and polarity, peak
  amplitude, last pulse) and `/lightning` (nearest strike distance, bearing,
  direction, type, amplitude, time, age).
- Optional storm nowcast entities from `/lightning/threats`.
- Binary sensors for lightning detected and lightning nearby.
- `DataUpdateCoordinator` with reauth on credential failure, and diagnostics
  with credentials redacted.
