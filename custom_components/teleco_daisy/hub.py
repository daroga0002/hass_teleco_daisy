"""Hub module for Teleco Daisy integration."""

from __future__ import annotations

import logging
from re import L
from typing import List

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .teleco_daisy import (
    DaisyCover,
    DaisyLight,
    TelecoDaisy,
    DaisyRoom,
    DaisyInstallation,
)

_LOGGER = logging.getLogger(__name__)


class DaisyHub:
    """Hub to interface with Teleco Daisy API."""

    manufacturer = "Teleco Automation"

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        """Initialize the Teleco Daisy Hub."""
        self._hass = hass
        self._name = "Teleco DaisyHub"
        self._id = "teleco_daisyhub"
        self.online = False
        self.lights: List[DaisyLight] = []
        self.covers: List[DaisyCover] = []

        session = async_get_clientsession(hass)
        self.api = TelecoDaisy(session, email, password)

    async def login(self):
        """Login to the Teleco Daisy API."""
        try:
            await self.api.login(self.api.email, self.api.password)
            self.online = True
            return True
        except Exception as ex:
            _LOGGER.error("Failed to login to Teleco Daisy API: %s", ex)
            self.online = False
            return False

    async def async_setup(self) -> bool:
        """Set up the Teleco Daisy Hub."""
        try:
            await self.api.login(self.api.email, self.api.password)
            self.online = True
            return True
        except Exception as ex:
            _LOGGER.error("Failed to setup Teleco Daisy hub: %s", ex)
            self.online = False
            return False

    async def async_fetch_entities(self):
        """Fetch all entities from the Teleco Daisy API."""
        self.lights = []
        self.covers = []

        try:
            installations = await self.api.get_account_installation_list()

            for installation in installations:
                # The error is likely in the get_room_list call or its result handling
                rooms = await self.api.get_room_list(installation)

                _LOGGER.debug(rooms)

                for room in rooms:
                    if not hasattr(room, "deviceList"):
                        # Use str() to ensure safe string conversion for any object
                        _LOGGER.warning(
                            "Room does not have deviceList attribute: %s",
                            str(vars(room)),
                        )
                        continue

                    for device in room.deviceList:
                        # Add debug logging to identify potential type issues
                        _LOGGER.debug(
                            "Processing device: %s (type: %s)",
                            getattr(device, "label", "unknown"),
                            type(device).__name__,
                        )

                        if isinstance(device, DaisyLight):
                            self.lights.append(device)
                        elif isinstance(device, DaisyCover):
                            self.covers.append(device)
                        else:
                            # Log unhandled device types to help debugging
                            _LOGGER.debug(
                                "Unhandled device type: %s", type(device).__name__
                            )

            self.online = True
        except Exception as ex:
            _LOGGER.error("Error fetching entities: %s", ex)
            # Add more detailed error information for debugging
            import traceback

            _LOGGER.debug("Exception traceback: %s", traceback.format_exc())
            self.online = False

    @property
    def hub_id(self) -> str:
        """Return the hub ID."""
        return self._id

    async def test_connection(self) -> bool:
        """Test connection to Teleco Daisy API."""
        try:
            await self.api.login(self.api.email, self.api.password)
            return True
        except Exception as ex:
            _LOGGER.error("Connection test failed: %s", ex)
            return False
