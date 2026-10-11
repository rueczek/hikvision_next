"""Platform for binary sensor integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import HikvisionConfigEntry
from .const import CAMERAS_STATUS, EVENTS, EVENTS_COORDINATOR
from .hikvision_device import HikvisionDevice
from .isapi import EventInfo, IPCamera
from .isapi.const import CONNECTION_TYPE_PROXIED, EVENT_IO


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for hikvision events states."""

    device = entry.runtime_data

    entities = []

    # Video Events
    for camera in device.cameras:
        for event in camera.events_info:
            entities.append(EventBinarySensor(device, camera.id, event))

    # General Events
    for event in device.events_info:
        entities.append(EventBinarySensor(device, 0, event))

    # Online status of IP cameras connected to NVR
    if device.capabilities.support_channel_status:
        events_coordinator = device.coordinators.get(EVENTS_COORDINATOR)
        for camera in device.cameras:
            if isinstance(camera, IPCamera) and camera.connection_type == CONNECTION_TYPE_PROXIED:
                entities.append(CameraOnlineBinarySensor(events_coordinator, camera))

    async_add_entities(entities)


class EventBinarySensor(BinarySensorEntity):
    """Event detection sensor."""

    _attr_has_entity_name = True
    _attr_is_on = False

    def __init__(self, device: HikvisionDevice, device_id: int, event: EventInfo) -> None:
        """Initialize."""
        self.entity_id = ENTITY_ID_FORMAT.format(event.unique_id)
        self._attr_unique_id = self.entity_id
        self._attr_device_class = EVENTS[event.id]["device_class"]
        self._attr_device_info = device.hass_device_info(device_id)
        self._attr_entity_registry_enabled_default = not event.disabled

        # For multi-channel devices, add channel suffix to name for clarity
        if device.capabilities.is_multi_channel and event.channel_id > 0:
            base_label = EVENTS[event.id]["label"]
            self._attr_name = f"{base_label} (Ch. {event.channel_id})"
        else:
            self._attr_translation_key = event.id
            if event.id == EVENT_IO:
                self._attr_translation_placeholders = {"io_port_id": event.io_port_id}


class CameraOnlineBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Online status of IP camera connected to NVR."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "camera_online"

    def __init__(self, coordinator, camera: IPCamera) -> None:
        """Initialize."""
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = slugify(f"{device.device_info.serial_no.lower()}_{camera.id}_online")
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        self._attr_device_info = device.hass_device_info(camera.id)
        self.camera = camera

    @property
    def _status(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(CAMERAS_STATUS, {}).get(self.camera.id)

    @property
    def available(self) -> bool:
        """Return True if the status is known."""
        return super().available and self._status is not None

    @property
    def is_on(self) -> bool | None:
        """Return True if the camera is online."""
        status = self._status
        return status["online"] if status else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detection result reported by NVR and camera address."""
        status = self._status or {}
        return {
            "detect_result": status.get("detect_result"),
            "ip_address": self.camera.ip_addr,
        }
