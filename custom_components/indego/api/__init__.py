"""Bosch Indego API Client Module."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TypeVar, Generic, Callable, Awaitable

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import ConfigEntryAuthFailed

from ..const import DOMAIN, UPDATE_INTERVAL
from ..exceptions import (
    IndegoAuthenticationError,
    IndegoConnectionError,
    IndegoRequestError,
    IndegoRateLimitError
)

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

class IndegoApiClient:
    """Modern API client for Bosch Indego mowers."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: str,
        token_refresh_method: Optional[Callable[[], Awaitable[str]]] = None,
        serial: Optional[str] = None,
        api_url: str = "https://api.indego.iot.bosch-si.com/api/v1/",
    ) -> None:
        """Initialize the API client."""
        self.hass = hass
        self._token = token
        self._token_refresh_method = token_refresh_method
        self._serial = serial
        self._api_url = api_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_remaining = 150  # Requests per minute
        self._rate_limit_reset = datetime.now()
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, timedelta] = {
            "state": timedelta(seconds=5),
            "generic_data": timedelta(minutes=5),
            "alerts": timedelta(minutes=1),
            "calendar": timedelta(minutes=5),
        }
        self._last_request_time: Dict[str, datetime] = {}

    async def initialize(self) -> None:
        """Initialize the client session."""
        if not self._session:
            self._session = aiohttp.ClientSession()

    async def shutdown(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None

    def _check_rate_limit(self) -> None:
        """Check if we can make a request based on rate limits."""
        now = datetime.now()
        if now >= self._rate_limit_reset:
            self._rate_limit_remaining = 150
            self._rate_limit_reset = now + timedelta(minutes=1)
        
        if self._rate_limit_remaining <= 0:
            raise IndegoRateLimitError("Rate limit exceeded")
        
        self._rate_limit_remaining -= 1

    async def _handle_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        cache_key: Optional[str] = None,
        force_update: bool = False,
    ) -> Any:
        """Make an API request with error handling and caching."""
        if not self._session:
            await self.initialize()

        # Check cache if enabled
        if cache_key and not force_update:
            cached_data = self._cache.get(cache_key)
            cache_time = self._last_request_time.get(cache_key)
            cache_ttl = self._cache_ttl.get(cache_key, timedelta(minutes=5))
            
            if cached_data and cache_time:
                if datetime.now() - cache_time < cache_ttl:
                    return cached_data

        # Rate limiting check
        self._check_rate_limit()

        # Prepare headers
        request_headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            **headers or {}
        }

        try:
            # Make request
            url = f"{self._api_url.rstrip('/')}/{endpoint.lstrip('/')}"
            async with self._session.request(
                method,
                url,
                params=params,
                json=data,
                headers=request_headers,
                timeout=30,
            ) as response:
                # Update rate limits from headers
                if "X-RateLimit-Remaining" in response.headers:
                    self._rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])
                
                # Handle common errors
                if response.status == 401:
                    if self._token_refresh_method:
                        self._token = await self._token_refresh_method()
                        return await self._handle_request(
                            method, endpoint, params, data, headers, cache_key, force_update
                        )
                    raise IndegoAuthenticationError("Authentication failed")
                
                response.raise_for_status()
                result = await response.json()

                # Update cache
                if cache_key:
                    self._cache[cache_key] = result
                    self._last_request_time[cache_key] = datetime.now()

                return result

        except asyncio.TimeoutError as err:
            raise IndegoConnectionError(f"Request timed out: {err}") from err
        except aiohttp.ClientError as err:
            raise IndegoConnectionError(f"Connection error: {err}") from err

    async def get_state(self, force_update: bool = False) -> Dict:
        """Get the current state of the mower."""
        return await self._handle_request(
            "GET",
            f"alms/{self._serial}/state",
            cache_key="state",
            force_update=force_update
        )

    async def get_generic_data(self) -> Dict:
        """Get generic data about the mower."""
        return await self._handle_request(
            "GET",
            f"alms/{self._serial}",
            cache_key="generic_data"
        )

    async def put_command(self, command: str) -> Dict:
        """Send a command to the mower."""
        return await self._handle_request(
            "PUT",
            f"alms/{self._serial}/state",
            data={"state": command}
        )

    async def get_alerts(self) -> Dict:
        """Get alerts from the mower."""
        return await self._handle_request(
            "GET",
            f"alms/{self._serial}/alerts",
            cache_key="alerts"
        )

    async def get_calendar(self) -> Dict:
        """Get the mowing calendar."""
        return await self._handle_request(
            "GET",
            f"alms/{self._serial}/calendar",
            cache_key="calendar"
        )
