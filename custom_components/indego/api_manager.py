"""API Manager for Indego integration."""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp.client_exceptions import ClientResponseError

_LOGGER = logging.getLogger(__name__)

class IndegoApiManager:
    """Class to manage API calls with caching and rate limiting."""

    def __init__(self, hass: HomeAssistant, api_client: Any):
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

    def _clean_old_timestamps(self):
        """Remove timestamps older than 1 minute."""
        current_time = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if current_time - t <= 60]

    def can_make_request(self) -> bool:
        """Check if we can make a new request based on rate limits."""
        self._clean_old_timestamps()
        return len(self._request_timestamps) < self._rate_limit

    async def wait_for_rate_limit(self):
        """Wait until we can make another request."""
        while not self.can_make_request():
            await asyncio.sleep(0.1)
            self._clean_old_timestamps()
        self._request_timestamps.append(time.time())

    def is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_times:
            return False
        ttl = self._cache_ttl.get(cache_key, timedelta(minutes=5))
        return datetime.now() - self._cache_times[cache_key] < ttl

    async def _make_api_call(self, cache_key: str, api_method: str, *args, **kwargs):
        """Make an API call with caching and rate limiting."""
        async with self._lock:
            # Check cache first
            if self.is_cache_valid(cache_key):
                return self._cache[cache_key]

            # Wait for rate limiting
            await self.wait_for_rate_limit()

            try:
                # Make the API call
                method = getattr(self.api_client, api_method)
                result = await method(*args, **kwargs)

                # Update cache
                self._cache[cache_key] = result
                self._cache_times[cache_key] = datetime.now()

                # Reset error count on success
                self._error_count[cache_key] = 0

                return result

            except ClientResponseError as exc:
                if exc.status == 429:  # Too Many Requests
                    _LOGGER.warning("Rate limit hit, backing off for 60 seconds")
                    await asyncio.sleep(60)
                    return await self._make_api_call(cache_key, api_method, *args, **kwargs)
                
                self._handle_error(cache_key, exc)
                raise

            except Exception as exc:
                self._handle_error(cache_key, exc)
                raise

    def _handle_error(self, cache_key: str, exc: Exception):
        """Handle and track errors."""
        current_time = time.time()
        if cache_key not in self._error_count:
            self._error_count[cache_key] = 0

        # Only log if we haven't logged in the last minute
        if current_time - self._last_error_time.get(cache_key, 0) > 60:
            self._last_error_time[cache_key] = current_time
            self._error_count[cache_key] += 1
            _LOGGER.error(
                "Error making API call %s (attempt %d): %s",
                cache_key,
                self._error_count[cache_key],
                str(exc)
            )

    async def get_state(self, force: bool = False, longpoll: bool = False):
        """Get the mower state with caching."""
        if force:
            self._cache.pop('state', None)
            self._cache_times.pop('state', None)
        return await self._make_api_call('state', 'update_state', longpoll=longpoll)

    async def get_operating_data(self):
        """Get operating data with caching."""
        return await self._make_api_call('operating_data', 'update_operating_data')

    async def get_next_mow(self):
        """Get next mow time with caching."""
        return await self._make_api_call('next_mow', 'update_next_mow')

    async def get_last_completed_mow(self):
        """Get last completed mow with caching."""
        return await self._make_api_call('last_completed_mow', 'update_last_completed_mow')

    async def get_alerts(self):
        """Get alerts with caching."""
        return await self._make_api_call('alerts', 'update_alerts')

    async def get_generic_data(self):
        """Get generic data with caching."""
        return await self._make_api_call('generic_data', 'update_generic_data')

    async def get_predictive_calendar(self):
        """Get predictive calendar with caching."""
        return await self._make_api_call('predictive_calendar', 'update_predictive_calendar')

    def invalidate_cache(self, cache_key: Optional[str] = None):
        """Invalidate specific or all cache entries."""
        if cache_key is None:
            self._cache.clear()
            self._cache_times.clear()
        elif cache_key in self._cache:
            del self._cache[cache_key]
            del self._cache_times[cache_key]

    async def download_map(self, max_retries: int = 3, retry_delay: int = 5) -> Optional[bytes]:
        """Download the map from the API with retries and validation.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Delay in seconds between retries
            
        Returns:
            Optional[bytes]: The map data if successful, None if failed
        """
        async with self._lock:  # Ensure only one map download at a time
            attempt = 0
            last_error = None
            
            while attempt < max_retries:
                try:
                    # Check rate limiting
                    await self.wait_for_rate_limit()
                    
                    # Try to get state first to ensure mower is responsive
                    await self.get_state(force=True)
                    if not self.api_client.state:
                        _LOGGER.warning("Cannot download map: mower state unavailable")
                        return None
                    
                    # Download the map
                    _LOGGER.debug("Downloading map (attempt %d/%d)", attempt + 1, max_retries)
                    map_data = await self.api_client.download_map()
                    
                    # Validate map data
                    if not map_data:
                        raise ValueError("Received empty map data")
                        
                    if not map_data.startswith(b'<?xml') and not map_data.startswith(b'<svg'):
                        raise ValueError("Invalid map data format")
                        
                    # Add timestamp to rate limiting
                    self._request_timestamps.append(time.time())
                    
                    _LOGGER.debug("Map downloaded successfully (%d bytes)", len(map_data))
                    return map_data
                    
                except (ClientResponseError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    if isinstance(exc, ClientResponseError):
                        if exc.status == 404:
                            _LOGGER.warning("Map not found on server")
                            return None
                        if exc.status == 429:  # Rate limited
                            retry_delay = int(exc.headers.get('Retry-After', retry_delay))
                            
                    _LOGGER.warning(
                        "Map download failed (attempt %d/%d): %s. Retrying in %d seconds...",
                        attempt + 1,
                        max_retries,
                        str(exc),
                        retry_delay
                    )
                    
                except Exception as exc:
                    last_error = exc
                    _LOGGER.warning(
                        "Unexpected error downloading map (attempt %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        str(exc)
                    )
                
                # Wait before retrying
                await asyncio.sleep(retry_delay)
                attempt += 1
                # Increase delay for next attempt
                retry_delay = min(retry_delay * 2, 60)  # Cap at 60 seconds
            
            if last_error:
                _LOGGER.error(
                    "Failed to download map after %d attempts. Last error: %s",
                    max_retries,
                    str(last_error)
                )
            return None
