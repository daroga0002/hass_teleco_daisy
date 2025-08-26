from __future__ import annotations

import logging
from typing import Any
from .const import DOMAIN

from homeassistant import config_entries, core

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    LightEntity,
    ColorMode,
    LightEntityDescription,
    ATTR_RGB_COLOR,
)
from .teleco_daisy import DaisyLight
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    hub = hass.data[DOMAIN][config_entry.entry_id]

    if config_entry.options:
        hub.update(config_entry.options)

    async_add_entities(TelecoDaisyLight(light) for light in hub.lights)


class TelecoDaisyLight(LightEntity):
    entity_description = LightEntityDescription(
        key="teleco_daisy_light", has_entity_name=True, name=None
    )

    def __init__(self, light: DaisyLight) -> None:
        self._light = light
        self._name = light.label
        self._attr_is_on = light.is_on
        self._attr_brightness = (
            round(light.brightness * 2.55) if light.brightness else 50
        )
        self._attr_rgb_color = light.rgb or (255, 255, 255)

        self._attr_unique_id = str(self._light.idInstallationDevice)
        self._attr_name = self._light.label
        self._attr_color_mode = ColorMode.RGB
        self._attr_supported_color_modes = {ColorMode.RGB}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name,
            manufacturer="Teleco Automation",
        )

    @property
    def name(self) -> str:
        return self._name

    def turn_on(self, **kwargs: Any) -> None:
        new_rgb = kwargs.get(ATTR_RGB_COLOR)
        if new_rgb:
            self._attr_rgb_color = (int(new_rgb[0]), int(new_rgb[1]), int(new_rgb[2]))

        new_bright = kwargs.get(ATTR_BRIGHTNESS)
        if new_bright:
            self._attr_brightness = int(new_bright)

        self._light.set_rgb_and_brightness(
            rgb=self._attr_rgb_color,
            brightness=round((self._attr_brightness / 255) * 100),
        )
        self.update()

    def turn_off(self, **kwargs: Any) -> None:
        self._light.turn_off()
        self.update()

    def update(self) -> None:
        self._light.update_state()
        self._attr_is_on = self._light.is_on
        if self._light.brightness:
            self._attr_brightness = round(self._light.brightness * 2.55)
        if self._light.rgb:
            self._attr_rgb_color = self._light.rgb
