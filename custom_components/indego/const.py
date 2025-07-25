"""Constants for Indego integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "indego"

# OAuth2 endpoints
OAUTH2_AUTHORIZE: Final = "https://prodindego.b2clogin.com/prodindego.onmicrosoft.com/b2c_1a_signup_signin/oauth2/v2.0/authorize"
OAUTH2_TOKEN: Final = "https://prodindego.b2clogin.com/prodindego.onmicrosoft.com/b2c_1a_signup_signin/oauth2/v2.0/token"
OAUTH2_CLIENT_ID: Final = "65bb8c9d-1070-4fb4-aa95-853618acc876"

# API Configuration
API_BASE_URL: Final = "https://api.indego.iot.bosch-si.com/api/v1"
API_DEFAULT_TIMEOUT: Final = 30
API_RATE_LIMIT_REQUESTS: Final = 150
API_RATE_LIMIT_WINDOW: Final = timedelta(minutes=1)
API_RETRY_COUNT: Final = 3
API_BACKOFF_FACTOR: Final = 1.5

# Update intervals
UPDATE_INTERVAL: Final = timedelta(minutes=5)
POSITION_UPDATE_INTERVAL: Final = timedelta(seconds=10)
STATE_UPDATE_INTERVAL: Final = timedelta(seconds=5)
CALENDAR_UPDATE_INTERVAL: Final = timedelta(minutes=15)

# Cache TTLs
CACHE_TTL_STATE: Final = timedelta(seconds=5)
CACHE_TTL_CALENDAR: Final = timedelta(minutes=15)
CACHE_TTL_ALERTS: Final = timedelta(minutes=1)
CACHE_TTL_GENERIC: Final = timedelta(minutes=60)

# Status update retry delays
STATUS_UPDATE_FAILURE_DELAY_TIME: Final = [0, 10, 30, 60]

# Configuration keys
CONF_MOWER_SERIAL: Final = "mower_serial"
CONF_MOWER_NAME: Final = "mower_name"
CONF_EXPOSE_INDEGO_AS_MOWER: Final = "expose_mower"
CONF_EXPOSE_INDEGO_AS_VACUUM: Final = "expose_vacuum"
CONF_SHOW_ALL_ALERTS: Final = "show_all_alerts"
CONF_USER_AGENT: Final = "user_agent"
CONF_SERVICES_REGISTERED: Final = "services_registered"
CONF_TRANSLATION_KEY: Final = "translation_key"
CONF_ATTR: Final = "attributes"
CONF_SEND_COMMAND: Final = "command"
CONF_SMARTMOWING: Final = "enable"
CONF_POLLING: Final = "polling"
CONF_POSITION_UPDATE_INTERVAL: Final = "position_update_interval"
CONF_ADAPTIVE_POSITION_UPDATES: Final = "adaptive_position_updates"
CONF_STATE_UPDATE_TIMEOUT: Final = "state_update_timeout"
CONF_LONGPOLL_TIMEOUT: Final = "longpoll_timeout"

# Default values
DEFAULT_NAME: Final = "Indego"
DEFAULT_POSITION_UPDATE_INTERVAL: Final = 10
DEFAULT_ADAPTIVE_POSITION_UPDATES: Final = True
DEFAULT_STATE_UPDATE_TIMEOUT: Final = 10
DEFAULT_LONGPOLL_TIMEOUT: Final = 60
DEFAULT_NAME_COMMANDS: Final = None

# Services
SERVICE_NAME_COMMAND: Final = "command"
SERVICE_NAME_SMARTMOW: Final = "smartmowing"
SERVICE_NAME_DELETE_ALERT: Final = "delete_alert"
SERVICE_NAME_READ_ALERT: Final = "read_alert"
SERVICE_NAME_DELETE_ALERT_ALL: Final = "delete_alert_all"
SERVICE_NAME_READ_ALERT_ALL: Final = "read_alert_all"
SERVICE_NAME_DOWNLOAD_MAP: Final = "download_map"
SERVICE_NAME_REFRESH: Final = "refresh"

# Entity types
CAMERA_TYPE: Final = "camera"
SENSOR_TYPE: Final = "sensor"
BINARY_SENSOR_TYPE: Final = "binary_sensor"
VACUUM_TYPE: Final = "vacuum"
LAWN_MOWER_TYPE: Final = "lawn_mower"
INDEGO_PLATFORMS: Final = [
    SENSOR_TYPE,
    BINARY_SENSOR_TYPE,
    VACUUM_TYPE,
    LAWN_MOWER_TYPE,
    CAMERA_TYPE
]

# Entity IDs
ENTITY_ONLINE: Final = "online"
ENTITY_UPDATE_AVAILABLE: Final = "update_available"
ENTITY_ALERT: Final = "alert"
ENTITY_MOWER_STATE: Final = "mower_state"
ENTITY_MOWER_STATE_DETAIL: Final = "mower_state_detail"
ENTITY_BATTERY: Final = "battery_percentage"
ENTITY_AMBIENT_TEMP: Final = "ambient_temperature"
ENTITY_BATTERY_TEMP: Final = "battery_temperature"
ENTITY_LAWN_MOWED: Final = "lawn_mowed"
ENTITY_LAST_COMPLETED: Final = "last_completed"
ENTITY_NEXT_MOW: Final = "next_mow"
ENTITY_MOWING_MODE: Final = "mowing_mode"
ENTITY_RUNTIME: Final = "runtime_total"
ENTITY_TOTAL_MOWING_TIME: Final = "total_mowing_time"
ENTITY_TOTAL_CHARGING_TIME: Final = "total_charging_time"
ENTITY_TOTAL_OPERATION_TIME: Final = "total_operation_time"
ENTITY_VACUUM: Final = "vacuum"
ENTITY_LAWN_MOWER: Final = "lawn_mower"
ENTITY_GARDEN_SIZE: Final = "garden_size"
ENTITY_FIRMWARE: Final = "firmware_version"
ENTITY_SERIAL_NUMBER: Final = "serial_number"
ENTITY_CAMERA: Final = "camera"
ENTITY_CAMERA_PROGRESS: Final = "camera_progress"
ENTITY_FORECAST: Final = "forecast"
ENTITY_BATTERY_CYCLES: Final = "battery_cycles"
ENTITY_AVERAGE_MOW_TIME: Final = "average_mow_time"
ENTITY_WEEKLY_AREA: Final = "weekly_area"
ENTITY_API_ERRORS: Final = "api_errors"

# HTTP Headers
HTTP_HEADER_USER_AGENT: Final = "User-Agent"
HTTP_HEADER_USER_AGENT_DEFAULT: Final = "HA/Indego"
HTTP_HEADER_USER_AGENT_DEFAULTS: Final = [
    "HomeAssistant/Indego",
    "HA/Indego"
]

# Retry configuration
RETRY_AFTER_DEFAULT: Final = 60
API_ERROR_LOG_INTERVAL: Final = 300

# Map configuration
MAP_PROGRESS_LINE_WIDTH: Final = 6
MAP_PROGRESS_LINE_COLOR: Final = "#0000FF"
MAP_UPDATE_INTERVAL: Final = timedelta(minutes=5)

# Event constants
DATA_UPDATED: Final = f"{DOMAIN}_data_updated"
SERVER_DATA_ALERT_INDEX: Final = "alert_index"

# Mower states
STATE_ERROR: Final = "error"
STATE_DOCKED: Final = "docked"
STATE_CHARGING: Final = "charging"
STATE_MOWING: Final = "mowing"
STATE_PAUSED: Final = "paused"
STATE_RETURNING: Final = "returning"

# Command types
COMMAND_MOW: Final = "mow"
COMMAND_PAUSE: Final = "pause"
COMMAND_RETURN: Final = "return"
COMMAND_START: Final = "start"
COMMAND_STOP: Final = "stop"
