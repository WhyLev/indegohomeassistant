"""Base class for indego."""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Callable, Awaitable

import pytz

from .const import (
    DEFAULT_HEADERS,
    DEFAULT_CALENDAR,
    DEFAULT_URL,
    MOWER_STATE_DESCRIPTION,
    MOWER_STATE_DESCRIPTION_DETAIL,
    Methods,
)
from .helpers import convert_bosch_datetime, generate_update
from .states import (
    Alert,
    Calendar,
    Config,
    GenericData,
    Location,
    Network,
    OperatingData,
    PredictiveSchedule,
    Security,
    Setup,
    State,
    User,
)

_LOGGER = logging.getLogger(__name__)


class IndegoBaseClient(ABC):
    """Indego base client class."""

    def __init__(
        self,
        token: str,
        token_refresh_method: Optional[Callable[[], Awaitable[str]]] = None,
        serial: str = None,
        map_filename: str = None,
        api_url: str = DEFAULT_URL,
        raise_request_exceptions: bool = False,
    ):
        """Abstract class for the Indego Client."""
        self._default_headers = DEFAULT_HEADERS.copy()
        self._token = token
        self._token_refresh_method = token_refresh_method
        self._serial = serial
        self._mowers_in_account = None
        self.map_filename = map_filename
        self._api_url = api_url
        self._raise_request_exceptions = raise_request_exceptions
        self._logged_in = False
        self._online = False
        self._contextid = ""
        self._userid = None
        self._headers = self._default_headers.copy()

        self.alerts = []
        self._alerts_loaded = False
        self.calendar = None
        self.config = None
        self.generic_data = None
        self.last_completed_mow = None
        self.location = None
        self.network = None
        self.next_mow = None
        self.operating_data = None
        self.predictive_calendar = None
        self.predictive_schedule = None
        self.security = None
        self.state = None
        self.setup = None
        self.runtime = None
        self.update_available = False
        self.user = None

    def _get_alert_by_index(self, alert_index: int) -> str:
        """Get alert ID by index."""
        try:
            return self.alerts[alert_index - 1].alert_id
        except IndexError:
            _LOGGER.error(
                "Alert index %d is out of range (alerts: %d)",
                alert_index,
                len(self.alerts)
            )
            return None

    def _update_alerts(self, alerts_raw: list):
        """Update alerts."""
        self.alerts = []
        if alerts_raw:
            for alert in alerts_raw:
                self.alerts.append(Alert(**alert))

    def _update_calendar(self, calendar_raw):
        """Update calendar."""
        if calendar_raw:
            self.calendar = Calendar(**calendar_raw)

    def _update_config(self, config_raw):
        """Update config."""
        if config_raw:
            self.config = Config(**config_raw)

    def _update_generic_data(self, generic_data_raw):
        """Update generic data."""
        if generic_data_raw:
            self.generic_data = GenericData(**generic_data_raw)

    def _update_last_completed_mow(self, last_completed_raw):
        """Update last completed mow."""
        if last_completed_raw:
            self.last_completed_mow = convert_bosch_datetime(last_completed_raw["last_mowed"])

    def _update_location(self, location_raw):
        """Update location."""
        if location_raw:
            self.location = Location(**location_raw)

    def _update_network(self, network_raw):
        """Update network."""
        if network_raw:
            self.network = Network(**network_raw)

    def _update_next_mow(self, next_mow_raw):
        """Update next mow datetime."""
        if next_mow_raw:
            self.next_mow = convert_bosch_datetime(next_mow_raw["mow_next"])

    def _update_operating_data(self, operating_data_raw):
        """Update operating data."""
        if operating_data_raw:
            self.operating_data = OperatingData(**operating_data_raw)

    def _update_predictive_calendar(self, predictive_calendar_raw):
        """Update predictive calendar."""
        if predictive_calendar_raw:
            self.predictive_calendar = Calendar(**predictive_calendar_raw)

    def _update_predictive_schedule(self, predictive_schedule_raw):
        """Update predictive schedule."""
        if predictive_schedule_raw:
            self.predictive_schedule = PredictiveSchedule(**predictive_schedule_raw)

    def _update_security(self, security_raw):
        """Update security."""
        if security_raw:
            self.security = Security(**security_raw)

    def _update_setup(self, setup_raw):
        """Update setup."""
        if setup_raw:
            self.setup = Setup(**setup_raw)

    def _update_state(self, state_raw):
        """Update state."""
        if state_raw:
            self.state = State(**state_raw)
            self.runtime = self.state.runtime

    def _update_updates_available(self, update_raw):
        """Update updates available."""
        if update_raw:
            self.update_available = update_raw.get("available", False)

    def _update_user(self, user_raw):
        """Update users."""
        if user_raw:
            self.user = User(**user_raw)

    def set_default_header(self, header: str, value: str):
        """Set headers to use for calls."""
        self._headers[header] = value

    @property
    def serial(self):
        """Return the serial number of the mower."""
        if self._serial:
            return self._serial
        _LOGGER.warning("Serial not yet set, please login first")
        return None

    @property
    def mowers_in_account(self):
        """Return the list of mower detected during login."""
        return self._mowers_in_account

    @property
    def alerts_count(self):
        """Return the count of alerts."""
        if self.alerts:
            return len(self.alerts)
        return 0

    @property
    def state_description(self):
        """Return the description of the state."""
        if self.state:
            return MOWER_STATE_DESCRIPTION.get(self.state.state, "Unknown State")
        _LOGGER.warning("Please call update_state before calling this property")
        return None

    @property
    def state_description_detail(self):
        """Return the description detail of the state."""
        if self.state:
            return MOWER_STATE_DESCRIPTION_DETAIL.get(
                self.state.state, "Unknown State Detail"
            )
        _LOGGER.warning("Please call update_state before calling this property")
        return None

    @property
    def next_mows(self):
        """Return the next mows from the calendar without a timezone."""
        if self.calendar:
            return [
                slot.dt for day in self.calendar.days for slot in day.slots if slot.dt
            ]
        _LOGGER.warning("Please call update_calendar before calling this property")
        return None

    @property
    def next_mows_with_tz(self):
        """Return the next mows from the calendar with timezone from location."""
        if self.location and self.calendar:
            return [
                slot.dt.astimezone(pytz.timezone(self.location.timezone))
                for day in self.calendar.days
                for slot in day.slots
                if slot.dt
            ]
        if not self.location:
            _LOGGER.warning("Please call update_location before calling this property")
        if not self.calendar:
            _LOGGER.warning("Please call update_calendar before calling this property")
        return None

    # Abstract methods that must be implemented by derived classes
    @abstractmethod
    def delete_alert(self, alert_index: int):
        """Delete the alert with the specified index."""

    @abstractmethod
    def delete_all_alerts(self):
        """Delete all the alerts."""

    @abstractmethod
    def download_map(self, filename=None):
        """Download the map."""

    @abstractmethod
    def put_alert_read(self, alert_index: int):
        """Set to read the read_status of the alert with the specified index."""

    @abstractmethod
    def put_all_alerts_read(self):
        """Set to read the read_status of all alerts."""

    @abstractmethod
    def put_command(self, command: str):
        """Send a command to the mower."""

    @abstractmethod
    def put_mow_mode(self, command: Any):
        """Set the mower to mode manual (false-ish) or predictive (true-ish)."""

    @abstractmethod
    def put_predictive_cal(self, calendar: dict = DEFAULT_CALENDAR):
        """Set the predictive calendar."""

    @abstractmethod
    def update_alerts(self):
        """Update alerts."""

    @abstractmethod
    def get_alerts(self):
        """Update alerts and return them."""

    @abstractmethod
    def update_all(self):
        """Update all."""
