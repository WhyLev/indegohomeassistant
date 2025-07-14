"""Component for integrating a Bosch Indego lawn mower."""
import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import aiofiles
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_time_interval,
)
import homeassistant.util.dt
import voluptuous as vol
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
import sys
import os.path as path

# Add local pyIndego to the Python path
pyindego_path = path.join(path.dirname(path.dirname(path.dirname(__file__))), 'pyindego', 'pyIndego')
if pyindego_path not in sys.path:
    sys.path.insert(0, pyindego_path)

from indego_async_client import IndegoAsyncClient
from svgutils.transform import fromstring

from .api import IndegoOAuth2Session
from .binary_sensor import IndegoBinarySensor
from .vacuum import IndegoVacuum
from .lawn_mower import IndegoLawnMower
from .const import *
from .sensor import IndegoSensor
from .camera import IndegoCamera, IndegoMapCamera
from .api_manager import IndegoApiManager

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

    return True

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

        try:
            await instance._api.get_state(force=True)  # Ensure we have latest state
            await instance._indego_client.set_smart_mowing(enable == "on")
            await instance._api.get_generic_data(force=True)  # Force refresh generic data
        except Exception as exc:
            _LOGGER.error("Failed to set smart mowing mode: %s", str(exc))
            raise

    async def async_delete_alert(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        index = call.data.get(SERVER_DATA_ALERT_INDEX, DEFAULT_NAME_COMMANDS)
        _LOGGER.debug("Indego.delete_alert service called with alert index: %s", index)

        try:
            await instance._api.get_alerts()  # Get latest alerts first
            await instance._indego_client.delete_alert(index)
            # Force refresh alerts after deletion
            instance._api.invalidate_cache('alerts')
            await instance._api.get_alerts()
        except Exception as exc:
            _LOGGER.error("Failed to delete alert: %s", str(exc))
            raise

    async def async_delete_alert_all(call):
        """Handle the service call."""
        instance = find_instance_for_mower_service_call(call)
        _LOGGER.debug("Indego.delete_alert_all service called")

        try:
            await instance._api.get_alerts()  # Get latest alerts first
            await instance._indego_client.delete_all_alerts()
            # Force refresh alerts after deletion
            instance._api.invalidate_cache('alerts')
            await instance._api.get_alerts()
        except Exception as exc:
            _LOGGER.error("Failed to delete all alerts: %s", str(exc))
            raise

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
    """Indego API hub."""

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
