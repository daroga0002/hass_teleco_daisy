from __future__ import annotations
from homeassistant.core import HomeAssistant

from .teleco_daisy import TelecoDaisy, DaisyLight, DaisyCover


class DaisyHub(TelecoDaisy):
    manufacturer = "Teleco Automation"
    lights = []
    covers = []

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        super().__init__(email, password)

        self._hass = hass
        self._name = "Teleco DaisyHub"
        self._id = "Teleco DaisyHub".lower()

        self.online = True

    def fetch_entities(self):
        self.lights = []
        self.covers = []
        for installation in self.get_account_installation_list():
            for room in self.get_room_list(installation):
                for device in room.deviceList:
                    if isinstance(device, DaisyLight):
                        self.lights += [device]
                    elif isinstance(device, DaisyCover):
                        self.covers += [device]

    @property
    def hub_id(self) -> str:
        return self._id

    async def test_connection(self) -> bool:
        # TODO
        return True
