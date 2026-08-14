"""Minimal async client for the Vaisala Xweather lightning endpoints.

Deliberately Home Assistant agnostic so it can be tested standalone.

API reference: https://www.xweather.com/docs/weather-api/endpoints/lightning
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://data.api.xweather.com"
REQUEST_TIMEOUT = ClientTimeout(total=30)

# Xweather signals "your query was fine, there is simply nothing there" with
# success=false plus a warn_* code. For lightning that is the common case:
# most of the time nothing is striking near you.
EMPTY_RESULT_CODES = frozenset(
    {
        "warn_no_data",
        "warn_no_results",
        "warn_invalid_location",
    }
)

AUTH_ERROR_CODES = frozenset(
    {
        "invalid_client",
        "invalid_grant",
        "auth_error",
        "access_denied",
        "unauthorized_action",
        "invalid_client_id",
        "invalid_client_secret",
    }
)

QUOTA_ERROR_CODES = frozenset(
    {
        "usage_limit_exceeded",
        "plan_limit_exceeded",
        "rate_limit_exceeded",
    }
)


class XWeatherError(Exception):
    """Base error for the Xweather client."""


class XWeatherConnectionError(XWeatherError):
    """Raised when the API could not be reached."""


class XWeatherAuthError(XWeatherError):
    """Raised when the client ID / secret pair was rejected."""


class XWeatherQuotaError(XWeatherError):
    """Raised when the account has exhausted its request allowance."""


class XWeatherLightningClient:
    """Small wrapper around the three lightning endpoints this integration uses."""

    def __init__(
        self,
        session: ClientSession,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Store the session and credentials."""
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret

    async def _async_request(self, path: str, params: dict[str, Any]) -> Any:
        """Perform a GET and unwrap the Xweather response envelope.

        Returns the ``response`` payload, or ``None`` when the API reports that
        no data matched the query.
        """
        url = f"{BASE_URL}{path}"
        query = {
            **{k: str(v) for k, v in params.items() if v is not None},
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "format": "json",
        }

        try:
            async with self._session.get(
                url, params=query, timeout=REQUEST_TIMEOUT
            ) as response:
                if response.status in (401, 403):
                    raise XWeatherAuthError(
                        f"Credentials rejected by Xweather (HTTP {response.status})"
                    )
                if response.status == 429:
                    raise XWeatherQuotaError("Xweather rate limit exceeded")
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise XWeatherConnectionError(f"Timeout contacting {path}") from err
        except aiohttp.ClientResponseError as err:
            raise XWeatherConnectionError(
                f"Xweather returned HTTP {err.status} for {path}"
            ) from err
        except ClientError as err:
            raise XWeatherConnectionError(f"Error contacting {path}: {err}") from err
        except ValueError as err:
            raise XWeatherError(f"Malformed JSON from {path}: {err}") from err

        if not isinstance(payload, dict):
            raise XWeatherError(f"Unexpected payload type from {path}")

        if not payload.get("success"):
            error = payload.get("error") or {}
            code = str(error.get("code", "")).lower()
            description = error.get("description", "no description")

            if code in EMPTY_RESULT_CODES:
                _LOGGER.debug("%s returned no data (%s)", path, code)
                return None
            if code in AUTH_ERROR_CODES:
                raise XWeatherAuthError(f"{code}: {description}")
            if code in QUOTA_ERROR_CODES or "limit" in code:
                raise XWeatherQuotaError(f"{code}: {description}")
            raise XWeatherError(f"{path} failed: {code}: {description}")

        return payload.get("response")

    @staticmethod
    def _first(response: Any) -> dict[str, Any] | None:
        """Normalise a response that may be an object or a single-item array."""
        if isinstance(response, list):
            return response[0] if response else None
        if isinstance(response, dict):
            return response
        return None

    async def async_get_summary(
        self, latitude: float, longitude: float, radius_km: int, window_minutes: int
    ) -> dict[str, Any] | None:
        """Return aggregate pulse counts for the area over the lookback window.

        Uses /lightning/summary, which reports counts broken down by
        cloud-to-ground vs intracloud and by polarity, plus peak amplitude
        statistics.
        """
        response = await self._async_request(
            "/lightning/summary/closest",
            {
                "p": f"{latitude},{longitude}",
                "radius": f"{radius_km}km",
                "from": f"-{window_minutes}minutes",
                "limit": 1,
            },
        )
        record = self._first(response)
        if record is None:
            return None
        # The payload nests everything under "summary".
        summary = record.get("summary")
        return summary if isinstance(summary, dict) else record

    async def async_get_nearest_pulse(
        self, latitude: float, longitude: float, radius_km: int, window_minutes: int
    ) -> dict[str, Any] | None:
        """Return the single closest lightning pulse, or None if the area is quiet.

        Uses /lightning with the ``closest`` action, which populates a
        ``relativeTo`` block containing distance and bearing from the queried
        coordinates.
        """
        response = await self._async_request(
            "/lightning/closest",
            {
                "p": f"{latitude},{longitude}",
                "radius": f"{radius_km}km",
                "from": f"-{window_minutes}minutes",
                "limit": 1,
            },
        )
        return self._first(response)

    async def async_get_threat(
        self, latitude: float, longitude: float, radius_km: int
    ) -> dict[str, Any] | None:
        """Return the nearest active lightning threat nowcast, if any.

        Uses /lightning/threats, which forecasts up to 60 minutes of potential
        thunderstorm activity in 10 minute intervals. Note the 10x request
        multiplier on this endpoint.
        """
        response = await self._async_request(
            "/lightning/threats/closest",
            {
                "p": f"{latitude},{longitude}",
                "radius": f"{radius_km}km",
                "limit": 1,
            },
        )
        return self._first(response)

    async def async_validate_credentials(
        self, latitude: float, longitude: float
    ) -> None:
        """Raise if the credentials or coordinates are not usable.

        A quiet sky is a valid outcome here, so "no data" counts as success.
        """
        await self._async_request(
            "/lightning/summary/closest",
            {
                "p": f"{latitude},{longitude}",
                "radius": "50km",
                "from": "-5minutes",
                "limit": 1,
            },
        )
