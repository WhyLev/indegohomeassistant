"""OAuth2 implementation for Indego."""
from typing import cast

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


class IndegoOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """Indego OAuth2 implementation."""

    @property
    def name(self) -> str:
        """Return name of implementation."""
        return "Bosch Indego"

    @property
    def redirect_uri(self) -> str:
        """Return the redirect uri."""
        return "com.bosch.indegoconnect://login"


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Return auth implementation."""
    return IndegoOAuth2Implementation(
        hass,
        auth_domain,
        credential.client_id,
        None,  # Bosch OAuth requires no client secret
        AuthorizationServer(
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        ),
    )
