"""Authentication handling for Bosch Indego integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    OAUTH2_CLIENT_ID,
)
from .exceptions import IndegoAuthenticationError

_LOGGER = logging.getLogger(__name__)


class IndegoAuth:
    """Handle authentication with Bosch Indego API."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize auth handler."""
        self.hass = hass
        self._token = token
        self._session = async_get_clientsession(hass)

    async def async_get_access_token(self) -> str:
        """Get a valid access token."""
        if not self._token:
            raise ConfigEntryAuthFailed("No token available")

        if self._token_expired and self._token.get("refresh_token"):
            await self.async_refresh_token()

        return self._token["access_token"]

    async def async_refresh_token(self) -> None:
        """Refresh the access token."""
        try:
            async with self._session.post(
                OAUTH2_TOKEN,
                data={
                    "grant_type": "refresh_token",
                    "client_id": OAUTH2_CLIENT_ID,
                    "refresh_token": self._token["refresh_token"],
                },
            ) as resp:
                resp.raise_for_status()
                self._token = await resp.json()

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise IndegoAuthenticationError(
                f"Failed to refresh access token: {err}"
            ) from err

    @property
    def _token_expired(self) -> bool:
        """Check if the token is expired."""
        import time

        if not self._token:
            return True

        expires_in = self._token.get("expires_in", 0)
        created_at = self._token.get("created_at", time.time())
        
        return time.time() >= created_at + expires_in - 60  # Refresh 1 min before expiry

    async def async_ensure_token_valid(self) -> None:
        """Ensure that the current token is valid."""
        if self._token_expired:
            await self.async_refresh_token()

    @property
    def token(self) -> Optional[Dict[str, Any]]:
        """Return the current token."""
        return self._token

    async def async_validate_token(self) -> bool:
        """Validate that the current token works."""
        try:
            await self.async_ensure_token_valid()
            return True
        except IndegoAuthenticationError:
            return False
