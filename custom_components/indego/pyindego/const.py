"""Constants for pyIndego."""
from enum import Enum
from .version import __version__


class Methods(Enum):
    """Enum with HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


DEFAULT_URL = "https://api.indego-cloud.iot.bosch-si.com/api/v1/"
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE = "Content-Type"
COMMANDS = ("mow", "pause", "returnToDock")

DEFAULT_HEADERS = {
    CONTENT_TYPE: CONTENT_TYPE_JSON,
    # We need to change the user-agent!
    # The Microsoft Azure proxy WAF seems to block requests (HTTP 403) for the default 'python-requests' user-agent.
    'User-Agent': "pyIndego (%s)" % __version__
}
DEFAULT_LOOKUP_VALUE = "Not in database."

DEFAULT_CALENDAR = {
    "sel_cal": 1,
    "cals": [
        {
            "cal": 1,
            "days": [
                {
                    "day": 0,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 1,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 2,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 3,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 4,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 5,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 8, "EnMin": 0},
                        {"En": True, "StHr": 20, "StMin": 0, "EnHr": 23, "EnMin": 59},
                    ],
                },
                {
                    "day": 6,
                    "slots": [
                        {"En": True, "StHr": 0, "StMin": 0, "EnHr": 23, "EnMin": 59}
                    ],
                },
            ],
        }
    ],
}

MOWER_STATE_DESCRIPTION_DETAIL = {
    0: "Reading status",
    101: "Mower lifted",
    257: "Charging",
    258: "Docked",
    259: "Docked - Software update",
    260: "Charging",
    261: "Docked",
    262: "Docked - Loading map",
    263: "Docked - Saving map",
    266: "Docked - Leaving dock",
    512: "Mowing - Leaving dock",
    513: "Mowing",
    514: "Mowing - Relocalising",
    515: "Mowing - Loading map",
    516: "Mowing - Learning lawn",
    517: "Mowing - Paused",
    518: "Border cut",
    519: "Idle in lawn",
    520: "Mowing - Learning lawn paused",
    521: "Border cut",
    523: "Mowing - Spot mowing",
    524: "Mowing - Random",
    525: "Mowing - Random complete",
    768: "Returning to Dock",
    769: "Returning to Dock",
    770: "Returning to Dock",
    771: "Returning to Dock - Battery low",
    772: "Returning to dock - Calendar timeslot ended",
    773: "Returning to dock - Battery temp range",
    774: "Returning to dock - requested by user/app",
    775: "Returning to dock - Lawn complete",
    776: "Returning to dock - Relocalising",
    1005: "Connection to dockingstation failed",
    1025: "Diagnostic mode",
    1026: "End of life",
    1027: "Service Requesting Status",
    1038: "Mower immobilized",
    1281: "Software update",
    1537: "Stuck on lawn, help needed",
    64513: "Sleeping",
    99999: "Offline",
}

MOWER_STATE_DESCRIPTION = {
    0: "Docked",
    101: "Docked",
    257: "Docked",
    258: "Docked",
    259: "Docked",
    260: "Docked",
    261: "Docked",
    262: "Docked",
    263: "Docked",
    266: "Mowing",
    512: "Mowing",
    513: "Mowing",
    514: "Mowing",
    515: "Mowing",
    516: "Mowing",
    517: "Mowing",
    518: "Mowing",
    519: "Mowing",
    520: "Mowing",
    521: "Mowing",
    522: "Mowing",
    523: "Mowing",
    524: "Mowing",
    525: "Mowing",
    768: "Mowing",
    769: "Mowing",
    770: "Mowing",
    771: "Mowing",
    772: "Mowing",
    773: "Mowing",
    774: "Mowing",
    775: "Mowing",
    776: "Mowing",
    1005: "Mowing",
    1025: "Diagnostic mode",
    1026: "End of life",
    1027: "Service Requesting Status",
    1038: "Mower immobilized",
    1281: "Software update",
    1537: "Stuck",
    64513: "Docked",
    99999: "Offline",
}

MOWER_MODEL_DESCRIPTION = {
    "3600HA2300": "Indego 1000",
    "3600HA2301": "Indego 1200",
    "3600HA2302": "Indego 1100",
    "3600HA2303": "Indego 13C",
    "3600HA2304": "Indego 10C",
    "3600HB0100": "Indego 350",
    "3600HB0101": "Indego 400",
    "3600HB0102": "Indego S+ 350 1gen",
    "3600HB0103": "Indego S+ 400 1gen",
    "3600HB0105": "Indego S+ 350 2gen",
    "3600HB0106": "Indego S+ 400 2gen",
    "3600HB0302": "Indego S+ 500",
    "3600HB0301": "Indego M+ 700 1gen",
    "3600HB0303": "Indego M+ 700 2gen",
}

MOWING_MODE_DESCRIPTION = {
    "smart": "SmartMowing",
    "calendar": "CalendarMowing"
}
