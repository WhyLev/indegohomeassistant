"""Helper functions for the Bosch Indego integration."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, Optional

import pytz

from .const import (
    STATE_ERROR,
    STATE_DOCKED,
    STATE_CHARGING,
    STATE_MOWING,
    STATE_PAUSED,
    STATE_RETURNING,
)

_LOGGER = logging.getLogger(__name__)


def convert_bosch_datetime(dt_str: str) -> Optional[datetime]:
    """Convert Bosch datetime string to datetime object."""
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as err:
        _LOGGER.error("Error parsing datetime %s: %s", dt_str, err)
        return None


def get_local_datetime(dt: datetime, timezone_str: str) -> datetime:
    """Convert UTC datetime to local timezone."""
    try:
        local_tz = pytz.timezone(timezone_str)
        return dt.astimezone(local_tz)
    except Exception as err:
        _LOGGER.error("Error converting timezone for %s to %s: %s", dt, timezone_str, err)
        return dt


def calculate_mow_progress(total_size: float, mowed_size: float) -> int:
    """Calculate mowing progress percentage."""
    try:
        if total_size > 0:
            progress = (mowed_size / total_size) * 100
            return min(max(round(progress), 0), 100)
        return 0
    except Exception as err:
        _LOGGER.error("Error calculating mow progress: %s", err)
        return 0


def get_state_description(state_code: int) -> str:
    """Get human readable state description."""
    state_map = {
        0: STATE_DOCKED,
        1: STATE_CHARGING,
        2: STATE_MOWING,
        3: STATE_PAUSED,
        4: STATE_RETURNING,
        5: STATE_ERROR,
    }
    return state_map.get(state_code, "unknown")


def parse_operating_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate operating data."""
    try:
        return {
            "total_operation": int(data.get("runtime", {}).get("total_operation", 0)),
            "total_charging": int(data.get("runtime", {}).get("total_charging", 0)),
            "total_mowing": int(data.get("runtime", {}).get("total_mowing", 0)),
            "battery_percent": int(data.get("battery", {}).get("percent", 0)),
            "battery_cycles": int(data.get("battery", {}).get("cycles", 0)),
            "garden_size": int(data.get("garden", {}).get("size", 0)),
        }
    except (ValueError, AttributeError, KeyError) as err:
        _LOGGER.error("Error parsing operating data: %s", err)
        return {}


def format_duration(minutes: int) -> str:
    """Format duration in minutes to human readable string."""
    try:
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{minutes}m"
    except Exception as err:
        _LOGGER.error("Error formatting duration: %s", err)
        return "unknown"
