"""Data update coordinator for Bosch Indego integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import IndegoApiClient
from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    STATE_UPDATE_INTERVAL,
    CALENDAR_UPDATE_INTERVAL,
)
from .models import State, Calendar, OperatingData, Alert

_LOGGER = logging.getLogger(__name__)


class IndegoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Indego data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IndegoApiClient,
        update_interval: timedelta = UPDATE_INTERVAL,
    ) -> None:
        """Initialize global Indego data updater."""
        self.api = api
        self.state: Optional[State] = None
        self.calendar: Optional[Calendar] = None
        self.operating_data: Optional[OperatingData] = None
        self.alerts: list[Alert] = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Indego API."""
        try:
            # Get state with shorter interval
            state_data = await self.api.get_state(force_update=True)
            self.state = State.from_dict(state_data)

            tasks = []

            # Only update other data less frequently
            if not self.calendar or self.calendar_needs_update():
                tasks.append(self._update_calendar())
            if not self.operating_data or self.operating_data_needs_update():
                tasks.append(self._update_operating_data())
            if not self.alerts or self.alerts_need_update():
                tasks.append(self._update_alerts())

            if tasks:
                await asyncio.gather(*tasks)

            return {
                "state": self.state,
                "calendar": self.calendar,
                "operating_data": self.operating_data,
                "alerts": self.alerts,
            }

        except Exception as err:
            raise UpdateFailed(f"Error communicating with Indego API: {err}") from err

    async def _update_calendar(self) -> None:
        """Update calendar data."""
        try:
            calendar_data = await self.api.get_calendar()
            self.calendar = Calendar.from_dict(calendar_data)
        except Exception as err:
            _LOGGER.error("Error updating calendar: %s", err)

    async def _update_operating_data(self) -> None:
        """Update operating data."""
        try:
            operating_data = await self.api.get_generic_data()
            self.operating_data = OperatingData.from_dict(operating_data)
        except Exception as err:
            _LOGGER.error("Error updating operating data: %s", err)

    async def _update_alerts(self) -> None:
        """Update alerts."""
        try:
            alerts_data = await self.api.get_alerts()
            self.alerts = [Alert.from_dict(alert) for alert in alerts_data]
        except Exception as err:
            _LOGGER.error("Error updating alerts: %s", err)

    def calendar_needs_update(self) -> bool:
        """Check if calendar needs update."""
        return self._needs_update(CALENDAR_UPDATE_INTERVAL)

    def operating_data_needs_update(self) -> bool:
        """Check if operating data needs update."""
        return self._needs_update(UPDATE_INTERVAL)

    def alerts_need_update(self) -> bool:
        """Check if alerts need update."""
        return self._needs_update(UPDATE_INTERVAL)

    def _needs_update(self, interval: timedelta) -> bool:
        """Check if data needs update based on interval."""
        if not self.last_update_success:
            return True
        return self.last_update_success + interval < self.hass.loop.time()
