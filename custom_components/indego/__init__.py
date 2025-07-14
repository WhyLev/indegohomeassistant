"""The Bosch Indego integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import IndegoApiClient
from .const import (
    DOMAIN,
    INDEGO_PLATFORMS,
    UPDATE_INTERVAL,
    CONF_MOWER_SERIAL,
    DEFAULT_NAME,
)
from .coordinator import IndegoDataUpdateCoordinator
from .models import State, Calendar, OperatingData

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Indego component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Indego from a config entry."""
    try:
        # Get OAuth session
        session = aiohttp_client.async_get_clientsession(hass)
        
        # Initialize API client
        api = IndegoApiClient(
            hass=hass,
            token=entry.data["token"]["access_token"],
            token_refresh_method=entry.data.get("token_refresh_method"),
            serial=entry.data[CONF_MOWER_SERIAL],
        )

        # Initialize coordinator
        coordinator = IndegoDataUpdateCoordinator(
            hass=hass,
            api=api,
            update_interval=UPDATE_INTERVAL,
        )

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, INDEGO_PLATFORMS)

        return True

    except Exception as err:
        _LOGGER.error("Error setting up Indego integration: %s", err)
        raise ConfigEntryAuthFailed from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, INDEGO_PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        api: IndegoApiClient = data["api"]
        await api.shutdown()

    return unload_ok


class IndegoEntity(CoordinatorEntity):
    """Base class for Indego entities."""

    def __init__(
        self,
        coordinator: IndegoDataUpdateCoordinator,
        device_info: dict,
    ) -> None:
        """Initialize Indego entity."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_has_entity_name = True

    @property
    def state(self) -> State:
        """Return coordinator state data."""
        return self.coordinator.state

    @property
    def calendar(self) -> Calendar:
        """Return coordinator calendar data."""
        return self.coordinator.calendar

    @property
    def operating_data(self) -> OperatingData:
        """Return coordinator operating data."""
        return self.coordinator.operating_data
