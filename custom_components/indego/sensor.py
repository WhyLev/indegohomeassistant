"""Class for Indego Sensors."""
import logging

from homeassistant.components.sensor import SensorEntity, ENTITY_ID_FORMAT as SENSOR_FORMAT, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.const import TIME_MINUTES, AREA_SQUARE_METERS
from .mixins import IndegoEntity
from .const import DATA_UPDATED, DOMAIN, ENTITY_BATTERY_CYCLES, ENTITY_AVERAGE_MOW_TIME, ENTITY_WEEKLY_AREA

_LOGGER = logging.getLogger(__name__)


INDEGO_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ENTITY_BATTERY_CYCLES,
        name="Battery Cycles",
        icon="mdi:battery-heart-variant",
    ),
    SensorEntityDescription(
        key=ENTITY_AVERAGE_MOW_TIME,
        name="Average Mow Time",
        icon="mdi:clock-outline",
        native_unit_of_measurement=TIME_MINUTES,
    ),
    SensorEntityDescription(
        key=ENTITY_WEEKLY_AREA,
        name="Weekly Area Mowed",
        icon="mdi:texture-box",
        native_unit_of_measurement=AREA_SQUARE_METERS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    indego_hub = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        entity
        for entity in indego_hub.entities.values()
        if isinstance(entity, IndegoSensor)
    ]

    for description in INDEGO_SENSORS:
        if description.key == ENTITY_BATTERY_CYCLES:
            entities.append(
                IndegoBatteryCyclesSensor(
                    f"{indego_hub.name}_{description.key}",
                    description.name,
                    description.icon,
                    indego_hub.device_info,
                )
            )
        elif description.key == ENTITY_AVERAGE_MOW_TIME:
            entities.append(
                IndegoAverageMowTimeSensor(
                    f"{indego_hub.name}_{description.key}",
                    description.name,
                    description.icon,
                    indego_hub.device_info,
                )
            )
        elif description.key == ENTITY_WEEKLY_AREA:
            entities.append(
                IndegoWeeklyAreaSensor(
                    f"{indego_hub.name}_{description.key}",
                    description.name,
                    description.icon,
                    indego_hub.device_info,
                )
            )

    async_add_entities(entities, True)


class IndegoSensor(IndegoEntity, SensorEntity):
    """Class for Indego Sensors."""

    def __init__(self, entity_id, name, icon, device_class, unit_of_measurement, attributes, device_info: DeviceInfo, translation_key: str = None):
        """Initialize a sensor.

        Args:
            entity_id (str): entity_id of the sensor
            name (str): name of the sensor
            icon (str, Callable): string or function for icons
            device_class (str): device class of the sensor
            unit_of_measurement (str): unit of measurement of the sensor
            device_info (DeviceInfo): Initial device info
            translation_key: Optional translation key for (custom state) translations
        """
        super().__init__(SENSOR_FORMAT.format(entity_id), name, icon, attributes, device_info)

        self._device_class = device_class
        self._unit = unit_of_measurement
        self.charging = False
        self._attr_translation_key = translation_key

    async def async_added_to_hass(self):
        """Once the sensor is added, see if it was there before and pull in that state."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()

        if state is None or state.state is None:
            return

        self.state = state.state
        async_dispatcher_connect(
            self.hass, DATA_UPDATED, self._schedule_immediate_update
        )

    @property
    def state(self):
        """Get the state."""
        return self._state

    @state.setter
    def state(self, new):
        """Set the state to new."""
        if self._state != new:
            self._state = new
            self.async_schedule_update_ha_state()

    @property
    def device_class(self) -> str:
        """Return device class."""
        return self._device_class

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        if self._updateble_icon:
            return self._icon_func(self._state)
        if self._icon == "battery":
            return icon_for_battery_level(
                int(self._state) if self._state is not None and (isinstance(self._state, int) or self._state.isdigit()) else None, self.charging
            )
        return self._icon

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self._unit


class IndegoBatteryCyclesSensor(IndegoSensor):
    """Sensor for battery cycles."""

    def __init__(self, entity_id, name, icon, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(entity_id, name, icon, None, None, None, device_info)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if op_data := self._indego_hub.coordinator.data.get("operating_data"):
            self.state = op_data.battery.cycles
        super()._handle_coordinator_update()


class IndegoAverageMowTimeSensor(IndegoSensor):
    """Sensor for average mow time."""

    def __init__(self, entity_id, name, icon, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(entity_id, name, icon, None, TIME_MINUTES, None, device_info)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.state = 0
        if op_data := self._indego_hub.coordinator.data.get("operating_data"):
            total_mowing_time = op_data.runtime.total_mowing
            total_mowing_sessions = op_data.runtime.total_mowing_sessions
            if total_mowing_sessions > 0:
                self.state = total_mowing_time / total_mowing_sessions
        super()._handle_coordinator_update()


class IndegoWeeklyAreaSensor(IndegoSensor):
    """Sensor for weekly area mowed."""

    def __init__(self, entity_id, name, icon, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(entity_id, name, icon, None, AREA_SQUARE_METERS, None, device_info)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.state = 0
        if op_data := self._indego_hub.coordinator.data.get("operating_data"):
            self.state = op_data.garden.get("weekly_mowing", 0)
        super()._handle_coordinator_update()
