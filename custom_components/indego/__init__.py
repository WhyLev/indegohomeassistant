"""Bosch Indego Mower integration."""
from typing import Optional
import asyncio
import logging
import time
import aiofiles
import os
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from aiohttp.client_exceptions import ClientResponseError

import homeassistant.util.dt
import voluptuous as vol
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_TYPE,
    CONF_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    STATE_ON,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later
from homeassistant.util.dt import utcnow
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import async_get_config_entry_implementation
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.event import async_track_time_interval
from pyIndego import IndegoAsyncClient
from svgutils.transform import fromstring

from .api import IndegoOAuth2Session
from .binary_sensor import IndegoBinarySensor
from .vacuum import IndegoVacuum
from .lawn_mower import IndegoLawnMower
from .const import *
from .sensor import IndegoSensor
from .camera import IndegoCamera, IndegoMapCamera

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA_COMMAND = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string,
    vol.Required(CONF_SEND_COMMAND): cv.string
})

SERVICE_SCHEMA_SMARTMOWING = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string,
    vol.Required(CONF_SMARTMOWING): cv.string
})

SERVICE_SCHEMA_DELETE_ALERT = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string,
    vol.Required(SERVER_DATA_ALERT_INDEX): cv.positive_int
})

SERVICE_SCHEMA_DELETE_ALERT_ALL = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string
})

SERVICE_SCHEMA_READ_ALERT = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string,
    vol.Required(SERVER_DATA_ALERT_INDEX): cv.positive_int
})

SERVICE_SCHEMA_READ_ALERT_ALL = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string
})

SERVICE_SCHEMA_DOWNLOAD_MAP = vol.Schema({
    vol.Required(CONF_MOWER_SERIAL): cv.string
})

SERVICE_SCHEMA_REFRESH = vol.Schema({
    vol.Optional(CONF_MOWER_SERIAL): cv.string
})


def FUNC_ICON_MOWER_ALERT(state):
    if state:
        if int(state) > 0 or state == STATE_ON:
            return "mdi:alert-outline"
    return "mdi:check-circle-outline"


ENTITY_DEFINITIONS = {
    ENTITY_ONLINE: {
        CONF_TYPE: BINARY_SENSOR_TYPE,
        CONF_NAME: "online",
        CONF_ICON: "mdi:cloud-check",
        CONF_DEVICE_CLASS: BinarySensorDeviceClass.CONNECTIVITY,
        CONF_ATTR: [],
    },
    ENTITY_UPDATE_AVAILABLE: {
        CONF_TYPE: BINARY_SENSOR_TYPE,
        CONF_NAME: "update available",
        CONF_ICON: "mdi:download-outline",
        CONF_DEVICE_CLASS: BinarySensorDeviceClass.UPDATE,
        CONF_ATTR: [],
    },
    ENTITY_ALERT: {
        CONF_TYPE: BINARY_SENSOR_TYPE,
        CONF_NAME: "alert",
        CONF_ICON: FUNC_ICON_MOWER_ALERT,
        CONF_DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        CONF_ATTR: ["alerts_count"],
        CONF_TRANSLATION_KEY: "indego_alert",
    },
    ENTITY_MOWER_STATE: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "mower state",
        CONF_ICON: "mdi:robot-mower-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: ["last_updated"],
        CONF_TRANSLATION_KEY: "mower_state",
    },
    ENTITY_MOWER_STATE_DETAIL: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "mower state detail",
        CONF_ICON: "mdi:robot-mower-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [
            "last_updated",
            "state_number",
            "state_description",
        ],
        CONF_TRANSLATION_KEY: "mower_state_detail",
    },
    ENTITY_BATTERY: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "battery %",
        CONF_ICON: "battery",
        CONF_DEVICE_CLASS: SensorDeviceClass.BATTERY,
        CONF_UNIT_OF_MEASUREMENT: "%",
        CONF_ATTR: [
            "last_updated",
            "voltage_V",
            "discharge_Ah",
            "cycles",
            f"battery_temp_{UnitOfTemperature.CELSIUS}",
            f"ambient_temp_{UnitOfTemperature.CELSIUS}",
        ],
    },
    ENTITY_AMBIENT_TEMP: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "ambient temperature",
        CONF_ICON: "mdi:thermometer",
        CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        CONF_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS,
        CONF_ATTR: [],
    },
    ENTITY_BATTERY_TEMP: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "battery temperature",
        CONF_ICON: "mdi:thermometer",
        CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        CONF_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS,
        CONF_ATTR: [],
    },
    ENTITY_LAWN_MOWED: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "lawn mowed",
        CONF_ICON: "mdi:grass",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "%",
        CONF_ATTR: [
            "last_updated",
            "last_completed_mow",
            "next_mow",
            "last_session_operation_min",
            "last_session_cut_min",
            "last_session_charge_min",
        ],
    },
    ENTITY_LAST_COMPLETED: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "last completed",
        CONF_ICON: "mdi:calendar-check",
        CONF_DEVICE_CLASS: SensorDeviceClass.TIMESTAMP,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_NEXT_MOW: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "next mow",
        CONF_ICON: "mdi:calendar-clock",
        CONF_DEVICE_CLASS: SensorDeviceClass.TIMESTAMP,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_FORECAST: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "forecast",
        CONF_ICON: "mdi:weather-partly-cloudy",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: ["rain_probability", "recommended_next_mow"],
    },
    ENTITY_BATTERY_CYCLES: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "battery cycles",
        CONF_ICON: "mdi:counter",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_AVERAGE_MOW_TIME: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "average mow time",
        CONF_ICON: "mdi:timer-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "min",
        CONF_ATTR: [],
    },
    ENTITY_WEEKLY_AREA: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "weekly mowed area",
        CONF_ICON: "mdi:chart-areaspline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "m²",
        CONF_ATTR: [],
    },
    ENTITY_API_ERRORS: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "api errors",
        CONF_ICON: "mdi:alert-circle-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_MOWING_MODE: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "mowing mode",
        CONF_ICON: "mdi:alpha-m-circle-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_RUNTIME: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "mowtime total",
        CONF_ICON: "mdi:information-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "h",
        CONF_ATTR: [
            "total_mowing_time_h",
            "total_charging_time_h",
            "total_operation_time_h",
        ],
    },
    ENTITY_TOTAL_MOWING_TIME: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "total mowing time",
        CONF_ICON: "mdi:clock-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "h",
        CONF_ATTR: [],
    },
    ENTITY_TOTAL_CHARGING_TIME: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "total charging time",
        CONF_ICON: "mdi:clock-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "h",
        CONF_ATTR: [],
    },
    ENTITY_TOTAL_OPERATION_TIME: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "total operation time",
        CONF_ICON: "mdi:clock-outline",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "h",
        CONF_ATTR: [],
    },
    ENTITY_VACUUM: {
        CONF_TYPE: VACUUM_TYPE,
    },
    ENTITY_LAWN_MOWER: {
        CONF_TYPE: LAWN_MOWER_TYPE,
    },
    ENTITY_GARDEN_SIZE: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "garden size",
        CONF_ICON: "mdi:ruler-square",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: "m²",
        CONF_ATTR: [],
    },
    ENTITY_FIRMWARE: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "firmware version",
        CONF_ICON: "mdi:chip",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_SERIAL_NUMBER: {
        CONF_TYPE: SENSOR_TYPE,
        CONF_NAME: "serial number",
        CONF_ICON: "mdi:identifier",
        CONF_DEVICE_CLASS: None,
        CONF_UNIT_OF_MEASUREMENT: None,
        CONF_ATTR: [],
    },
    ENTITY_CAMERA: {
        CONF_TYPE: CAMERA_TYPE,
    },
    ENTITY_CAMERA_PROGRESS: {
        CONF_TYPE: CAMERA_TYPE,
    },
}


def format_indego_date(date: datetime) -> str:
    return date.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def last_updated_now() -> str:
    return homeassistant.util.dt.as_local(utcnow()).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    hass.data.setdefault(DOMAIN, {})

    entry_implementation = await async_get_config_entry_implementation(hass, entry)
    oauth_session = IndegoOAuth2Session(hass, entry, entry_implementation)
    indego_hub = hass.data[DOMAIN][entry.entry_id] = IndegoHub(
        entry.data[CONF_MOWER_NAME],
        oauth_session,
        entry.data[CONF_MOWER_SERIAL],
        {
            CONF_EXPOSE_INDEGO_AS_MOWER: entry.options.get(CONF_EXPOSE_INDEGO_AS_MOWER, False),
            CONF_EXPOSE_INDEGO_AS_VACUUM: entry.options.get(CONF_EXPOSE_INDEGO_AS_VACUUM, False),
            CONF_SHOW_ALL_ALERTS: entry.options.get(CONF_SHOW_ALL_ALERTS, False),
        },
        hass,
        entry.options.get(CONF_USER_AGENT),
        entry.options.get(CONF_POSITION_UPDATE_INTERVAL, DEFAULT_POSITION_UPDATE_INTERVAL),
        entry.options.get(CONF_ADAPTIVE_POSITION_UPDATES, DEFAULT_ADAPTIVE_POSITION_UPDATES),
        entry.options.get(CONF_PROGRESS_LINE_WIDTH, MAP_PROGRESS_LINE_WIDTH),
        entry.options.get(CONF_PROGRESS_LINE_COLOR, MAP_PROGRESS_LINE_COLOR),
        entry.options.get(CONF_STATE_UPDATE_TIMEOUT, DEFAULT_STATE_UPDATE_TIMEOUT),
        entry.options.get(CONF_LONGPOLL_TIMEOUT, DEFAULT_LONGPOLL_TIMEOUT)
    )

    await indego_hub.start_periodic_position_update()

    async def load_platforms():
        _LOGGER.debug("Loading platforms")
        await hass.config_entries.async_forward_entry_setups(entry, INDEGO_PLATFORMS)

    try:
        await indego_hub.update_generic_data_and_load_platforms(load_platforms)

    except ClientResponseError as exc:
        if 400 <= exc.status < 500:
            _LOGGER.debug("Received 401, triggering ConfigEntryAuthFailed in HA...")
            raise ConfigEntryAuthFailed from exc

        _LOGGER.warning("Login unsuccessful: %s", str(exc))
        return False

    except AttributeError as exc:
        _LOGGER.warning("Login unsuccessful: %s", str(exc))
        return False

    def find_instance_for_mower_service_call(call):
        mower_serial = call.data.get(CONF_MOWER_SERIAL, None)
        if mower_serial is None:
            # Return the first instance when params is missing for backwards compatibility.
            return hass.data[DOMAIN][hass.data[DOMAIN][CONF_SERVICES_REGISTERED]]

        for config_entry_id in hass.data[DOMAIN]:
            if config_entry_id == CONF_SERVICES_REGISTERED:
                continue

            instance = hass.data[DOMAIN][config_entry_id]
            if instance.serial == mower_serial:
                return instance

        raise HomeAssistantError("No mower instance found for serial '%s'" % mower_serial)

    async def async_send_command(call):
        """Handle the mower command service call."""
        instance = find_instance_for_mower_service_call(call)
        command = call.data.get(CONF_SEND_COMMAND, DEFAULT_NAME_COMMANDS)
        _LOGGER.debug("Indego.send_command service called, with command: %s", command)

        await instance.async_send_command_to_client(command)

    async def async_send_smartmowing(call):
        """Handle the smartmowing service call."""
        instance = find_instance_for_mower_service_call(call)
        enable = call.data.get(CONF_SMARTMOWING, DEFAULT_NAME_COMMANDS)
        _LOGGER.debug("Indego.send_smartmowing service called, enable: %s", enable)

        await instance._indego_client.put_mow_mode(enable)
        await instance._update_generic_data()

    async def async_delete_alert(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        index = call.data.get(SERVER_DATA_ALERT_INDEX, DEFAULT_NAME_COMMANDS)
        _LOGGER.debug("Indego.delete_alert service called with alert index: %s", index)

        await instance._update_alerts()
        await instance._indego_client.delete_alert(index)
        await instance._update_alerts()     

    async def async_delete_alert_all(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        _LOGGER.debug("Indego.delete_alert_all service called")

        await instance._update_alerts()
        await instance._indego_client.delete_all_alerts()
        await instance._update_alerts()   

    async def async_read_alert(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        index = call.data.get(SERVER_DATA_ALERT_INDEX, DEFAULT_NAME_COMMANDS)
        _LOGGER.debug("Indego.read_alert service called with alert index: %s", index)

        await instance._update_alerts()
        await instance._indego_client.put_alert_read(index)
        await instance._update_alerts()

    async def async_read_alert_all(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        _LOGGER.debug("Indego.read_alert_all service called")

        await instance._update_alerts()
        await instance._indego_client.put_all_alerts_read()
        await instance._update_alerts()

    async def async_download_map(call):
        """Handle the download_map service call."""
        instance = find_instance_for_mower_service_call(call)
        _LOGGER.debug("Indego.download_map service called for serial: %s", instance.serial)
        await instance.download_and_store_map()

    async def async_refresh(call):
        """Handle the refresh service call."""
        instance = find_instance_for_mower_service_call(call)
        if instance._unsub_refresh_state is not None:
            _LOGGER.debug("Refresh skipped due to cooldown for serial: %s", instance.serial)
            return
        _LOGGER.debug("Indego.refresh service called for serial: %s", instance.serial)
        await asyncio.gather(
            instance.refresh_state(),
            instance.refresh_10m(),
            instance.refresh_24h(),
        )

    # In HASS we can have multiple Indego component instances as long as the mower serial is unique.
    # So the mower services should only need to be registered for the first instance.
    if CONF_SERVICES_REGISTERED not in hass.data[DOMAIN]:
        _LOGGER.debug("Initializing mower service for config entry '%s'", entry.entry_id)

        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME_COMMAND,
            async_send_command,
            schema=SERVICE_SCHEMA_COMMAND
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME_SMARTMOW,
            async_send_smartmowing,
            schema=SERVICE_SCHEMA_SMARTMOWING,
        )
        hass.services.async_register(
            DOMAIN, 
            SERVICE_NAME_DELETE_ALERT, 
            async_delete_alert, 
            schema=SERVICE_SCHEMA_DELETE_ALERT
        )
        hass.services.async_register(
            DOMAIN, 
            SERVICE_NAME_READ_ALERT, 
            async_read_alert, 
            schema=SERVICE_SCHEMA_READ_ALERT
        )
        hass.services.async_register(
            DOMAIN, 
            SERVICE_NAME_DELETE_ALERT_ALL, 
            async_delete_alert_all, 
            schema=SERVICE_SCHEMA_DELETE_ALERT_ALL
        )
        hass.services.async_register(
            DOMAIN, 
            SERVICE_NAME_READ_ALERT_ALL, 
            async_read_alert_all, 
            schema=SERVICE_SCHEMA_READ_ALERT_ALL
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME_DOWNLOAD_MAP,
            async_download_map,
            schema=SERVICE_SCHEMA_DOWNLOAD_MAP
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME_REFRESH,
            async_refresh,
            schema=SERVICE_SCHEMA_REFRESH,
        )

        hass.data[DOMAIN][CONF_SERVICES_REGISTERED] = entry.entry_id

    else:
        _LOGGER.debug("Indego mower services already registered. Skipping for config entry '%s'", entry.entry_id)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, INDEGO_PLATFORMS)
    if not unload_ok:
        return False

    if CONF_SERVICES_REGISTERED in hass.data[DOMAIN] and hass.data[DOMAIN][CONF_SERVICES_REGISTERED] == entry.entry_id:
        del hass.data[DOMAIN][CONF_SERVICES_REGISTERED]

    await hass.data[DOMAIN][entry.entry_id].async_shutdown()
    del hass.data[DOMAIN][entry.entry_id]

    return True


class IndegoHub:
    """Class for the IndegoHub, which controls the sensors and binary sensors."""

    def __init__(
        self,
        name: str,
        session: IndegoOAuth2Session,
        serial: str,
        features: dict,
        hass: HomeAssistant,
        user_agent: Optional[str] = None,
        position_interval: int = DEFAULT_POSITION_UPDATE_INTERVAL,
        adaptive_updates: bool = DEFAULT_ADAPTIVE_POSITION_UPDATES,
        progress_line_width: int = MAP_PROGRESS_LINE_WIDTH,
        progress_line_color: str = MAP_PROGRESS_LINE_COLOR,
        state_update_timeout: int = DEFAULT_STATE_UPDATE_TIMEOUT,
        longpoll_timeout: int = DEFAULT_LONGPOLL_TIMEOUT,
    ):
        """Initialize the IndegoHub.

        Args:
            name (str): the name of the mower for entities
            session (IndegoOAuth2Session): the Bosch SingleKey ID OAuth session
            serial (str): serial of the mower, is used for uniqueness
            hass (HomeAssistant): HomeAssistant instance

        """
        self._mower_name = name
        self._serial = serial
        self._features = features
        self._hass = hass
        self._unsub_refresh_state = None
        self._refresh_state_task = None
        self._refresh_10m_remover = None
        self._refresh_24h_remover = None
        self._shutdown = False
        self._latest_alert = None
        self.entities = {}
        self._update_fail_count = None
        self._lawn_map = None
        self._unsub_map_timer = None
        self._last_position = (None, None)
        self._last_state = None
        self._position_interval = position_interval
        self._current_position_interval = position_interval
        self._adaptive_updates = adaptive_updates
        self._progress_line_width = progress_line_width
        self._progress_line_color = progress_line_color
        self._state_update_timeout = state_update_timeout
        self._longpoll_timeout = longpoll_timeout
        self._weekly_area_entries = []
        self._last_completed_ts = None
        self._last_state_ts = None
        self._last_error = {}
        self._error_log = {}
        self._api_error_stats = {}
        self._next_request_ts = 0
        self._online = False
        self._offline_since = None
        self._offline_failures = 0
        self._pending_mower_state = None
        self._pending_mower_detail = None
        self._debounce_remover = None

        async def async_token_refresh() -> str:
            await session.async_ensure_token_valid()
            return session.token["access_token"]

        self._indego_client = IndegoAsyncClient(
            token=session.token["access_token"],
            token_refresh_method=async_token_refresh,
            serial=self._serial,
            session=async_get_clientsession(hass),
            raise_request_exceptions=True
        )
        self._indego_client.set_default_header(HTTP_HEADER_USER_AGENT, user_agent)

    async def async_send_command_to_client(self, command: str):
        """Send a mower command to the Indego client."""
        _LOGGER.debug("Sending command to mower (%s): '%s'", self._serial, command)
        await self._indego_client.put_command(command)

    def _create_entities(self, device_info):
        """Create sub-entities and add them to Hass."""

        _LOGGER.debug("Creating entities")

        for entity_key, entity in ENTITY_DEFINITIONS.items():
            if entity[CONF_TYPE] == SENSOR_TYPE:
                self.entities[entity_key] = IndegoSensor(
                    f"indego_{entity_key}",
                    f"{self._mower_name} {entity[CONF_NAME]}",
                    entity[CONF_ICON],
                    entity[CONF_DEVICE_CLASS],
                    entity[CONF_UNIT_OF_MEASUREMENT],
                    entity[CONF_ATTR],
                    device_info,
                    translation_key=entity[CONF_TRANSLATION_KEY] if CONF_TRANSLATION_KEY in entity else None,
                )
                if entity_key == ENTITY_SERIAL_NUMBER:
                    # Avoid scheduling a state update before the entity is
                    # added to Home Assistant by setting the protected
                    # attribute directly.
                    self.entities[entity_key]._state = self._serial
                elif entity_key == ENTITY_API_ERRORS:
                    # Initialize API error counter with zero
                    self.entities[entity_key]._state = 0
                    # Avoid scheduling a state update before the entity is
                    # added to Home Assistant. Attributes will be set once
                    # the entity is registered, so disable sync here.
                    self.entities[entity_key].set_attributes({}, sync_state=False)

            elif entity[CONF_TYPE] == BINARY_SENSOR_TYPE:
                self.entities[entity_key] = IndegoBinarySensor(
                    f"indego_{entity_key}",
                    f"{self._mower_name} {entity[CONF_NAME]}",
                    entity[CONF_ICON],
                    entity[CONF_DEVICE_CLASS],
                    entity[CONF_ATTR],
                    device_info,
                    translation_key=entity[CONF_TRANSLATION_KEY] if CONF_TRANSLATION_KEY in entity else None,
                )

            elif entity[CONF_TYPE] == LAWN_MOWER_TYPE:
                if self._features[CONF_EXPOSE_INDEGO_AS_MOWER]:
                    self.entities[entity_key] = IndegoLawnMower(
                        "indego",
                        self._mower_name,
                        device_info,
                        self
                    )

            elif entity[CONF_TYPE] == VACUUM_TYPE:
                if self._features[CONF_EXPOSE_INDEGO_AS_VACUUM]:
                    self.entities[entity_key] = IndegoVacuum(
                        "indego",
                        self._mower_name,
                        device_info,
                        self
                    )

            elif entity[CONF_TYPE] == CAMERA_TYPE:
                if entity_key == ENTITY_CAMERA:
                    self.entities[entity_key] = IndegoMapCamera(
                        "indego",
                        self._mower_name,
                        device_info,
                        self,
                    )
                else:
                    self.entities[entity_key] = IndegoCamera(
                        "indego_progress",
                        self._mower_name,
                        device_info,
                        self,
                    )

    async def update_generic_data_and_load_platforms(self, load_platforms):
        """Update the generic mower data, so we can create the HA platforms for the Indego component."""
        _LOGGER.debug("Getting generic data for device info.")
        generic_data = await self._update_generic_data()

        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            manufacturer="Bosch",
            name=self._mower_name,
            model=generic_data.bareToolnumber if generic_data else None,
            sw_version=generic_data.alm_firmware_version if generic_data else None,
        )

        self._create_entities(device_info)
        await load_platforms()

        if self._hass.state == CoreState.running:
            # HA has already been started (this probably an integration reload).
            # Perform initial update right away...
            self._hass.async_create_task(self._initial_update())

        else:
            # HA is still starting, delay the initial update...
            self._hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._initial_update
            )

        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_shutdown)

    async def _initial_update(self, _=None):
        """Do the initial update and create all entities."""
        _LOGGER.debug("Starting initial update.")

        self.set_online_state(False)
        await self._create_refresh_state_task()
        await asyncio.gather(*[self.refresh_10m(), self.refresh_24h()])

        try:
            _LOGGER.debug("Refreshing initial operating data.")
            await self._update_operating_data()
        except Exception:
            _LOGGER.exception("Initial call to _update_operating_data failed")

    async def async_shutdown(self, _=None):
        """Remove all future updates, cancel tasks and close the client."""
        if self._shutdown:
            return

        _LOGGER.debug("Starting shutdown.")
        self._shutdown = True

        self._cancel_delayed_refresh_state()

        if self._refresh_state_task:
            self._refresh_state_task.cancel()
            await self._refresh_state_task
            self._refresh_state_task = None

        if self._refresh_10m_remover:
            self._refresh_10m_remover()

        if self._refresh_24h_remover:
            self._refresh_24h_remover()

        if self._unsub_map_timer:
            self._unsub_map_timer()
            self._unsub_map_timer = None

        await self._indego_client.close()
        _LOGGER.debug("Shutdown finished.")

    async def refresh_state(self):
        """Update the state, if necessary update operating data and recall itself."""
        _LOGGER.debug("Refreshing state.")
        self._cancel_delayed_refresh_state()

        update_failed = False
        try:
            await self._update_state(longpoll=(self._update_fail_count is None or self._update_fail_count == 0))
            self._update_fail_count = 0
            mower_state = getattr(self._indego_client.state, "mower_state", "unknown")
            if mower_state == "unknown":
                if self._last_state_ts is None:
                    _LOGGER.debug(
                        "Received unknown state for %s on initial update – refreshing",
                        self._serial,
                    )
                else:
                    _LOGGER.warning(
                        "Received unknown state for %s, last success at %s – refreshing",
                        self._serial,
                        self._last_state_ts,
                    )
                try:
                    await self._update_state(longpoll=False)
                except Exception as exc:  # noqa: BLE001
                    update_failed = True
                    _LOGGER.warning(
                        "Retry after unknown state failed for %s: %s",
                        self._serial,
                        str(exc),
                    )

        except Exception as exc:
            update_failed = True
            _LOGGER.warning(
                "Mower state update failed for %s, reason: %s",
                self._serial,
                str(exc),
            )
            self.set_online_state(False)

        if self._shutdown:
            return

        if update_failed:
            if self._update_fail_count is None:
                self._update_fail_count = 1
            _LOGGER.debug("Delaying next status update with %i seconds due to previous failure...", STATUS_UPDATE_FAILURE_DELAY_TIME[self._update_fail_count])
            when = datetime.now() + timedelta(seconds=STATUS_UPDATE_FAILURE_DELAY_TIME[self._update_fail_count])
            self._update_fail_count = min(self._update_fail_count + 1, len(STATUS_UPDATE_FAILURE_DELAY_TIME) - 1)
            self._unsub_refresh_state = async_track_point_in_time(self._hass, self._create_refresh_state_task, when)
            return

        if self._indego_client.state is not None:
            state = self._indego_client.state.state
            if (500 <= state <= 799) or (state in (257, 260)):
                try:
                    _LOGGER.debug("Refreshing operating data.")
                    await self._update_operating_data()

                except Exception as exc:
                    _LOGGER.warning(
                        "Mower operating data update failed for %s, reason: %s",
                        self._serial,
                        str(exc),
                    )

            if self._indego_client.state.error != self._latest_alert:
                self._latest_alert = self._indego_client.state.error
                try:
                    _LOGGER.debug("Refreshing alerts, to get new alert.")
                    await self._update_alerts()

                except Exception as exc:
                    _LOGGER.warning(
                        "Mower alerts update failed for %s, reason: %s",
                        self._serial,
                        str(exc),
                    )

        await self._create_refresh_state_task()

    async def _create_refresh_state_task(self, event=None):
        """Create a task to refresh the mower state."""
        self._refresh_state_task = self._hass.async_create_task(self.refresh_state())

    def _cancel_delayed_refresh_state(self):
        """Cancel a delayed refresh state callback (if any exists)."""
        if self._unsub_refresh_state is None:
            return

        self._unsub_refresh_state()
        self._unsub_refresh_state = None

    def _apply_pending_state(self, _=None):
        """Apply a debounced mower state update."""
        self._debounce_remover = None
        if self._pending_mower_state is None:
            return

        state, detail = self._pending_mower_state
        self._pending_mower_state = None
        self._pending_mower_detail = None

        self.entities[ENTITY_MOWER_STATE].state = state
        self.entities[ENTITY_MOWER_STATE_DETAIL].state = detail

        self.entities[ENTITY_MOWER_STATE].add_attributes({"last_updated": last_updated_now()})
        self.entities[ENTITY_MOWER_STATE_DETAIL].add_attributes(
            {
                "last_updated": last_updated_now(),
                "state_number": self._indego_client.state.state,
                "state_description": detail,
            }
        )

        self._last_state_ts = last_updated_now()

    def _schedule_state_update(self, state: str, detail: str) -> None:
        """Schedule a debounced mower state update."""
        self._pending_mower_state = state
        self._pending_mower_detail = detail
        if self._debounce_remover is not None:
            self._debounce_remover()
        self._debounce_remover = async_call_later(
            self._hass, STATE_DEBOUNCE_SECONDS, self._apply_pending_state
        )

    def _warn_once(self, msg: str, *args) -> None:
        """Log a warning only if more than 60 seconds passed since last time."""
        key = msg % args if args else msg
        now = time.time()
        last = self._last_error.get(key)
        if last is None or now - last > 60:
            _LOGGER.warning(msg, *args)
            self._last_error[key] = now

    def _log_api_error(self, err_type: str, msg: str, exc: Exception | None = None) -> None:
        """Log stack traces throttled per error type and count occurrences."""
        info = self._error_log.get(err_type, {"last": 0, "count": 0})
        now = time.time()
        if now - info["last"] > API_ERROR_LOG_INTERVAL:
            if info["count"]:
                _LOGGER.warning("%s occurred %i more times", err_type, info["count"])
            if exc is not None:
                _LOGGER.exception(msg)
            else:
                _LOGGER.warning(msg)
            info = {"last": now, "count": 0}
        else:
            info["count"] += 1
        self._error_log[err_type] = info
        self._api_error_stats[err_type] = self._api_error_stats.get(err_type, 0) + 1
    def _in_cooldown(self) -> bool:
        """Return True if requests are currently rate limited."""
        return time.time() < self._next_request_ts

    def _handle_rate_limit(self, exc: ClientResponseError) -> None:
        """Process HTTP 429 errors and set cooldown."""
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        delay = RETRY_AFTER_DEFAULT
        if retry_after:
            try:
                delay = int(retry_after)
            except ValueError:
                try:
                    delay_dt = parsedate_to_datetime(retry_after)
                    delay = max(0, (delay_dt - datetime.utcnow()).total_seconds())
                except Exception:  # noqa: BLE001
                    delay = RETRY_AFTER_DEFAULT
        self._next_request_ts = time.time() + delay
        self._warn_once(
            "Rate limit reached for %s, delaying API calls for %s seconds",
            self._serial,
            int(delay),
        )

    async def refresh_10m(self, _=None):
        """Refresh Indego sensors every 10m."""
        _LOGGER.debug("Refreshing 10m.")

        results = await asyncio.gather(
            *[
                self._update_generic_data(),
                self._update_alerts(),
                self._update_last_completed_mow(),
                self._update_next_mow(),
                self._update_forecast(),
            ],
            return_exceptions=True,
        )

        next_refresh = 600
        for index, res in enumerate(results):
            if res and isinstance(res, BaseException):
                try:
                    raise res
                except Exception as exc:
                    _LOGGER.warning(
                        "Error %s for index %i while performing 10m update for %s",
                        str(exc),
                        index,
                        self._serial,
                    )
        await self._update_api_error_sensor()

        self._refresh_10m_remover = async_call_later(
            self._hass, next_refresh, self.refresh_10m
        )

    async def refresh_24h(self, _=None):
        """Refresh Indego sensors every 24h."""
        _LOGGER.debug("Refreshing 24h.")

        try:
            await self._update_updates_available()

        except Exception as exc:
            _LOGGER.warning(
                "Error %s while performing 24h update for %s", str(exc), self._serial
            )

        self._refresh_24h_remover = async_call_later(self._hass, 86400, self.refresh_24h)

    def map_path(self):
        return f"/config/www/indego_map_{self._serial}.svg"

    async def download_and_store_map(self) -> None:
        """Download the current map from the mower and save it locally."""
        try:
            svg_bytes = await self._indego_client.get(f"alms/{self._serial}/map")
            if svg_bytes:
                path = self.map_path()
                os.makedirs(os.path.dirname(path), exist_ok=True)
                try:
                    async with aiofiles.open(path, "wb") as f:
                        await f.write(svg_bytes)
                    _LOGGER.info("Map saved in %s", path)
                except OSError as exc:
                    self._warn_once(
                        "Error during saving the map [%s]: %s", self._serial, exc
                    )
        except ClientResponseError as exc:
            _LOGGER.warning(
                "Map download for %s failed: HTTP %s - %s",
                self._serial,
                exc.status,
                exc.message,
            )
        except Exception as e:  # noqa: BLE001
            self._warn_once("Error during saving the map [%s]: %s", self._serial, e)

    async def start_periodic_position_update(self, interval: int | None = None):
        if interval is None:
            interval = self._position_interval

        if self._unsub_map_timer:
            self._unsub_map_timer()

        self._current_position_interval = interval
        self._unsub_map_timer = async_track_time_interval(
            self._hass, self._check_position_and_state, timedelta(seconds=interval)
        )

    async def _check_position_and_state(self, now):
        delays = [0, 1, 2, 4, 8]
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping position update for %s due to cooldown", self._serial
            )
            return
        delays = [0, 1, 2, 4]
        for attempt, delay in enumerate(delays, 1):
            if delay:
                await asyncio.sleep(delay)
            try:
                await asyncio.wait_for(
                    self._indego_client.update_state(
                        force=True, longpoll_timeout=self._longpoll_timeout
                    ),
                    timeout=self._state_update_timeout,
                )
                break
            except ClientResponseError as exc:
                if exc.status in (502, 429) and attempt < len(delays):
                    if exc.status == 429:
                        self._handle_rate_limit(exc)
                        return
                    if exc.status == 502:
                        if attempt == len(delays):
                            self._log_api_error(
                                "502",
                                "Failed to update state for %s due to HTTP 502" % self._serial,
                                exc,
                            )
                            return
                        continue
                if exc.status == 429:
                    self._log_api_error(
                        "429",
                        "Failed to update state for %s due to HTTP 429" % self._serial,
                        exc,
                    )
                    return
                self._api_error_count += 1
                self.entities[ENTITY_API_ERRORS].state = self._api_error_count
                _LOGGER.warning(
                    "Failed to update state for %s due to HTTP %s",
                    self._serial,
                    exc.status,
                )
                return
            except asyncio.TimeoutError:
                self._log_api_error("timeout", "Timeout on update_state() for %s – mower not available or too slow" % self._serial)
                return
            except Exception as exc:
                self._log_api_error("other", "Error on update_state() for %s – actual mower_state=%s" % (self._serial, self._last_state), exc)
                return
        try:
            await asyncio.wait_for(
                self._indego_client.update_state(
                    force=True, longpoll_timeout=self._longpoll_timeout
                ),
                timeout=self._state_update_timeout,
            )
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise
        except asyncio.TimeoutError:
            self._log_api_error(
                "timeout",
                "Timeout on update_state() for %s – mower not available or too slow" % self._serial,
            )
            return
        except Exception as e:
            self._log_api_error(
                "other",
                "Error on update_state() for %s – actual mower_state=%s" % (self._serial, self._last_state),
                e,
            )
            return

        state = self._indego_client.state
        if not state:
            self._warn_once("Received invalid state from mower")
            return

        mower_state = getattr(state, "mower_state", "unknown")
        if mower_state == "unknown":
            if self._last_state_ts is None:
                _LOGGER.debug(
                    "Received unknown state for %s on initial update – refreshing",
                    self._serial,
                )
            else:
                _LOGGER.warning(
                    "Received unknown state for %s, last success at %s – refreshing",
                    self._serial,
                    self._last_state_ts,
                )
            try:
                await self._update_state(longpoll=False)
            except Exception as exc:  # noqa: BLE001
                self._log_api_error(
                    "other",
                    "Retrying state refresh failed for %s: %s" % (self._serial, exc),
                    exc,
                )
                return
            state = self._indego_client.state
            if not state:
                _LOGGER.warning("Received invalid state from mower after retry")
                return
            mower_state = getattr(state, "mower_state", "unknown")

        xpos = getattr(state, "svg_xPos", None)
        ypos = getattr(state, "svg_yPos", None)
        self._last_state = mower_state


        if self._adaptive_updates:
            desired_interval = 60 if mower_state == "docked" else self._position_interval
            if desired_interval != self._current_position_interval:
                await self.start_periodic_position_update(desired_interval)

        if mower_state == "docked":
            _LOGGER.debug("Mower is docked - no position updates")
            return

        if xpos is not None and ypos is not None:
            if (xpos, ypos) != self._last_position:
                _LOGGER.info("Position changed: x=%s, y=%s", xpos, ypos)
                self._last_position = (xpos, ypos)
                for entity in self.entities.values():
                    if hasattr(entity, "refresh_map"):
                        await entity.refresh_map(mower_state)
    
    async def _update_operating_data(self):
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping operating data update for %s due to cooldown", self._serial
            )
            return
        try:
            await self._indego_client.update_operating_data()
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            self._log_api_error(
                "timeout",
                "Timeout while updating operating data for %s. This usually means the mower did not respond in time: %s" % (self._serial, exc),
                exc,
            )
            return
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            _LOGGER.warning(
                "Failed to update operating data for %s: HTTP %s - %s",
                self._serial,
                exc.status,
                exc.message,
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._log_api_error(
                "other",
                "Failed to update operating data for %s: %s" % (self._serial, exc),
                exc,
            )
            return

        _LOGGER.debug("Updating operating data")
        if self._indego_client.operating_data:
            self.entities[ENTITY_BATTERY].state = self._indego_client.operating_data.battery.percent_adjusted

            if ENTITY_VACUUM in self.entities:
                self.entities[ENTITY_VACUUM].battery_level = self._indego_client.operating_data.battery.percent_adjusted

            self.entities[ENTITY_GARDEN_SIZE].state = self._indego_client.operating_data.garden.size

            self.entities[ENTITY_AMBIENT_TEMP].state = (
                self._indego_client.operating_data.battery.ambient_temp
            )
            self.entities[ENTITY_BATTERY_TEMP].state = (
                self._indego_client.operating_data.battery.battery_temp
            )

            self.entities[ENTITY_BATTERY].add_attributes(
                {
                    "last_updated": last_updated_now(),
                    "voltage_V": self._indego_client.operating_data.battery.voltage,
                    "discharge_Ah": self._indego_client.operating_data.battery.discharge,
                    "cycles": self._indego_client.operating_data.battery.cycles,
                    f"battery_temp_{UnitOfTemperature.CELSIUS}": self._indego_client.operating_data.battery.battery_temp,
                    f"ambient_temp_{UnitOfTemperature.CELSIUS}": self._indego_client.operating_data.battery.ambient_temp,
                }
            )

            runtime = self._indego_client.operating_data.runtime
            self.entities[ENTITY_TOTAL_OPERATION_TIME].state = runtime.total.operate
            self.entities[ENTITY_TOTAL_MOWING_TIME].state = runtime.total.cut
            self.entities[ENTITY_TOTAL_CHARGING_TIME].state = runtime.total.charge

            self.entities[ENTITY_BATTERY_CYCLES].state = self._indego_client.operating_data.battery.cycles

            if runtime.session.operate:
                sessions = runtime.total.operate / (runtime.session.operate / 60)
                if sessions:
                    avg = runtime.total.cut / sessions
                    self.entities[ENTITY_AVERAGE_MOW_TIME].state = round(avg * 60, 1)
            if hasattr(self, "_weekly_area_entries"):
                total_area = sum(float(a) for t, a in self._weekly_area_entries)
                self.entities[ENTITY_WEEKLY_AREA].state = total_area

    def set_online_state(self, online: bool):
        _LOGGER.debug("Set online state: %s", online)

        if online:
            self._offline_since = None
            self._offline_failures = 0
        else:
            now = time.monotonic()
            if self._offline_since is None:
                self._offline_since = now
            self._offline_failures += 1
            if (
                self._offline_failures < 2
                and now - self._offline_since < OFFLINE_GRACE_PERIOD
            ):
                _LOGGER.debug(
                    "Suppressing transient offline state (%s fails)",
                    self._offline_failures,
                )
                return
            if self._debounce_remover is not None:
                self._debounce_remover()
                self._debounce_remover = None
                self._pending_mower_state = None
                self._pending_mower_detail = None

        if self._online == online:
            return

        self._online = online
        self.entities[ENTITY_ONLINE].state = online
        self.entities[ENTITY_MOWER_STATE].set_cloud_connection_state(online)
        self.entities[ENTITY_MOWER_STATE_DETAIL].set_cloud_connection_state(online)

        if ENTITY_VACUUM in self.entities:
            self.entities[ENTITY_VACUUM].set_cloud_connection_state(online)

        if ENTITY_LAWN_MOWER in self.entities:
            self.entities[ENTITY_LAWN_MOWER].set_cloud_connection_state(online)

    async def _update_state(self, longpoll: bool = True):
        delays = [0, 1, 2, 4, 8]
        if self._in_cooldown():
            _LOGGER.debug("Skipping state update for %s due to cooldown", self._serial)
            return
        try:
            await asyncio.wait_for(
                self._indego_client.update_state(
                    longpoll=longpoll, longpoll_timeout=self._longpoll_timeout
                ),
                timeout=self._state_update_timeout,
            )
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise
        delays = [0, 1, 2, 4]
        for attempt, delay in enumerate(delays, 1):
            if delay:
                await asyncio.sleep(delay)
            try:
                await asyncio.wait_for(
                    self._indego_client.update_state(
                        longpoll=longpoll, longpoll_timeout=self._longpoll_timeout
                    ),
                    timeout=self._state_update_timeout,
                )
                break
            except ClientResponseError as exc:
                if exc.status in (502, 429) and attempt < len(delays):
                    if exc.status == 429:
                        self._handle_rate_limit(exc)
                        return
                    if exc.status == 502:
                        if attempt == len(delays):
                            self._log_api_error(
                                "502",
                                "Failed to update state for %s due to HTTP 502" % self._serial,
                                exc,
                            )
                            raise
                        continue
                if exc.status == 429:
                    self._log_api_error(
                        "429",
                        "Failed to update state for %s due to HTTP 429" % self._serial,
                        exc,
                    )
                    raise
                self._api_error_count += 1
                self.entities[ENTITY_API_ERRORS].state = self._api_error_count
                self._warn_once(
                    "Error while updating state for %s: HTTP %s",
                    self._serial,
                    exc.status,
                )
                raise
            except Exception as exc:
                self._warn_once(
                    "Error while updating state for %s: %s",
                    self._serial,
                    exc,
                )
                raise
        try:
            await asyncio.wait_for(
                self._indego_client.update_state(
                    longpoll=longpoll, longpoll_timeout=self._longpoll_timeout
                ),
                timeout=self._state_update_timeout,
            )
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise
        except Exception as exc:
            self._log_api_error("other", "Error while updating state for %s: %s" % (self._serial, exc), exc)
            raise

        if self._shutdown:
            return

        if self._indego_client.state is None:
            self.set_online_state(False)
            return  # State update failed

        # Refresh Camera map if Position is available
        new_x = self._indego_client.state.svg_xPos
        new_y = self._indego_client.state.svg_yPos
        mower_state = getattr(self._indego_client.state, "mower_state", "unknown")


        if new_x is not None and new_y is not None:
            for entity in self.entities.values():
                if hasattr(entity, "refresh_map"):
                    await entity.refresh_map(mower_state)
        
        self.set_online_state(self._indego_client.online)
        self._schedule_state_update(
            self._indego_client.state_description,
            self._indego_client.state_description_detail,
        )
        self.entities[ENTITY_LAWN_MOWED].state = self._indego_client.state.mowed
        self.entities[ENTITY_RUNTIME].state = self._indego_client.state.runtime.total.cut
        self.entities[ENTITY_BATTERY].charging = (
            True if self._indego_client.state_description_detail == "Charging" else False
        )

        self.entities[ENTITY_LAWN_MOWED].add_attributes(
            {
                "last_updated": last_updated_now(),
                "last_session_operation_min": self._indego_client.state.runtime.session.operate,
                "last_session_cut_min": self._indego_client.state.runtime.session.cut,
                "last_session_charge_min": self._indego_client.state.runtime.session.charge,
            }
        )

        self.entities[ENTITY_RUNTIME].add_attributes(
            {
                "total_operation_time_h": self._indego_client.state.runtime.total.operate,
                "total_mowing_time_h": self._indego_client.state.runtime.total.cut,
                "total_charging_time_h": self._indego_client.state.runtime.total.charge,
            }
        )

        runtime = self._indego_client.state.runtime
        if runtime.session.operate:
            sessions = runtime.total.operate / (runtime.session.operate / 60)
            if sessions:
                avg = runtime.total.cut / sessions
                self.entities[ENTITY_AVERAGE_MOW_TIME].state = round(avg * 60, 1)

        if hasattr(self, "_weekly_area_entries"):
            total_area = sum(float(a) for t, a in self._weekly_area_entries)
            self.entities[ENTITY_WEEKLY_AREA].state = total_area

        if ENTITY_VACUUM in self.entities:
            self.entities[ENTITY_VACUUM].indego_state = self._indego_client.state.state
            self.entities[ENTITY_VACUUM].battery_charging = self.entities[ENTITY_BATTERY].charging

        if ENTITY_LAWN_MOWER in self.entities:
            self.entities[ENTITY_LAWN_MOWER].indego_state = self._indego_client.state.state

    async def _update_generic_data(self):
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping generic data update for %s due to cooldown", self._serial
            )
            return
        try:
            await self._indego_client.update_generic_data()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise

        if self._indego_client.generic_data:
            if ENTITY_MOWING_MODE in self.entities:
                self.entities[
                    ENTITY_MOWING_MODE
                ].state = self._indego_client.generic_data.mowing_mode_description

            if ENTITY_FIRMWARE in self.entities:
                self.entities[ENTITY_FIRMWARE].state = (
                    self._indego_client.generic_data.alm_firmware_version
                )

        return self._indego_client.generic_data

    async def _update_alerts(self):
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping alerts update for %s due to cooldown", self._serial
            )
            return
        try:
            await self._indego_client.update_alerts()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise

        self.entities[ENTITY_ALERT].state = self._indego_client.alerts_count > 0

        if self._indego_client.alerts:
            self.entities[ENTITY_ALERT].add_attributes(
                {
                    "alerts_count": self._indego_client.alerts_count,
                    "last_alert_error_code": self._indego_client.alerts[0].error_code,
                    "last_alert_message": self._indego_client.alerts[0].message,
                    "last_alert_date": format_indego_date(self._indego_client.alerts[0].date),
                    "last_alert_read": self._indego_client.alerts[0].read_status,
                }, False
            )

            # It's not recommended to track full alerts, disabled by default.
            # See the developer docs: https://developers.home-assistant.io/docs/core/entity/
            if self._features[CONF_SHOW_ALL_ALERTS]:
                alert_index = 0
                for index, alert in enumerate(self._indego_client.alerts):
                    self.entities[ENTITY_ALERT].add_attributes({
                        ("alert_%i" % index): "%s: %s" % (format_indego_date(alert.date), alert.message)
                    }, False)
                    alert_index = index

                # Clear any other alerts that no longer exist.
                alert_index += 1
                while self.entities[ENTITY_ALERT].clear_attribute("alert_%i" % alert_index, False):
                    alert_index += 1

            self.entities[ENTITY_ALERT].async_schedule_update_ha_state()

        else:
            self.entities[ENTITY_ALERT].set_attributes(
                {
                    "alerts_count": self._indego_client.alerts_count
                }
            )

    async def _update_updates_available(self):
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping update check for %s due to cooldown", self._serial
            )
            return
        try:
            await self._indego_client.update_updates_available()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise

        self.entities[ENTITY_UPDATE_AVAILABLE].state = self._indego_client.update_available

    async def _update_last_completed_mow(self):
        if self._in_cooldown():
            _LOGGER.debug(
                "Skipping last completed mow update for %s due to cooldown",
                self._serial,
            )
            return
        try:
            await self._indego_client.update_last_completed_mow()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise

        if self._indego_client.last_completed_mow:
            self.entities[
                ENTITY_LAST_COMPLETED
            ].state = self._indego_client.last_completed_mow.isoformat()

            self.entities[ENTITY_LAWN_MOWED].add_attributes(
                {
                    "last_completed_mow": format_indego_date(self._indego_client.last_completed_mow)
                }
            )

            if self._last_completed_ts != self._indego_client.last_completed_mow:
                self._last_completed_ts = self._indego_client.last_completed_mow
                size = self.entities[ENTITY_GARDEN_SIZE].state
                if size is not None:
                    try:
                        size_val = float(size)
                    except (TypeError, ValueError):
                        _LOGGER.debug("Invalid garden size value: %s", size)
                        size_val = None
                    if size_val is not None:
                        self._weekly_area_entries.append((self._last_completed_ts, size_val))
                        week_ago = utcnow() - timedelta(days=7)
                        self._weekly_area_entries = [ (t, a) for t, a in self._weekly_area_entries if t >= week_ago ]

    async def _update_next_mow(self):
        if self._in_cooldown():
            _LOGGER.debug("Skipping next mow update for %s due to cooldown", self._serial)
            return
        try:
            await self._indego_client.update_next_mow()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            _LOGGER.warning(
                "Failed to update next mow for %s: HTTP %s - %s",
                self._serial,
                exc.status,
                exc.message,
            )
            return
        except Exception as exc:
            self._log_api_error(
                "other",
                "Failed to update next mow for %s: %s" % (self._serial, exc),
                exc,
            )
            return

        if self._indego_client.next_mow:
            self.entities[ENTITY_NEXT_MOW].state = self._indego_client.next_mow.isoformat()

            next_mow = format_indego_date(self._indego_client.next_mow)

            self.entities[ENTITY_NEXT_MOW].add_attributes(
                {"next_mow": next_mow}
            )

            self.entities[ENTITY_LAWN_MOWED].add_attributes(
                {"next_mow": next_mow}
            )

    async def _update_forecast(self):
        if self._in_cooldown():
            _LOGGER.debug("Skipping forecast update for %s due to cooldown", self._serial)
            return
        try:
            await self._indego_client.update_predictive_calendar()
        except ClientResponseError as exc:
            if exc.status == 429:
                self._handle_rate_limit(exc)
                return
            raise

        if self._indego_client.predictive_calendar:
            calendar = self._indego_client.predictive_calendar
            forecast = calendar[0] if isinstance(calendar, list) else calendar

            if isinstance(forecast, dict):
                recommendation = forecast.get("recommendation")
                rain_chance = forecast.get("rainChance")
                next_start = forecast.get("nextStart")
            else:
                recommendation = getattr(forecast, "recommendation", None)
                rain_chance = getattr(forecast, "rainChance", None)
                next_start = getattr(forecast, "nextStart", None)

            self.entities[ENTITY_FORECAST].state = recommendation

            self.entities[ENTITY_FORECAST].set_attributes(
                {
                    "rain_probability": rain_chance,
                    "recommended_next_mow": next_start,
                }
            )

    async def _update_api_error_sensor(self, _=None):
        """Update the API error sensor with aggregated counts."""
        if ENTITY_API_ERRORS not in self.entities:
            return
        self.entities[ENTITY_API_ERRORS].state = sum(self._api_error_stats.values())
        self.entities[ENTITY_API_ERRORS].set_attributes(dict(self._api_error_stats))

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def client(self) -> IndegoAsyncClient:
        return self._indego_client

    @property
    def progress_line_width(self) -> int:
        return self._progress_line_width

    @property
    def progress_line_color(self) -> str:
        return self._progress_line_color
