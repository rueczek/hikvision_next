"""Tests for 'Notify Surveillance Center' switches and cameras online status."""

import pytest
import respx
import xmltodict
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.conftest import TEST_HOST

VMD_1_TRIGGER = {
    "EventTrigger": {
        "@version": "2.0",
        "@xmlns": "http://www.isapi.org/ver20/XMLSchema",
        "id": "VMD-1",
        "eventType": "VMD",
        "dynVideoInputChannelID": "1",
        "EventTriggerNotificationList": {
            "@version": "2.0",
            "@xmlns": "http://www.isapi.org/ver20/XMLSchema",
            "EventTriggerNotification": {"id": "record-1", "notificationMethod": "record", "dynVideoInputID": "1"},
        },
    }
}


@pytest.mark.parametrize("init_integration", ["HWN-4104MH-4P"], indirect=True)
async def test_notify_center_switch_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test notify switches exist and event entities without 'center' are disabled."""

    for camera_id in range(1, 5):
        assert (switch := hass.states.get(f"switch.xxx_{camera_id}_motiondetection_notify_center"))
        assert switch.state == STATE_OFF

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("binary_sensor.xxx_1_motiondetection")
    assert entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.parametrize("init_integration", ["HWN-4104MH-4P"], indirect=True)
async def test_notify_center_switch_turn_on(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test turning on notify switch adds 'center' action and enables event entities."""

    url = f"{TEST_HOST}/ISAPI/Event/triggers/VMD-1"
    respx.get(url).respond(text=xmltodict.unparse(VMD_1_TRIGGER))
    put_route = respx.put(url).respond()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.xxx_1_motiondetection_notify_center"},
        blocking=True,
    )

    assert put_route.called
    payload = xmltodict.parse(put_route.calls.last.request.content)
    notifications = payload["EventTrigger"]["EventTriggerNotificationList"]["EventTriggerNotification"]
    assert [n["notificationMethod"] for n in notifications] == ["record", "center"]
    assert payload["EventTrigger"]["dynVideoInputChannelID"] == "1"

    entity_registry = er.async_get(hass)
    for entity_id in ["binary_sensor.xxx_1_motiondetection", "switch.xxx_1_motiondetection"]:
        assert entity_registry.async_get(entity_id).disabled_by is None
    # other cameras are untouched
    assert entity_registry.async_get("binary_sensor.xxx_2_motiondetection").disabled


@pytest.mark.parametrize("init_integration", ["HWN-4104MH-4P"], indirect=True)
async def test_notify_center_switch_turn_off(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test turning off notify switch removes only 'center' action."""

    trigger = VMD_1_TRIGGER["EventTrigger"]
    with_center = {
        "EventTrigger": {
            **trigger,
            "EventTriggerNotificationList": {
                "EventTriggerNotification": [
                    trigger["EventTriggerNotificationList"]["EventTriggerNotification"],
                    {"id": "center", "notificationMethod": "center", "notificationRecurrence": "beginning"},
                ]
            },
        }
    }
    url = f"{TEST_HOST}/ISAPI/Event/triggers/VMD-1"
    respx.get(url).respond(text=xmltodict.unparse(with_center))
    put_route = respx.put(url).respond()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.xxx_1_motiondetection_notify_center"},
        blocking=True,
    )

    payload = xmltodict.parse(put_route.calls.last.request.content)
    notification = payload["EventTrigger"]["EventTriggerNotificationList"]["EventTriggerNotification"]
    assert notification["notificationMethod"] == "record"


@pytest.mark.parametrize("init_integration", ["HWN-4104MH-4P"], indirect=True)
async def test_camera_online_sensor(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test online status of cameras connected to NVR."""

    for camera_id, state in [(1, STATE_ON), (2, STATE_ON), (3, STATE_ON), (4, STATE_OFF)]:
        assert (sensor := hass.states.get(f"binary_sensor.xxx_{camera_id}_online"))
        assert sensor.state == state

    sensor = hass.states.get("binary_sensor.xxx_4_online")
    assert sensor.attributes["detect_result"] == "netUnreachable"
    assert sensor.attributes["ip_address"] == "1.0.0.241"
