"""Data models for Bosch Indego integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

from homeassistant.const import (
    PERCENTAGE,
    TEMP_CELSIUS,
    TIME_MINUTES,
    AREA_SQUARE_METERS,
)


@dataclass
class Battery:
    """Battery information."""
    percent: int
    voltage: float
    cycles: int
    discharge: float
    ambient_temp: float
    battery_temp: float
    percent_adjusted: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Battery:
        """Create from dictionary."""
        return cls(
            percent=data.get("percent", 0),
            voltage=data.get("voltage", 0.0),
            cycles=data.get("cycles", 0),
            discharge=data.get("discharge", 0.0),
            ambient_temp=data.get("ambient_temp", 0.0),
            battery_temp=data.get("battery_temp", 0.0),
            percent_adjusted=data.get("percent_adjusted")
        )


@dataclass
class Runtime:
    """Runtime statistics."""
    total_operation: int
    total_charging: int
    total_mowing: int
    total_docked: int
    total_mowing_sessions: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Runtime:
        """Create from dictionary."""
        return cls(
            total_operation=data.get("total_operation", 0),
            total_charging=data.get("total_charging", 0),
            total_mowing=data.get("total_mowing", 0),
            total_docked=data.get("total_docked", 0),
            total_mowing_sessions=data.get("total_mowing_sessions", 0)
        )


@dataclass
class Alert:
    """Alert information."""
    alert_id: str
    error_code: int
    message: str
    timestamp: datetime
    read: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Alert:
        """Create from dictionary."""
        return cls(
            alert_id=data.get("alert_id", ""),
            error_code=data.get("error_code", 0),
            message=data.get("message", ""),
            timestamp=datetime.fromisoformat(data.get("timestamp", "")),
            read=data.get("read", False)
        )


@dataclass
class CalendarSlot:
    """Calendar slot information."""
    start: datetime
    end: datetime
    duration: int
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CalendarSlot:
        """Create from dictionary."""
        return cls(
            start=datetime.fromisoformat(data.get("start", "")),
            end=datetime.fromisoformat(data.get("end", "")),
            duration=data.get("duration", 0)
        )


@dataclass
class CalendarDay:
    """Calendar day information."""
    day: int
    slots: List[CalendarSlot]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CalendarDay:
        """Create from dictionary."""
        return cls(
            day=data.get("day", 0),
            slots=[CalendarSlot.from_dict(slot) for slot in data.get("slots", [])]
        )


@dataclass
class Calendar:
    """Calendar information."""
    days: List[CalendarDay]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Calendar:
        """Create from dictionary."""
        return cls(
            days=[CalendarDay.from_dict(day) for day in data.get("days", [])]
        )


@dataclass
class State:
    """Mower state information."""
    state: int
    map_update_available: bool
    mowed: int
    mow_mode: int
    error: Optional[int] = None
    error_message: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> State:
        """Create from dictionary."""
        return cls(
            state=data.get("state", 0),
            map_update_available=data.get("map_update_available", False),
            mowed=data.get("mowed", 0),
            mow_mode=data.get("mow_mode", 0),
            error=data.get("error"),
            error_message=data.get("error_message")
        )


@dataclass
class Config:
    """Mower configuration."""
    serial: str
    model: str
    name: str
    garden_size: int
    firmware: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        """Create from dictionary."""
        return cls(
            serial=data.get("serial", ""),
            model=data.get("model", ""),
            name=data.get("name", ""),
            garden_size=data.get("garden_size", 0),
            firmware=data.get("firmware", "")
        )


@dataclass
class OperatingData:
    """Operating data information."""
    hmiKeys: Optional[Dict[str, Any]]
    battery: Battery
    garden: Dict[str, Any]
    runtime: Runtime
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OperatingData:
        """Create from dictionary."""
        return cls(
            hmiKeys=data.get("hmiKeys"),
            battery=Battery.from_dict(data.get("battery", {})),
            garden=data.get("garden", {}),
            runtime=Runtime.from_dict(data.get("runtime", {}))
        )
