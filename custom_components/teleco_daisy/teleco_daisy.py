from dataclasses import dataclass
from time import sleep
from typing import Literal
import asyncio
import json
import logging
import time

import aiohttp
import requests

TELECO_API_URL = "https://tmate.telecoautomation.com/"

logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)


@dataclass
class DaisyStatus:
    idInstallationDeviceStatusitem: int
    idDevicetypeStatusitemModel: int
    statusitemCode: str
    statusItem: str
    statusValue: str
    lowlevelStatusitem: None


@dataclass
class DaisyInstallation:
    activetimer: str
    firmwareVersion: str
    idInstallation: int
    idInstallationDevice: int
    instCode: str
    instDescription: str
    installationOrder: int
    latitude: float
    longitude: float
    weekend: str  # list[str]
    workdays: str  # list[str]

    client: "TelecoDaisy"

    def status(self):
        return self.client.get_installation_is_active(self)


@dataclass
class DaisyDevice:
    activetimer: str
    deviceCode: str
    deviceIndex: int
    deviceOrder: int
    directOnly: None
    favorite: str
    feedback: str
    idDevicemodel: int
    idDevicetype: int
    idInstallationDevice: int
    label: str
    remoteControlCode: str

    client: "TelecoDaisy"
    installation: DaisyInstallation

    def update_state(self) -> list[DaisyStatus]:
        return self.client.status_device_list(self.installation, self)


@dataclass
class DaisyRoom:
    idInstallationRoom: int
    idRoomtype: int
    roomDescription: str
    roomOrder: int
    deviceList: list["DaisyDevice"]


class TelecoDaisy:
    idAccount: int | None = None
    idSession: str | None = None

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        base_url=TELECO_API_URL,
    ) -> None:
        _LOGGER.debug("Init DAISY TELECO")
        self.headers = {"Accept": "application/json", "Accept-Encoding": "gzip"}
        self.auth = aiohttp.BasicAuth(
            login="teleco", password="tmate20", encoding="utf-8"
        )
        self.base_url = base_url
        self.session = session
        self.email = email
        self.password = password

    async def post(self, request_path, post_data):
        """Send a POST request to the specified URL with the given data.

        Args:
        request_path: The path for the request.
        post_data: The data to be sent with the request.

        Returns:
        The JSON response from the request.

        Raises:
        DaisyTelecoError: If the response status is not 200.

        """
        url = self.base_url + request_path
        _LOGGER.debug("Sending POST request: %s", url)
        async with self.session.post(
            url, data=post_data, headers=self.headers, auth=self.auth
        ) as response:
            if response.status != 200:
                _LOGGER.warning(
                    "Invalid response from Daisy Teleco API: %s", response.status
                )
                # raise DaisyTelecoError(response.status, await response.text())
            _LOGGER.debug("Response: %s", response)

            return await response.json()

    async def login(self, email: str, password: str):
        path = "teleco/services/account-login"
        data = {"email": email, "pwd": password}

        _LOGGER.debug(data)
        result = await self.post(path, json.dumps(data))
        if result["codEsito"] != "S":
            raise Exception(result)
        self.idAccount = result["valRisultato"]["idAccount"]
        self.idSession = result["valRisultato"]["idSession"]
        _LOGGER.debug("Login successful: %s", result)
        return self.idAccount, self.idSession

    async def get_account_installation_list(self) -> list[DaisyInstallation]:
        path = "teleco/services/account-installation-list"
        data = {"idSession": self.idSession, "idAccount": self.idAccount}

        result = await self.post(path, json.dumps(data))
        if result["codEsito"] != "S":
            raise Exception(result)

        installations = []
        for inst in result["valRisultato"]["installationList"]:
            installations += [DaisyInstallation(**inst, client=self)]
        return installations

    async def get_installation_is_active(self, installation: DaisyInstallation):
        path = "teleco/services/tmate20/nodestatus"
        data = {
            "idSession": self.idSession,
            "idInstallation": installation.idInstallation,
        }
        _LOGGER.debug(data)
        result = await self.post(path, json.dumps(data))
        return result["nodeActive"]

    async def get_room_list(self, installation: DaisyInstallation) -> list[DaisyRoom]:
        path = "teleco/services/room-list"
        data = {
            "idSession": self.idSession,
            "idAccount": self.idAccount,
            "idInstallation": installation.idInstallation,
        }

        result = await self.post(path, json.dumps(data))
        if result["codEsito"] != "S":
            raise Exception(result)

        rooms = []
        for room in result["valRisultato"]["roomList"]:
            devices = []
            for device in room.pop("deviceList"):
                # 21 White LED light
                # 23 RGB LED light
                # 22 ZIP cover
                # 24 lamella cover
                if device["idDevicetype"] in (21, 23):
                    devices += [
                        DaisyLight(**device, client=self, installation=installation)
                    ]
                elif device["idDevicetype"] == 22:
                    devices += [
                        DaisyShade(**device, client=self, installation=installation)
                    ]
                elif device["idDevicetype"] == 24:
                    devices += [
                        DaisyCover(**device, client=self, installation=installation)
                    ]
            rooms += [DaisyRoom(**room, deviceList=devices)]
        return rooms

    async def status_device_list(
        self, installation: DaisyInstallation, device: DaisyDevice
    ) -> list[DaisyStatus]:
        path = "teleco/services/status-device-list"
        data = {
            "idSession": self.idSession,
            "idAccount": self.idAccount,
            "idInstallation": installation.idInstallation,
            "idInstallationDevice": device.idInstallationDevice,
        }

        result = await self.post(path, json.dumps(data))
        if result["codEsito"] != "S":
            raise Exception(result)

        return [DaisyStatus(**x) for x in result["valRisultato"]["statusitemList"]]

    async def feed_the_commands(
        self,
        installation: DaisyInstallation,
        commandsList: list[dict],
        ignore_ack=False,
    ):
        path = "teleco/services/tmate20/feedthecommands/"
        data = {
            "commandsList": commandsList,
            "idInstallation": installation.instCode,
            "idSession": self.idSession,
            "idScenario": 0,
            "isScenario": False,
        }

        result = await self.post(path, json.dumps(data))
        if result["MessageID"] != "WS-000":
            raise Exception(result)

        if ignore_ack:
            return {"success": None}

        return self._get_ack(installation, result["ActionReference"])

    async def _get_ack(self, installation: DaisyInstallation, action_reference: str):
        path = "teleco/services/tmate20/getackcommand/"
        data = {
            "id": action_reference,
            "idInstallation": installation.instCode,
            "idSession": self.idSession,
        }

        result = await self.post(path, json.dumps(data))
        assert result["MessageID"] == "WS-300"
        if result["MessageText"] == "RCV":
            sleep(0.5)
            return self._get_ack(installation, action_reference)
        if result["MessageText"] == "PROC":
            return {"success": True}
        return {"success": False}


class DaisyCover(DaisyDevice):
    position: int | None = None
    is_closed: bool | None = None

    def update_state(self):
        stati = super().update_state()
        for status in stati:
            if status.statusitemCode == "OPEN_CLOSE":
                if status.statusValue == "CLOSE":
                    self.is_closed = True
                elif status.statusValue == "OPEN":
                    self.is_closed = False
                else:
                    self.is_closed = None
            if status.statusitemCode == "LEVEL":
                self.position = int(status.statusValue)

    def open_cover(self, percent: Literal["33", "66", "100"] = None):
        if percent == "100":
            return self._open_stop_close("open")
        self._control_cover(percent)

    def stop_cover(self):
        self._open_stop_close("stop")

    def close_cover(self):
        self._open_stop_close("close")

    def _open_stop_close(self, open_stop_close: Literal["open", "stop", "close"]):
        osc_map = {
            "open": ["OPEN", 94, "CH4"],
            "stop": ["STOP", 95, "CH7"],
            "close": ["CLOSE", 96, "CH1"],
        }
        c_param, c_id, c_ll = osc_map[open_stop_close]
        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "commandAction": "OPEN_STOP_CLOSE",
                    "commandId": c_id,
                    "commandParam": c_param,
                    "lowlevelCommand": c_ll,
                }
            ],
        )

    def _control_cover(self, percent: Literal["33", "66", "100"]):
        percent_map = {
            "33": ["LEV2", 97, "CH2"],
            "66": ["LEV3", 98, "CH3"],
            "100": ["LEV4", 99, "CH4"],
        }
        c_param, c_id, c_ll = percent_map[percent]

        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "commandAction": "LEVEL",
                    "commandId": c_id,
                    "commandParam": c_param,
                    "lowlevelCommand": c_ll,
                }
            ],
        )


class DaisyShade(DaisyDevice):
    position: int | None = None
    is_closed: bool | None = None

    def update_state(self):
        stati = super().update_state()
        for status in stati:
            if status.statusitemCode == "OPEN_CLOSE":
                if status.statusValue == "CLOSE":
                    self.is_closed = True
                elif status.statusValue == "OPEN":
                    self.is_closed = False
                else:
                    self.is_closed = None
            if status.statusitemCode == "LEVEL":
                self.position = int(status.statusValue)

    def open_cover(self, percent: Literal["33", "66", "100"] = None):
        if percent == "100":
            return self._open_stop_close("open")
        self._control_cover(percent)

    def stop_cover(self):
        self._open_stop_close("stop")

    def close_cover(self):
        self._open_stop_close("close")

    def _open_stop_close(self, open_stop_close: Literal["open", "stop", "close"]):
        osc_map = {
            "open": ["OPEN", 75, "CH5"],
            "stop": ["STOP", 76, "CH7"],
            "close": ["CLOSE", 77, "CH8"],
        }

        c_param, c_id, c_ll = osc_map[open_stop_close]
        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "commandAction": "OPEN_STOP_CLOSE",
                    "commandId": c_id,
                    "commandParam": c_param,
                    "lowlevelCommand": c_ll,
                }
            ],
        )

    def _control_cover(self, percent: Literal["33", "66", "100"]):
        percent_map = {
            "33": ["LEV2", 97, "CH2"],
            "66": ["LEV3", 98, "CH3"],
            "100": ["LEV4", 99, "CH4"],
        }
        c_param, c_id, c_ll = percent_map[percent]

        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "commandAction": "LEVEL",
                    "commandId": c_id,
                    "commandParam": c_param,
                    "lowlevelCommand": c_ll,
                }
            ],
        )


class DaisyLight(DaisyDevice):
    is_on: bool | None = None
    brightness: int | None = None  # from 0 to 100
    rgb: tuple[int, int, int] | None = None

    def update_state(self):
        stati = super().update_state()
        for status in stati:
            if status.statusitemCode == "POWER":
                self.is_on = status.statusValue == "ON"
            if status.statusitemCode == "COLOR":
                val = status.statusValue
                self.brightness = int(val[1:4])
                self.rgb = (int(val[5:8]), int(val[9:12]), int(val[13:16]))

    def set_rgb_and_brightness(
        self, rgb: tuple[int, int, int] = None, brightness: int = None
    ):
        if brightness is None:
            brightness = self.brightness or 0
        if brightness < 0 or brightness > 100:
            raise ValueError("Brightness must be between 0 and 100")
        if rgb is None:
            rgb = self.rgb or (255, 255, 255)
        if any((c < 0 or c > 255) for c in rgb):
            raise ValueError("Color must be between 0 and 255")

        v = f"A{brightness:03d}R{rgb[0]:03d}G{rgb[1]:03d}B{rgb[2]:03d}"

        if self.idDevicetype == 21:
            commandId = 146
            lowlevelCommand = "CH1"
        elif self.idDevicetype == 23:
            commandId = 137
            lowlevelCommand = None

        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "commandAction": "COLOR",
                    "commandId": 137,
                    "commandParam": v,
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                }
            ],
        )

    def turn_on(self):
        if self.idDevicetype == 21:
            commandId = 146
            lowlevelCommand = "CH1"
        elif self.idDevicetype == 23:
            commandId = 138  # maybe incorrect
            lowlevelCommand = None

        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "commandAction": "POWER",
                    "commandId": commandId,
                    "commandParam": "ON",
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "lowlevelCommand": lowlevelCommand,
                }
            ],
        )

    def turn_off(self):
        if self.idDevicetype == 21:
            commandId = 147
            lowlevelCommand = "CH8"
        elif self.idDevicetype == 23:
            commandId = 138
            lowlevelCommand = None

        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[
                {
                    "commandAction": "POWER",
                    "commandId": commandId,
                    "commandParam": "OFF",
                    "deviceCode": str(self.deviceIndex),
                    "idInstallationDevice": self.idInstallationDevice,
                    "lowlevelCommand": lowlevelCommand,
                }
            ],
        )
