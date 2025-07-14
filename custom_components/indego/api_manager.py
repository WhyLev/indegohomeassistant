"""API Manager for Indego integration."""
from datetime import datetime, timedelta
import asyncio
import logging
import time
import random
from typing import Any, Dict, Optional

from aiohttp.client_exceptions import (
    ClientResponseError,
    ClientError,
    ServerTimeoutError,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import ATTR_NAME

from .const import (
    API_ERROR_LOG_INTERVAL,
    DEFAULT_STATE_UPDATE_TIMEOUT,
    DEFAULT_LONGPOLL_TIMEOUT,
)
from pyIndego import IndegoAsyncClient

_LOGGER = logging.getLogger(__name__)

class IndegoApiManager:
    """Class to manage API calls with caching and rate limiting."""

    def __init__(self, hass: HomeAssistant, api_client: IndegoAsyncClient):
        """Initialize the API manager."""
        self.hass = hass
        self.api_client = api_client
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._request_timestamps: list = []
        self._rate_limit = 150  # Maximum requests per minute
        self._cache_ttl = {
            'state': timedelta(seconds=5),
            'generic_data': timedelta(minutes=60),
            'alerts': timedelta(minutes=5),
            'operating_data': timedelta(minutes=5),
            'next_mow': timedelta(minutes=5),
            'last_completed_mow': timedelta(minutes=5),
            'predictive_calendar': timedelta(minutes=30),
        }
        self._last_error_time: Dict[str, float] = {}
        self._error_count: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._retry_count: Dict[str, int] = {}
        self._max_retries = 5 
        self._min_retry_delay = 1
        self._max_retry_delay = 60
        self._backoff_factor = 2
        self._request_timeout = 30

    async def _handle_request(self, request_key: str, request_func, *args, **kwargs) -> Any:
        """Handle an API request with retries, rate limiting and caching."""
        async with self._lock:
            # Check cache first
            if self.is_cache_valid(request_key):
                return self._cache.get(request_key)

            # Wait for rate limiting
            await self.wait_for_rate_limit()

            retry_count = 0
            last_exception = None

            while retry_count <= self._max_retries:
                try:
                    # Ensure token is valid before request
                    await self.api_client.start()

                    # Make the request
                    result = await request_func(*args, **kwargs)

                    # Update cache
                    self._cache[request_key] = result
                    self._cache_times[request_key] = datetime.now()
                    self._retry_count[request_key] = 0
                    self._error_count[request_key] = 0

                    return result

                except (ClientResponseError, ServerTimeoutError) as exc:
                    last_exception = exc
                    status = getattr(exc, 'status', 0)
                    
                    # Handle specific status codes
                    if status == 403:  # Forbidden - token likely expired
                        await self.api_client.start()  # Force token refresh
                    elif status == 429:  # Too many requests
                        retry_delay = float(exc.headers.get('Retry-After', self._min_retry_delay))
                        await asyncio.sleep(retry_delay)
                    elif status == 500:  # Server error
                        retry_count += 1
                        retry_delay = self._calculate_retry_delay(retry_count)
                        await asyncio.sleep(retry_delay)
                    else:
                        retry_count += 1
                        retry_delay = self._calculate_retry_delay(retry_count)
                        await asyncio.sleep(retry_delay)

                except Exception as exc:
                    last_exception = exc
                    retry_count += 1
                    retry_delay = self._calculate_retry_delay(retry_count)
                    _LOGGER.warning(
                        "Request failed for %s: %s. Retrying in %.1f seconds (attempt %d/%d)",
                        request_key, exc, retry_delay, retry_count, self._max_retries
                    )
                    await asyncio.sleep(retry_delay)

            # If we get here, all retries failed
            self._error_count[request_key] = self._error_count.get(request_key, 0) + 1
            _LOGGER.error(
                "Request failed for %s after %d retries: %s",
                request_key, self._max_retries, last_exception
            )
            raise last_exception

    def _calculate_retry_delay(self, retry_count: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        delay = min(
            self._min_retry_delay * (self._backoff_factor ** retry_count),
            self._max_retry_delay
        )
        # Add jitter between 75% and 100% of delay
        return delay * (0.75 + (0.25 * random.random()))

    async def check_token(self):
        """Check if token needs refresh and refresh if needed."""
        if not hasattr(self.api_client, 'token_refresh_method'):
            return
            
        if not hasattr(self.api_client, 'valid_token'):
            return
            
        try:
            if not self.api_client.valid_token:
                _LOGGER.debug("Token expired, requesting refresh")
                await self.api_client.start()
        except Exception as exc:
            _LOGGER.error("Error refreshing token: %s", exc)
            raise

    async def ensure_token_valid(self):
        """Ensure the token is valid before making a request."""
        await self.check_token()
        
        # Add pre-request validation
        if not self.api_client or not hasattr(self.api_client, '_session'):
            raise RuntimeError("API client not properly initialized")

    def _clean_old_timestamps(self):
        """Remove timestamps older than 1 minute."""
        current_time = time.time()
        self._request_timestamps = [
            t for t in self._request_timestamps 
            if current_time - t <= 60
        ]

    def can_make_request(self) -> bool:
        """Check if we can make a new request based on rate limits."""
        self._clean_old_timestamps()
        return len(self._request_timestamps) < self._rate_limit

    async def wait_for_rate_limit(self):
        """Wait until we can make another request."""
        while not self.can_make_request():
            await asyncio.sleep(1)
        self._request_timestamps.append(time.time())

    def is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_times:
            return False
            
        ttl = self._cache_ttl.get(cache_key, timedelta(minutes=5))
        return datetime.now() - self._cache_times[cache_key] < ttl

    async def get_state(self, force: bool = False, longpoll: bool = False) -> Any:
        """Get the state from the mower."""
        return await self._handle_request(
            'state',
            self.api_client.get_state,
            force=force,
            longpoll=longpoll
        )

    async def get_generic_data(self) -> Any:
        """Get the generic data from the mower."""
        return await self._handle_request(
            'generic_data',
            self.api_client.get_generic_data
        )

    async def get_alerts(self) -> Any:
        """Get the alerts from the mower."""
        return await self._handle_request(
            'alerts',
            self.api_client.get_alerts
        )

    async def get_operating_data(self) -> Any:
        """Get the operating data from the mower."""
        return await self._handle_request(
            'operating_data',
            self.api_client.get_operating_data
        )

    async def get_next_mow(self) -> Any:
        """Get the next mow schedule."""
        return await self._handle_request(
            'next_mow',
            self.api_client.get_next_mow
        )

    async def get_last_completed_mow(self) -> Any:
        """Get the last completed mow."""
        return await self._handle_request(
            'last_completed_mow',
            self.api_client.get_last_completed_mow
        )

    async def get_predictive_calendar(self) -> Any:
        """Get the predictive calendar."""
        return await self._handle_request(
            'predictive_calendar',
            self.api_client.get_predictive_calendar
        )

    async def put_command(self, command: str) -> Any:
        """Send a command to the mower."""
        return await self._handle_request(
            f'command_{command}',
            self.api_client.put_command,
            command
        )

    async def put_mow_mode(self, command: Any) -> Any:
        """Set the mow mode."""
        return await self._handle_request(
            f'mow_mode_{command}',
            self.api_client.put_mow_mode,
            command
        )

    async def download_map(self, filename: str = None) -> bool:
        """Download the map from the mower."""
        try:
            return await self._handle_request(
                'download_map',
                self.api_client.download_map,
                filename
            )
        except Exception as exc:
            _LOGGER.error("Failed to download map: %s", exc)
            return False

    async def update_all(self) -> None:
        """Update all states from the API."""
        try:
            await self._handle_request(
                'update_all',
                self.api_client.update_all
            )
        except Exception as exc:
            _LOGGER.error("Failed to update all states: %s", exc)

    async def delete_alert(self, alert_index: int) -> bool:
        """Delete an alert."""
        try:
            return await self._handle_request(
                f'delete_alert_{alert_index}',
                self.api_client.delete_alert,
                alert_index
            )
        except Exception as exc:
            _LOGGER.error("Failed to delete alert: %s", exc)
            return False

    async def put_alert_read(self, alert_index: int) -> bool:
        """Mark an alert as read."""
        try:
            return await self._handle_request(
                f'put_alert_read_{alert_index}',
                self.api_client.put_alert_read,
                alert_index
            )
        except Exception as exc:
            _LOGGER.error("Failed to mark alert as read: %s", exc)
            return False

    async def delete_all_alerts(self) -> bool:
        """Delete all alerts."""
        try:
            return await self._handle_request(
                'delete_all_alerts',
                self.api_client.delete_all_alerts
            )
        except Exception as exc:
            _LOGGER.error("Failed to delete all alerts: %s", exc)
            return False
