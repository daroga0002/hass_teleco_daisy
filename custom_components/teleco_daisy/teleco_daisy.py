import json
from dataclasses import dataclass
from enum import Enum
from time import sleep
from typing import Literal, Optional, List, Tuple, Dict, Any, Union, ClassVar

import requests

BASE_URL = "https://tmate.telecoautomation.com/"


@dataclass
class DaisyStatus:
    idInstallationDeviceStatusitem: int
    idDevicetypeStatusitemModel: int
    statusitemCode: str
    statusItem: str
    statusValue: str
    lowlevelStatusitem: None


@dataclass
class DaisyRoom:
    roomOrder: int
    deviceList: List["DaisyDevice"]
    idInstallationRoom: int
    idRoomtype: int
    roomDescription: str

class DeviceType(Enum):
    WHITE_LED = 21
    COVER_TYPE_1 = 22 # ZIP
    RGB_LED = 23
    COVER_TYPE_2 = 24 # Pergola


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

    def status(self) -> bool:
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
    installation: "DaisyInstallation"

    def update_state(self) -> List[DaisyStatus]:
        return self.client.status_device_list(self.installation, self)
    
    def send_command(self, action: str, param: str, command_id: int, 
                    low_level_command: Optional[str] = None) -> Dict[str, Any]:
        command = {
            "deviceCode": str(self.deviceIndex),
            "idInstallationDevice": self.idInstallationDevice,
            "commandAction": action,
            "commandId": command_id,
            "commandParam": param,
        }
        
        if low_level_command:
            command["lowlevelCommand"] = low_level_command
            
        return self.client.feed_the_commands(
            installation=self.installation,
            commandsList=[command],
        )


class DaisyCover(DaisyDevice):
    position: Optional[int] = None
    is_closed: Optional[bool] = None
    
    # Command mappings for different cover types
    COMMAND_MAPS: ClassVar[Dict[int, Dict[str, List[Any]]]] = {
        DeviceType.COVER_TYPE_1.value: {
            "open": ["OPEN", 75, "CH5"],
            "stop": ["STOP", 76, "CH7"],
            "close": ["CLOSE", 77, "CH8"],
        },
        DeviceType.COVER_TYPE_2.value: {
            "open": ["OPEN", 94, "CH4"],
            "stop": ["STOP", 95, "CH7"],
            "close": ["CLOSE", 96, "CH1"],
        }
    }
    
    PERCENT_MAP: ClassVar[Dict[str, List[Any]]] = {
        "33": ["LEV2", 97, "CH2"],
        "66": ["LEV3", 98, "CH3"],
        "100": ["LEV4", 99, "CH4"],
    }

    def update_state(self) -> None:
        stati = super().update_state()
        for status in stati:
            if status.statusitemCode == "OPEN_CLOSE":
                self.is_closed = {
                    "CLOSE": True,
                    "OPEN": False
                }.get(status.statusValue, None)
            elif status.statusitemCode == "LEVEL":
                self.position = int(status.statusValue)

    def open_cover(self, percent: Optional[Literal["33", "66", "100"]] = None) -> Dict[str, Any]:
        if percent == "100" or percent is None:
            return self._open_stop_close("open")
        return self._control_cover(percent)

    def stop_cover(self) -> Dict[str, Any]:
        return self._open_stop_close("stop")

    def close_cover(self) -> Dict[str, Any]:
        return self._open_stop_close("close")

    def _open_stop_close(self, action: Literal["open", "stop", "close"]) -> Dict[str, Any]:
        command_map = self.COMMAND_MAPS.get(self.idDevicetype, {})
        if not command_map:
            raise ValueError(f"Unsupported device type: {self.idDevicetype}")
            
        c_param, c_id, c_ll = command_map[action]
        return self.send_command(
            action="OPEN_STOP_CLOSE",
            param=c_param,
            command_id=c_id,
            low_level_command=c_ll
        )

    def _control_cover(self, percent: Literal["33", "66", "100"]) -> Dict[str, Any]:
        c_param, c_id, c_ll = self.PERCENT_MAP[percent]
        return self.send_command(
            action="LEVEL",
            param=c_param,
            command_id=c_id,
            low_level_command=c_ll
        )


class DaisyLight(DaisyDevice):
    is_on: Optional[bool] = None
    brightness: Optional[int] = None  # from 0 to 100
    rgb: Optional[Tuple[int, int, int]] = None
    
    # Command configurations for different light types
    DEVICE_CONFIGS: ClassVar[Dict[int, Dict[str, Dict[str, Any]]]] = {
        DeviceType.WHITE_LED.value: {
            "power_on": {"id": 40, "ll": "CH1"},
            "power_off": {"id": 41, "ll": "CH8"},
            "color": {"id": 146, "ll": "CH1"}
        },
        DeviceType.RGB_LED.value: {
            "power_on": {"id": 138, "ll": None},
            "power_off": {"id": 138, "ll": None},
            "color": {"id": 137, "ll": None}
        }
    }

    def update_state(self) -> None:
        stati = super().update_state()
        for status in stati:
            if status.statusitemCode == "POWER":
                self.is_on = status.statusValue == "ON"
            elif status.statusitemCode == "COLOR":
                val = status.statusValue
                self.brightness = int(val[1:4])
                self.rgb = (int(val[5:8]), int(val[9:12]), int(val[13:16]))

    def set_rgb_and_brightness(
        self, rgb: Optional[Tuple[int, int, int]] = None, brightness: Optional[int] = None
    ) -> Dict[str, Any]:
        brightness = brightness if brightness is not None else (self.brightness or 0)
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
            
        rgb = rgb if rgb is not None else (self.rgb or (255, 255, 255))
        if any(not 0 <= c <= 255 for c in rgb):
            raise ValueError("Color components must be between 0 and 255")

        value = f"A{brightness:03d}R{rgb[0]:03d}G{rgb[1]:03d}B{rgb[2]:03d}"
        
        config = self.DEVICE_CONFIGS.get(self.idDevicetype, {}).get("color")
        if not config:
            raise ValueError(f"Unsupported device type: {self.idDevicetype}")
            
        return self.send_command(
            action="COLOR",
            param=value,
            command_id=config["id"],
            low_level_command=config["ll"]
        )

    def turn_on(self) -> Dict[str, Any]:
        config = self.DEVICE_CONFIGS.get(self.idDevicetype, {}).get("power_on")
        if not config:
            raise ValueError(f"Unsupported device type: {self.idDevicetype}")
            
        return self.send_command(
            action="POWER",
            param="ON",
            command_id=config["id"],
            low_level_command=config["ll"]
        )

    def turn_off(self) -> Dict[str, Any]:
        config = self.DEVICE_CONFIGS.get(self.idDevicetype, {}).get("power_off")
        if not config:
            raise ValueError(f"Unsupported device type: {self.idDevicetype}")
            
        return self.send_command(
            action="POWER",
            param="OFF",
            command_id=config["id"],
            low_level_command=config["ll"]
        )


class TelecoDaisy:
    idAccount: Optional[int] = None
    idSession: Optional[str] = None

    def __init__(self, email: str, password: str):
        self.s = requests.Session()
        self.s.auth = ("teleco", "tmate20")
        self.email = email
        self.password = password

    def login(self) -> None:
        login = self.s.post(
            BASE_URL + "teleco/services/account-login",
            json={"email": self.email, "pwd": self.password},
        )
        login_json = login.json()
        if login_json["codEsito"] != "S":
            raise Exception(f"Login failed: {login_json}")

        self.idAccount = login_json["valRisultato"]["idAccount"]
        self.idSession = login_json["valRisultato"]["idSession"]

    def get_account_installation_list(self) -> List[DaisyInstallation]:
        req = self.s.post(
            BASE_URL + "teleco/services/account-installation-list",
            json={"idSession": self.idSession, "idAccount": self.idAccount},
        )
        req_json = req.json()
        if req_json["codEsito"] != "S":
            raise Exception(f"Failed to get installations: {req_json}")

        return [DaisyInstallation(**inst, client=self) 
                for inst in req_json["valRisultato"]["installationList"]]

    def get_installation_is_active(self, installation: DaisyInstallation) -> bool:
        req = self.s.post(
            BASE_URL + "teleco/services/tmate20/nodestatus",
            json={
                "idSession": self.idSession,
                "idInstallation": installation.idInstallation,
            },
        )
        req_json = req.json()
        return req_json["nodeActive"]

    def get_room_list(self, installation: DaisyInstallation) -> List[DaisyRoom]:
        req = self.s.post(
            BASE_URL + "teleco/services/room-list",
            json={
                "idSession": self.idSession,
                "idAccount": self.idAccount,
                "idInstallation": installation.idInstallation,
            },
        )
        req_json = req.json()
        if req_json["codEsito"] != "S":
            raise Exception(f"Failed to get rooms: {req_json}")

        rooms = []
        for room_data in req_json["valRisultato"]["roomList"]:
            devices = []
            device_list = room_data.pop("deviceList")
            
            for device in device_list:
                device_type = device["idDevicetype"]
                
                if device_type in (DeviceType.WHITE_LED.value, DeviceType.RGB_LED.value):
                    devices.append(
                        DaisyLight(**device, client=self, installation=installation)
                    )
                elif device_type in (DeviceType.COVER_TYPE_1.value, DeviceType.COVER_TYPE_2.value):
                    devices.append(
                        DaisyCover(**device, client=self, installation=installation)
                    )
                    
            rooms.append(DaisyRoom(**room_data, deviceList=devices))
            
        return rooms

    def status_device_list(
        self, installation: DaisyInstallation, device: DaisyDevice
    ) -> List[DaisyStatus]:
        req = self.s.post(
            BASE_URL + "teleco/services/status-device-list",
            json={
                "idSession": self.idSession,
                "idAccount": self.idAccount,
                "idInstallation": installation.idInstallation,
                "idInstallationDevice": device.idInstallationDevice,
            },
        )
        req_json = req.json()
        if req_json["codEsito"] != "S":
            raise Exception(f"Failed to get device status: {req_json}")

        return [DaisyStatus(**x) for x in req_json["valRisultato"]["statusitemList"]]

    def feed_the_commands(
        self,
        installation: DaisyInstallation,
        commandsList: List[Dict[str, Any]],
        ignore_ack: bool = False,
    ) -> Dict[str, Any]:
        req = self.s.post(
            BASE_URL + "teleco/services/tmate20/feedthecommands/",
            json={
                "commandsList": commandsList,
                "idInstallation": installation.instCode,
                "idSession": self.idSession,
                "idScenario": 0,
                "isScenario": False,
            },
        )
        req_json = req.json()
        if req_json["MessageID"] != "WS-000":
            raise Exception(f"Command failed: {req_json}")

        if ignore_ack:
            return {"success": None}

        return self._get_ack(installation, req_json["ActionReference"])

    def _get_ack(self, installation: DaisyInstallation, action_reference: str) -> Dict[str, bool]:
        req = self.s.post(
            BASE_URL + "teleco/services/tmate20/getackcommand/",
            json={
                "id": action_reference,
                "idInstallation": installation.instCode,
                "idSession": self.idSession,
            },
        )
        req_json = req.json()
        
        if req_json["MessageID"] != "WS-300":
            raise Exception(f"Invalid acknowledgment response: {req_json}")
            
        if req_json["MessageText"] == "RCV":
            sleep(0.5)
            return self._get_ack(installation, action_reference)
            
        return {"success": req_json["MessageText"] == "PROC"}
