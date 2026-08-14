"""Config and options flows for the Xweather Lightning integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    XWeatherAuthError,
    XWeatherConnectionError,
    XWeatherError,
    XWeatherLightningClient,
    XWeatherQuotaError,
)
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
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
    MAP_SIZES,
    MAP_STYLE_OPTIONS,
    MAX_MAP_FRAMES,
    MAX_RADIUS_KM,
    MAX_RETENTION_MINUTES,
    MAX_WINDOW_MINUTES,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CONF_LOCATION = "location"


def _options_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the options schema, seeded with the current values."""
    return vol.Schema(
        {
            vol.Required(
                CONF_RADIUS_KM,
                default=options.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_RADIUS_KM,
                    step=1,
                    unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_NEARBY_KM,
                default=options.get(CONF_NEARBY_KM, DEFAULT_NEARBY_KM),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_RADIUS_KM,
                    step=1,
                    unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_WINDOW_MINUTES,
                default=options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_WINDOW_MINUTES,
                    step=1,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=3600,
                    step=30,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RETENTION_MINUTES,
                default=options.get(
                    CONF_RETENTION_MINUTES, DEFAULT_RETENTION_MINUTES
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=MAX_RETENTION_MINUTES,
                    step=5,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SKIP_WHEN_CLEAR,
                default=options.get(CONF_SKIP_WHEN_CLEAR, DEFAULT_SKIP_WHEN_CLEAR),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ENABLE_THREATS,
                default=options.get(CONF_ENABLE_THREATS, DEFAULT_ENABLE_THREATS),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_MAP_STYLE,
                default=options.get(CONF_MAP_STYLE, DEFAULT_MAP_STYLE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=MAP_STYLE_OPTIONS,
                    translation_key="map_style",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_MAP_SIZE,
                # SelectSelector validates against its string options, so the
                # stored integer must be stringified or the form rejects its
                # own default with "expected str".
                default=str(options.get(CONF_MAP_SIZE, DEFAULT_MAP_SIZE)),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[str(size) for size in MAP_SIZES],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_MAP_FRAMES,
                default=options.get(CONF_MAP_FRAMES, DEFAULT_MAP_FRAMES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=MAX_MAP_FRAMES,
                    step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _setup_schema() -> vol.Schema:
    """Schema shared by initial setup and reconfigure.

    No defaults are baked in — callers seed the form with
    ``add_suggested_values_to_schema`` so that a failed submission redisplays
    what the user typed rather than resetting it.
    """
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Required(CONF_CLIENT_ID): selector.TextSelector(),
            vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_LOCATION): selector.LocationSelector(
                selector.LocationSelectorConfig(radius=False)
            ),
        }
    )


def _coordinates(user_input: dict[str, Any]) -> tuple[float, float]:
    """Pull rounded latitude and longitude out of the location selector value."""
    location = user_input[CONF_LOCATION]
    return (
        round(float(location[CONF_LATITUDE]), 5),
        round(float(location[CONF_LONGITUDE]), 5),
    )


async def _async_validate(
    hass, client_id: str, client_secret: str, latitude: float, longitude: float
) -> str | None:
    """Return an error key, or None if the credentials work."""
    client = XWeatherLightningClient(
        async_get_clientsession(hass), client_id, client_secret
    )
    try:
        await client.async_validate_credentials(latitude, longitude)
    except XWeatherAuthError:
        return "invalid_auth"
    except XWeatherQuotaError:
        return "quota_exceeded"
    except XWeatherConnectionError:
        return "cannot_connect"
    except XWeatherError:
        return "unknown"
    except Exception:  # noqa: BLE001 - surface as a generic form error
        _LOGGER.exception("Unexpected error validating Xweather credentials")
        return "unknown"
    return None


class XWeatherLightningConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setting up a monitored lightning location."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials and the coordinates to monitor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            latitude, longitude = _coordinates(user_input)

            await self.async_set_unique_id(f"{latitude}_{longitude}")
            self._abort_if_unique_id_configured()

            error = await _async_validate(
                self.hass,
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                latitude,
                longitude,
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                    },
                    options={
                        CONF_RADIUS_KM: DEFAULT_RADIUS_KM,
                        CONF_NEARBY_KM: DEFAULT_NEARBY_KM,
                        CONF_WINDOW_MINUTES: DEFAULT_WINDOW_MINUTES,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_RETENTION_MINUTES: DEFAULT_RETENTION_MINUTES,
                        CONF_SKIP_WHEN_CLEAR: DEFAULT_SKIP_WHEN_CLEAR,
                        CONF_ENABLE_THREATS: DEFAULT_ENABLE_THREATS,
                        CONF_MAP_STYLE: DEFAULT_MAP_STYLE,
                        CONF_MAP_SIZE: DEFAULT_MAP_SIZE,
                        CONF_MAP_FRAMES: DEFAULT_MAP_FRAMES,
                    },
                )

        suggested = user_input or {
            CONF_NAME: "Home Lightning",
            CONF_LOCATION: {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
            },
        }

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _setup_schema(), suggested
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit an existing location: coordinates, name, or credentials.

        Coordinates live in the entry data rather than the options because they
        form the entry's unique ID, so they are changed here rather than through
        the options flow. Entity unique IDs are derived from the entry ID, not
        the coordinates, so moving the marker preserves all existing entities
        and their recorded history.
        """
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            latitude, longitude = _coordinates(user_input)
            new_unique_id = f"{latitude}_{longitude}"

            # Only re-check uniqueness when the coordinates actually moved,
            # otherwise the entry being reconfigured would collide with itself.
            if new_unique_id != entry.unique_id:
                await self.async_set_unique_id(new_unique_id)
                self._abort_if_unique_id_configured()

            error = await _async_validate(
                self.hass,
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                latitude,
                longitude,
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_unique_id,
                    title=user_input[CONF_NAME],
                    data={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                    },
                    reason="reconfigure_successful",
                )

        suggested = user_input or {
            CONF_NAME: entry.title,
            CONF_CLIENT_ID: entry.data.get(CONF_CLIENT_ID),
            CONF_CLIENT_SECRET: entry.data.get(CONF_CLIENT_SECRET),
            CONF_LOCATION: {
                CONF_LATITUDE: entry.data[CONF_LATITUDE],
                CONF_LONGITUDE: entry.data[CONF_LONGITUDE],
            },
        }

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _setup_schema(), suggested
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the credentials stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh client ID and secret."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            error = await _async_validate(
                self.hass,
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                entry.data[CONF_LATITUDE],
                entry.data[CONF_LONGITUDE],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLIENT_ID, default=entry.data.get(CONF_CLIENT_ID)
                    ): selector.TextSelector(),
                    vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return XWeatherLightningOptionsFlow()


class XWeatherLightningOptionsFlow(OptionsFlow):
    """Let the user tune radius, window, interval, and threat polling."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_RADIUS_KM: int(user_input[CONF_RADIUS_KM]),
                    CONF_NEARBY_KM: int(user_input[CONF_NEARBY_KM]),
                    CONF_WINDOW_MINUTES: int(user_input[CONF_WINDOW_MINUTES]),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_RETENTION_MINUTES: int(user_input[CONF_RETENTION_MINUTES]),
                    CONF_SKIP_WHEN_CLEAR: bool(user_input[CONF_SKIP_WHEN_CLEAR]),
                    CONF_ENABLE_THREATS: bool(user_input[CONF_ENABLE_THREATS]),
                    CONF_MAP_STYLE: str(user_input[CONF_MAP_STYLE]),
                    CONF_MAP_SIZE: int(user_input[CONF_MAP_SIZE]),
                    CONF_MAP_FRAMES: int(user_input[CONF_MAP_FRAMES]),
                }
            )

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(self.config_entry.options)
        )
