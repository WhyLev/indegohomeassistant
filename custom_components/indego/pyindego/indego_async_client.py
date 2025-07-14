"""API for Bosch API server for Indego lawn mower."""
import asyncio
import logging
import json
import time
from socket import error as SocketError
from typing import Any, Optional, Callable, Awaitable

import aiohttp
from aiohttp import (
    ClientOSError,
    ClientResponseError,
    ServerTimeoutError,
    TooManyRedirects,
)
from aiohttp.web_exceptions import HTTPGatewayTimeout

from .const import (
    COMMANDS,
    CONTENT_TYPE_JSON,
    DEFAULT_CALENDAR,
    DEFAULT_URL,
    Methods,
)
from .indego_base_client import IndegoBaseClient
from .states import Calendar
from .helpers import random_request_id

_LOGGER = logging.getLogger(__name__)


class IndegoAsyncClient(IndegoBaseClient):
    """Class for Indego Async Client."""

    def __init__(
        self,
        token: str,
        token_refresh_method: Optional[Callable[[], Awaitable[str]]] = None,
        serial: str = None,
        map_filename: str = None,
        api_url: str = DEFAULT_URL,
        session: aiohttp.ClientSession = None,
        raise_request_exceptions: bool = False,
    ):
        """Initialize the Async Client."""
        super().__init__(token, token_refresh_method, serial, map_filename, api_url, raise_request_exceptions)
        if session:
            self._session = session
            self._should_close_session = False
        else:
            self._session = aiohttp.ClientSession(raise_for_status=False)
            self._should_close_session = True

    async def __aenter__(self):
        """Enter for async with."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit for async with."""
        await self.close()

    async def start(self):
        """Get the OAuth-token"""
        if self._token_refresh_method is not None:
            _LOGGER.debug("Refreshing token")
            self._token = await self._token_refresh_method()
        else:
            _LOGGER.debug("Token refresh is NOT available")

    async def close(self):
        """Close the aiohttp session."""
        if self._should_close_session:
            await self._session.close()

    async def get_mowers(self):
        """Get a list of the available mowers (serials) in the account."""
        result = await self.get("alms")
        if result is None:
            return []
        return [mower['alm_sn'] for mower in result]

    async def delete_alert(self, alert_index: int):
        """Delete the alert with the specified index."""
        if not self._alerts_loaded:
            raise ValueError("Alerts not loaded, please run update_alerts first.")
        alert_id = self._get_alert_by_index(alert_index)
        if alert_id:
            return await self._request(Methods.DELETE, f"alerts/{alert_id}/")

    async def delete_all_alerts(self):
        """Delete all alerts."""
        if not self._alerts_loaded:
            raise ValueError("Alerts not loaded, please run update_alerts first.")
        if self.alerts_count > 0:
            return await asyncio.gather(
                *[
                    self._request(Methods.DELETE, f"alerts/{alert.alert_id}")
                    for alert in self.alerts
                ]
            )
        _LOGGER.info("No alerts to delete")
        return None

    async def download_map(self, filename: str = None):
        """Download the map."""
        if not self.serial:
            return
        if filename:
            self.map_filename = filename
        if not self.map_filename:
            raise ValueError("No map filename defined.")
        lawn_map = await self.get(f"alms/{self.serial}/map")
        if lawn_map:
            with open(self.map_filename, "wb") as file:
                file.write(lawn_map)

    async def put_alert_read(self, alert_index: int):
        """Set the alert to read."""
        if not self._alerts_loaded:
            raise ValueError("Alerts not loaded, please run update_alerts first.")
        alert_id = self._get_alert_by_index(alert_index)
        if alert_id:
            return await self._request(
                Methods.PUT, f"alerts/{alert_id}", data={"read_status": "read"}
            )

    async def put_all_alerts_read(self):
        """Set all alerts as read."""
        if not self._alerts_loaded:
            raise ValueError("Alerts not loaded, please run update_alerts first.")
        if self.alerts_count > 0:
            return await asyncio.gather(
                *[
                    self._request(
                        Methods.PUT,
                        f"alerts/{alert.alert_id}",
                        data={"read_status": "read"},
                    )
                    for alert in self.alerts
                ]
            )
        _LOGGER.info("No alerts to set to read")
        return None

    async def put_command(self, command: str):
        """Send a command to the mower."""
        if command in COMMANDS:
            if not self.serial:
                return
            return await self.put(f"alms/{self.serial}/state", {"state": command})
        raise ValueError("Wrong Command, use one of 'mow', 'pause', 'returnToDock'")

    async def put_mow_mode(self, command: Any):
        """Set the mower to mode manual (false-ish) or predictive (true-ish)."""
        if command in ("true", "false", "True", "False") or isinstance(command, bool):
            if not self.serial:
                return
            if isinstance(command, str):
                smartmow = command.lower() == "true"
            else:
                smartmow = command
            return await self.put(
                f"alms/{self.serial}/predictive",
                {"enabled": smartmow}
            )
        raise ValueError("Wrong Command, only boolean-ish values allowed")

    async def put_predictive_cal(self, calendar: dict = DEFAULT_CALENDAR):
        """Set the predictive calendar."""
        if not self.serial:
            return
        _LOGGER.debug("calendar: %s", calendar)
        return await self.put(
            f"alms/{self.serial}/predictive/calendar",
            calendar
        )

    async def update_alerts(self):
        """Update alerts."""
        if not self.serial:
            return
        self._update_alerts(await self.get(f"alms/{self.serial}/alerts"))
        self._alerts_loaded = True

    async def get_alerts(self):
        """Update alerts and return them."""
        await self.update_alerts()
        return self.alerts

    async def update_all(self):
        """Update all states."""
        results = await asyncio.gather(
            self.update_alerts(),
            self.update_calendar(),
            self.update_config(),
            self.update_generic_data(),
            self.update_last_completed_mow(),
            self.update_location(),
            self.update_network(),
            self.update_next_mow(),
            self.update_operating_data(),
            self.update_predictive_calendar(),
            self.update_predictive_schedule(),
            self.update_security(),
            self.update_setup(),
            self.update_state(True),
            self.update_updates_available(),
            self.update_user(),
            return_exceptions=True,
        )
        _LOGGER.debug("Update all results: %s", results)

    async def update_calendar(self):
        """Update calendar."""
        if not self.serial:
            return
        self._update_calendar(await self.get(f"alms/{self.serial}/calendar"))

    async def get_calendar(self):
        """Update calendar and return it."""
        await self.update_calendar()
        return self.calendar

    async def update_config(self):
        """Update config."""
        if not self.serial:
            return
        self._update_config(await self.get(f"alms/{self.serial}/config"))

    async def get_config(self):
        """Update config and return it."""
        await self.update_config()
        return self.config

    async def update_generic_data(self):
        """Update generic data."""
        if not self.serial:
            return
        self._update_generic_data(await self.get(f"alms/{self.serial}"))

    async def get_generic_data(self):
        """Update generic_data and return it."""
        await self.update_generic_data()
        return self.generic_data

    async def update_last_completed_mow(self):
        """Update last completed mow."""
        if not self.serial:
            return
        self._update_last_completed_mow(
            await self.get(f"alms/{self.serial}/predictive/lastcutting")
        )

    async def get_last_completed_mow(self):
        """Update last_completed_mow and return it."""
        await self.update_last_completed_mow()
        return self.last_completed_mow

    async def update_location(self):
        """Update location."""
        if not self.serial:
            return
        self._update_location(await self.get(f"alms/{self.serial}/predictive/location"))

    async def get_location(self):
        """Update location and return it."""
        await self.update_location()
        return self.location

    async def update_network(self):
        """Update network."""
        if not self.serial:
            return
        self._update_network(await self.get(f"alms/{self.serial}/network"))

    async def get_network(self):
        """Update network and return it."""
        await self.update_network()
        return self.network

    async def update_next_mow(self):
        """Update next mow datetime."""
        if not self.serial:
            return
        self._update_next_mow(await self.get(f"alms/{self.serial}/predictive/nextcutting"))

    async def get_next_mow(self):
        """Update next_mow and return it."""
        await self.update_next_mow()
        return self.next_mow

    async def update_operating_data(self):
        """Update operating data."""
        if not self.serial:
            return
        self._update_operating_data(await self.get(f"alms/{self.serial}/operatingData"))

    async def get_operating_data(self):
        """Update operating_data and return it."""
        await self.update_operating_data()
        return self.operating_data

    async def update_predictive_calendar(self):
        """Update predictive_calendar."""
        if not self.serial:
            return
        self._update_predictive_calendar(
            await self.get(f"alms/{self.serial}/predictive/calendar")
        )

    async def get_predictive_calendar(self):
        """Update predictive_calendar and return it."""
        await self.update_predictive_calendar()
        return self.predictive_calendar

    async def update_predictive_schedule(self):
        """Update predictive schedule."""
        if not self.serial:
            return
        self._update_predictive_schedule(
            await self.get(f"alms/{self.serial}/predictive/schedule")
        )

    async def get_predictive_schedule(self):
        """Update predictive_schedule and return it."""
        await self.update_predictive_schedule()
        return self.predictive_schedule

    async def update_security(self):
        """Update security."""
        if not self.serial:
            return
        self._update_security(await self.get(f"alms/{self.serial}/security"))

    async def get_security(self):
        """Update security and return it."""
        await self.update_security()
        return self.security

    async def update_setup(self):
        """Update setup."""
        if not self.serial:
            return
        self._update_setup(await self.get(f"alms/{self.serial}/setup"))

    async def get_setup(self):
        """Update setup and return it."""
        await self.update_setup()
        return self.setup

    async def update_state(self, force=False, longpoll=False, longpoll_timeout=120):
        """Update state."""
        if not self.serial:
            return
        path = f"alms/{self.serial}/state"
        if longpoll:
            if force:
                path = path + "?longpoll=true&forceRefresh=true&timeout={timeout}".format(
                    timeout=longpoll_timeout
                )
            else:
                path = path + "?longpoll=true&timeout={timeout}".format(
                    timeout=longpoll_timeout
                )
        elif force:
            path = path + "?forceRefresh=true"

        self._update_state(await self.get(path, timeout=longpoll_timeout))

    async def get_state(self, force=False, longpoll=False, longpoll_timeout=120):
        """Update state and return it."""
        await self.update_state(force, longpoll, longpoll_timeout)
        return self.state

    async def update_updates_available(self):
        """Update updates available."""
        if not self.serial:
            return
        self._update_updates_available(await self.get(f"alms/{self.serial}/updates"))

    async def get_updates_available(self):
        """Update updates_available and return it."""
        await self.update_updates_available()
        return self.update_available

    async def update_user(self):
        """Update users."""
        self._update_user(await self.get(f"users/{self._userid}"))

    async def get_user(self):
        """Update network and return it."""
        await self.update_user()
        return self.user

    async def _request(
        self,
        method: Methods,
        path: str,
        data: dict = None,
        headers: dict = None,
        timeout: int = 30
    ):
        """Send a request."""
        url = self._api_url + path

        # Ensure we have headers we want.
        headers = self._headers if headers is None else {**self._headers, **headers}

        if self._token:
            headers["Authorization"] = "Bearer %s" % self._token

        request_id = random_request_id()
        request_start_time = None
        try:
            log_headers = headers.copy()
            if 'Authorization' in log_headers:
                log_headers['Authorization'] = '******'
            _LOGGER.debug(
                "[%s] %s call to API endpoint %s, headers: %s, data: %s",
                request_id,
                method.value,
                url,
                json.dumps(log_headers) if log_headers is not None else '',
                json.dumps(data) if data is not None else '',
            )

            request_start_time = time.time()
            async with self._session.request(
                method.value,
                url,
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if not response.ok:
                    response.raise_for_status()

                if response.status == 204:
                    # API call successful but no content
                    _LOGGER.debug(
                        "[%s] %s %s successful in %i seconds, no content",
                        request_id,
                        method.value,
                        path,
                        time.time() - request_start_time
                    )
                    return None

                # Get response as raw bytes
                response_content = await response.read()

                # Log the timing and response
                _LOGGER.debug(
                    "[%s] %s %s successful in %i seconds: %s",
                    request_id,
                    method.value,
                    path,
                    time.time() - request_start_time,
                    response_content.decode('utf-8') if response.content_type == CONTENT_TYPE_JSON else "[binary content]"
                )

                # Parse response
                if response.content_type == CONTENT_TYPE_JSON:
                    return json.loads(response_content)
                return response_content

        except asyncio.TimeoutError as exc:
            if self._raise_request_exceptions:
                raise
            _LOGGER.error(
                "[%s] %s %s request timed out after %i seconds: %s",
                request_id,
                method.value,
                path,
                time.time() - request_start_time,
                str(exc)
            )
            return None

        except (TooManyRedirects, ClientResponseError, SocketError) as exc:
            if self._raise_request_exceptions:
                raise
            _LOGGER.error(
                "[%s] %s %s failed after %i seconds: %s",
                request_id,
                method.value,
                path,
                time.time() - request_start_time,
                str(exc)
            )
            return None

        except asyncio.CancelledError:
            _LOGGER.debug("[%s] Task cancelled by task runner", request_id)
            return None

        except Exception as exc:
            if self._raise_request_exceptions:
                raise
            _LOGGER.error(
                "[%s] Request %s %s gave an unhandled error: %s",
                request_id,
                method.value,
                path,
                str(exc)
            )
            return None

    async def get(self, path: str, timeout: int = 30):
        """Send a GET request."""
        return await self._request(Methods.GET, path, timeout=timeout)

    async def put(self, path: str, data: dict, timeout: int = 30):
        """Send a PUT request."""
        return await self._request(Methods.PUT, path, data=data, timeout=timeout)
