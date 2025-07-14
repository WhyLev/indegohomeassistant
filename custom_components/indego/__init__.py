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
        name: str,
        oauth_session: IndegoOAuth2Session,
        serial: str,
        options: dict,
        hass: HomeAssistant,
        user_agent: str = None,
        position_update_interval: int = DEFAULT_POSITION_UPDATE_INTERVAL,
        adaptive_position_updates: bool = DEFAULT_ADAPTIVE_POSITION_UPDATES,
        progress_line_width: int = MAP_PROGRESS_LINE_WIDTH,
        progress_line_color: str = MAP_PROGRESS_LINE_COLOR,
        state_update_timeout: int = DEFAULT_STATE_UPDATE_TIMEOUT,
        longpoll_timeout: int = DEFAULT_LONGPOLL_TIMEOUT,
    ):
        """Initialize the IndegoHub with updated API manager."""
        self.hass = hass
        self.name = name
        self.options = options
        self.serial = serial
        self.last_position_update = None
        self._shutdown = False
        self._oauth_session = oauth_session
        self._first_update = True
        self._position_update_interval = position_update_interval
        self._adaptive_position_updates = adaptive_position_updates
        self._progress_line_width = progress_line_width
        self._progress_line_color = progress_line_color
        self._state_update_timeout = state_update_timeout
        self._longpoll_timeout = longpoll_timeout
        self._position_update_timer = None

        # Initialize the async client
        self._async_client = IndegoAsyncClient(
            token=oauth_session.token["access_token"],
            token_refresh_method=self._oauth_session.async_ensure_token_valid,
            serial=serial,
            api_url="https://api.indego.iot.bosch-si.com/api/v1/",
            session=async_get_clientsession(self.hass),
        )

        # Initialize the API manager with the async client
        self.api = IndegoApiManager(self.hass, self._async_client)

        # Initialize state holders
        self.states = {}
        self.sensors = {}
        self.binary_sensors = {}
        self.vacuum = None
        self.lawn_mower = None
        self.generic_data_loaded = False
        self.alerts = {}
        self.alerts_count = 0
        self.map_image = None
        self.map_update_timestamp = None
        self.map_filename = None
        self.device_info = None
        self._battery_percent = None
        self._battery_percent_adjusted = None
        self._mower_state = None
        self._mower_state_detail = None
        self._mower_state_description = None
        self._lawn_mowed = None
        self._runtime = None
        self._last_completed = None
        self._next_mow = None
        self._last_update = None

    async def _async_update_state(self, force_update: bool = False):
        """Update state using the API manager."""
        try:
            state = await self.api.get_state(force=force_update, longpoll=True)
            if state:
                self._mower_state = state.state
                self._mower_state_description = state.state_description
                self._mower_state_detail = state.state_description_detail
                self._last_update = last_updated_now()
                return True
        except Exception as exc:
            _LOGGER.error("Error updating state: %s", exc)
        return False

    async def _async_update_generic_data(self):
        """Update generic data using the API manager."""
        try:
            data = await self.api.get_generic_data()
            if data:
                self._battery_percent = data.battery.percent
                self._battery_percent_adjusted = data.battery.percent_adjusted
                self._runtime = data.runtime
                # Update device info if needed
                if not self.device_info:
                    self.device_info = DeviceInfo(
                        identifiers={(DOMAIN, self.serial)},
                        manufacturer="Bosch",
                        model=data.model,
                        name=self.name,
                        sw_version=data.firmware,
                    )
                return True
        except Exception as exc:
            _LOGGER.error("Error updating generic data: %s", exc)
        return False

    async def update_alerts(self):
        """Update alerts using the API manager."""
        try:
            alerts = await self.api.get_alerts()
            if alerts:
                self.alerts = alerts
                self.alerts_count = len(alerts)
                return True
        except Exception as exc:
            _LOGGER.error("Error updating alerts: %s", exc)
        return False

    async def update_operating_data(self):
        """Update operating data using the API manager."""
        try:
            data = await self.api.get_operating_data()
            if data:
                return True
        except Exception as exc:
            _LOGGER.error("Error updating operating data: %s", exc)
        return False

    async def update_next_mow(self):
        """Update next mow using the API manager."""
        try:
            self._next_mow = await self.api.get_next_mow()
            return True
        except Exception as exc:
            _LOGGER.error("Error updating next mow: %s", exc)
        return False

    async def update_last_completed_mow(self):
        """Update last completed mow using the API manager."""
        try:
            self._last_completed = await self.api.get_last_completed_mow()
            return True
        except Exception as exc:
            _LOGGER.error("Error updating last completed mow: %s", exc)
        return False

    async def update_all(self):
        """Update all states using the API manager."""
        try:
            await self.api.update_all()
            return True
        except Exception as exc:
            _LOGGER.error("Error updating all states: %s", exc)
        return False

    async def start_periodic_position_update(self):
        """Start periodic position update."""
        # Only start if we want position updates
        if self._position_update_interval > 0:
            if self._adaptive_position_updates:
                await self._adaptive_position_update()
            else:
                await self._fixed_position_update()

    async def _fixed_position_update(self):
        """Update position on fixed interval."""
        if not self._shutdown:
            await self._async_update_state(True)
            self._position_update_timer = async_track_point_in_time(
                self.hass,
                self._fixed_position_update,
                utcnow() + timedelta(minutes=self._position_update_interval)
            )

    async def _adaptive_position_update(self):
        """Update position adaptively based on state."""
        if not self._shutdown:
            is_mowing = self._mower_state in [1, 2, 3]
            interval = 1 if is_mowing else self._position_update_interval
            
            await self._async_update_state(True)
            self._position_update_timer = async_track_point_in_time(
                self.hass,
                self._adaptive_position_update,
                utcnow() + timedelta(minutes=interval)
            )

    async def async_shutdown(self):
        """Shut down the hub."""
        self._shutdown = True
        if self._position_update_timer:
            self._position_update_timer()
        await self._async_client.close()

    async def update_generic_data_and_load_platforms(self, load_platforms: Callable):
        """Update generic data and load platforms."""
        await self._async_update_generic_data()
        await load_platforms()
        self.generic_data_loaded = True

    async def handle_command(call):
        """Handle commands sent to the mower."""
        serial = call.data.get(CONF_MOWER_SERIAL)
        command = call.data.get(CONF_SEND_COMMAND)

        if serial is None:
            _LOGGER.debug("No serial defined, getting all indego hubs")
            targets = hass.data[DOMAIN].values()
        else:
            _LOGGER.debug("Serial defined, getting single hub")
            targets = [
                hub
                for hub in hass.data[DOMAIN].values()
                if hub.serial == serial
            ]

        if not targets:
            _LOGGER.warning("No hubs found for command")
            return

        for target in targets:
            _LOGGER.debug("Sending command to %s", target.serial)
            try:
                await target.api.put_command(command)
            except Exception as exc:
                _LOGGER.error(
                    "Command '%s' failed on %s: %s",
                    command,
                    target.serial,
                    str(exc)
                )

    async def handle_smartmow(call):
        """Handle smart mow commands."""
        serial = call.data.get(CONF_MOWER_SERIAL)
        enable = call.data.get(CONF_SMARTMOWING)

        if serial is None:
            targets = hass.data[DOMAIN].values()
        else:
            targets = [
                hub
                for hub in hass.data[DOMAIN].values()
                if hub.serial == serial
            ]

        if not targets:
            _LOGGER.warning("No hubs found for smartmow command")
            return

        for target in targets:
            try:
                await target.api.put_mow_mode({"enabled": enable == "on"})
            except Exception as exc:
                _LOGGER.error(
                    "Smartmow command failed on %s: %s",
                    target.serial,
                    str(exc)
                )

    async def handle_delete_alert(call):
        """Handle delete alert commands."""
        serial = call.data.get(CONF_MOWER_SERIAL)
        alert_index = call.data.get(SERVER_DATA_ALERT_INDEX)

        if serial is None:
            targets = hass.data[DOMAIN].values()
        else:
            targets = [
                hub
                for hub in hass.data[DOMAIN].values()
                if hub.serial == serial
            ]

        if not targets:
            _LOGGER.warning("No hubs found for delete alert command")
            return

        for target in targets:
            try:
                await target.api.delete_alert(alert_index)
            except Exception as exc:
                _LOGGER.error(
                    "Delete alert failed on %s: %s",
                    target.serial,
                    str(exc)
                )

    async def handle_delete_alert_all(call):
        """Handle delete all alerts command."""
        serial = call.data.get(CONF_MOWER_SERIAL)

        if serial is None:
            targets = hass.data[DOMAIN].values()
        else:
            targets = [
                hub
                for hub in hass.data[DOMAIN].values()
                if hub.serial == serial
            ]

        if not targets:
            _LOGGER.warning("No hubs found for delete all alerts command")
            return

        for target in targets:
            try:
                await target.api.delete_all_alerts()
            except Exception as exc:
                _LOGGER.error(
                    "Delete all alerts failed on %s: %s",
                    target.serial,
                    str(exc)
                )

    async def handle_read_alert(call):
        """Handle read alert command."""
        serial = call.data.get(CONF_MOWER_SERIAL)
        alert_index = call.data.get(SERVER_DATA_ALERT_INDEX)

        if serial is None:
            targets = hass.data[DOMAIN].values()
        else:
            targets = [
                hub
                for hub in hass.data[DOMAIN].values()
                if hub.serial == serial
            ]

        if not targets:
            _LOGGER.warning("No hubs found for read alert command")
            return

        for target in targets:
            try:
                await target.api.put_alert_read(alert_index)
            except Exception as exc:
                _LOGGER.error(
                    "Read alert failed on %s: %s",
                    target.serial,
                    str(exc)
                )

    async def handle_download_map(call):
        """Handle map download."""
        serial = call.data.get(CONF_MOWER_SERIAL)

        if serial is None:
            _LOGGER.error("Serial number required for map download")
            return

        targets = [
            hub
            for hub in hass.data[DOMAIN].values()
            if hub.serial == serial
        ]

        if not targets:
            _LOGGER.warning("No hub found for map download")
            return

        target = targets[0]
        try:
            await target.download_and_save_map()
        except Exception as exc:
            _LOGGER.error(
                "Map download failed for %s: %s",
                target.serial,
                str(exc)
            )

    # Register all service handlers
    hass.services.async_register(
        DOMAIN, SERVICE_NAME_COMMAND, handle_command, schema=SERVICE_SCHEMA_COMMAND
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NAME_SMARTMOW,
        handle_smartmow,
        schema=SERVICE_SCHEMA_SMARTMOWING,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NAME_DELETE_ALERT,
        handle_delete_alert,
        schema=SERVICE_SCHEMA_DELETE_ALERT,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NAME_DELETE_ALERT_ALL,
        handle_delete_alert_all,
        schema=SERVICE_SCHEMA_DELETE_ALERT_ALL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NAME_READ_ALERT,
        handle_read_alert,
        schema=SERVICE_SCHEMA_READ_ALERT,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NAME_DOWNLOAD_MAP,
        handle_download_map,
        schema=SERVICE_SCHEMA_DOWNLOAD_MAP,
    )

    async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Unload config entry."""
        unload_ok = await hass.config_entries.async_unload_platforms(entry, INDEGO_PLATFORMS)
        if unload_ok:
            indego_hub = hass.data[DOMAIN][entry.entry_id]
            await indego_hub.async_shutdown()
            hass.data[DOMAIN].pop(entry.entry_id)

            # Unregister services if this was the last entry
            if not hass.data[DOMAIN]:
                for service in [
                    SERVICE_NAME_COMMAND,
                    SERVICE_NAME_SMARTMOW,
                    SERVICE_NAME_DELETE_ALERT,
                    SERVICE_NAME_DELETE_ALERT_ALL,
                    SERVICE_NAME_READ_ALERT,
                ]:
                    hass.services.async_remove(DOMAIN, service)

        return unload_ok

    async def download_and_save_map(self, filename: str = None) -> bool:
        """Download the map from the mower and save it."""
        try:
            if filename is None:
                filename = f"map_{self.serial}_{int(time.time())}.svg"
                
            # Use the API manager to download the map
            success = await self.api.download_map(filename)
            
            if success:
                self.map_filename = filename
                self.map_update_timestamp = utcnow()
                try:
                    # Read and parse the SVG
                    async with aiofiles.open(filename, mode='r') as f:
                        content = await f.read()
                        svg = fromstring(content)
                        self.map_image = svg
                        return True
                except Exception as exc:
                    _LOGGER.error("Failed to parse downloaded map: %s", exc)
                    return False
            else:
                _LOGGER.error("Failed to download map")
                return False

        except Exception as exc:
            _LOGGER.error("Error downloading map: %s", exc)
            return False
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
