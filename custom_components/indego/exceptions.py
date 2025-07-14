"""Exceptions for Bosch Indego integration."""
from homeassistant.exceptions import HomeAssistantError


class IndegoError(HomeAssistantError):
    """Base class for Indego errors."""


class IndegoAuthenticationError(IndegoError):
    """Authentication failed."""


class IndegoConnectionError(IndegoError):
    """Unable to connect to Bosch Indego API."""


class IndegoRequestError(IndegoError):
    """Invalid request to Bosch Indego API."""


class IndegoRateLimitError(IndegoError):
    """Rate limit exceeded on Bosch Indego API."""
