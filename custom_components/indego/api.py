import asyncio
import logging
import time
from typing import Any, cast

from homeassistant.components.application_credentials import AuthImplementation
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from httpx import AsyncClient, HTTPStatusError, TimeoutException

from .const import API_BASE_URL, API_RETRY_COUNT, API_BACKOFF_FACTOR
from .exceptions import (
    IndegoAuthenticationError,
    IndegoConnectionError,
    IndegoRequestError,
)

_LOGGER = logging.getLogger(__name__)


class IndegoApiClient:
    """Bosch Indego API client."""

    def __init__(self, session: OAuth2Session):
        """Initialize the API client."""
        self._session = session
        self._client = AsyncClient(base_url=API_BASE_URL)

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make a request to the Indego API."""
        await self._session.async_ensure_token_valid()

        headers = {
            "Authorization": f"Bearer {self._session.token['access_token']}",
            "Accept": "application/json",
        }

        for attempt in range(API_RETRY_COUNT):
            try:
                response = await self._client.request(
                    method,
                    endpoint,
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
            except TimeoutException as err:
                _LOGGER.debug("Request timed out: %s", err)
                if attempt == API_RETRY_COUNT - 1:
                    raise IndegoConnectionError("Request timed out") from err
            except HTTPStatusError as err:
                _LOGGER.debug("HTTP error: %s", err)
                if err.response.status_code == 401:
                    raise IndegoAuthenticationError("Authentication failed") from err
                if err.response.status_code in (400, 404):
                    raise IndegoRequestError(f"Invalid request: {err.response.text}") from err
                if attempt == API_RETRY_COUNT - 1:
                    raise IndegoConnectionError(f"HTTP error: {err}") from err
            except Exception as err:
                _LOGGER.debug("Unexpected error: %s", err)
                if attempt == API_RETRY_COUNT - 1:
                    raise IndegoConnectionError(f"Unexpected error: {err}") from err

            await asyncio.sleep(API_BACKOFF_FACTOR * (2 ** attempt))

        raise IndegoConnectionError("Request failed after multiple retries")

    async def get_state(self, force_update: bool = False) -> dict[str, Any]:
        """Get the mower state."""
        return await self._request("GET", "state")

    async def get_calendar(self) -> dict[str, Any]:
        """Get the mower calendar."""
        return await self._request("GET", "calendar")

    async def get_generic_data(self) -> dict[str, Any]:
        """Get generic mower data."""
        return await self._request("GET", "genericdata")

    async def get_alerts(self) -> list[dict[str, Any]]:
        """Get mower alerts."""
        return await self._request("GET", "alerts")


class IndegoLocalOAuth2Implementation(AuthImplementation):
    """Indego Local OAuth2 implementation."""
    @property
    def name(self) -> str:
        """Return name of the implementation."""
        return "Bosch Indego"

    @property
    def domain(self) -> str:
        """Return the domain of the implementation."""
        return "indego"

    @property
    def redirect_uri(self) -> str:
        """Return the redirect uri."""
        return "com.bosch.indegoconnect://login"
        
    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate authorization url."""
        return await super().async_generate_authorize_url(flow_id)


class IndegoOAuth2Session(OAuth2Session):
    """Indego OAuth2 session implementation."""

    @property
    def valid_token(self) -> bool:
        """Return if token is still valid."""
        if not self.token:
            return False

        # The Bosch OAuth server returns an access and refresh token with the same value of 1 day (86400). Misconfiguration?
        # HomeAssistant only refreshes when the access token is expired (actually 20 seconds before expiring; see CLOCK_OUT_OF_SYNC_MAX_SEC).
        # So this could result in token refresh failure and the API start to respond with 400 Bad Request (which requires to the user to reauthenticate).
        # To prevent this we override the default implementation here and set it to expire 12 hours before the real expire time.
        # This means the token is refreshed twice a day.
        #
        # NOTE: The 400 Bad Request issue could still happen if HomeAssistant (or network connection) is offline for more than 12 hours. We can't ḟix this.
        #
        expires_at = cast(float, self.token.get("expires_at", 0))
        is_valid = expires_at > time.time() + 43200  # 12 hours
        _LOGGER.debug(f"Token expires at {time.ctime(expires_at)}, valid: {is_valid}")
        return is_valid
