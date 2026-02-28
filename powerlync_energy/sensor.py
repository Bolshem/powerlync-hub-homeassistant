"""Sensor platform for Powerlync Energy Monitor - polls device directly."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_start

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)
HOMEKIT_DOMAIN = "homekit_controller-devices"

AID = 1
CHARACTERISTICS = [
    (AID, 21),  # Instantaneous Demand
    (AID, 22),  # Current Summation Delivered
    (AID, 23),  # Current Summation Received
    (AID, 24),  # Local Instantaneous Demand
    (AID, 25),  # Local Summation Delivered
    (AID, 27),  # Meter Time
]


def _parse_kw_to_watts(value) -> float | None:
    try:
        match = re.search(r"([\d.]+)\s*kW", str(value))
        if match:
            return round(float(match.group(1)) * 1000, 1)
    except (ValueError, TypeError):
        pass
    return None

def _parse_kwh(value) -> float | None:
    try:
        match = re.search(r"([\d.]+)\s*kWh", str(value))
        if match:
            return round(float(match.group(1)), 3)
    except (ValueError, TypeError):
        pass
    return None

def _parse_float(value) -> float | None:
    try:
        return round(float(value), 1)
    except (ValueError, TypeError):
        return None

def _parse_timestamp(value) -> datetime | None:
    try:
        ts = int(value)
        if ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    return None


@dataclass
class PowerlyncSensorDescription(SensorEntityDescription):
    iid: int = 0
    value_parser: Any = None


SENSOR_DESCRIPTIONS: list[PowerlyncSensorDescription] = [
    PowerlyncSensorDescription(
        key="instantaneous_demand",
        name="Instantaneous Demand",
        iid=21,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_parser=_parse_kw_to_watts,
    ),
    PowerlyncSensorDescription(
        key="total_energy_consumed",
        name="Total Energy Consumed",
        iid=22,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-import",
        value_parser=_parse_kwh,
    ),
    PowerlyncSensorDescription(
        key="total_energy_received",
        name="Total Energy Received (Solar)",
        iid=23,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power",
        value_parser=_parse_kwh,
    ),
    PowerlyncSensorDescription(
        key="local_instantaneous_demand",
        name="Local Instantaneous Demand",
        iid=24,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-outline",
        value_parser=_parse_float,
    ),
    PowerlyncSensorDescription(
        key="local_energy_delivered",
        name="Local Energy Delivered",
        iid=25,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:home-lightning-bolt",
        value_parser=_parse_float,
    ),
    PowerlyncSensorDescription(
        key="meter_last_updated",
        name="Meter Last Updated",
        iid=27,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check",
        value_parser=_parse_timestamp,
    ),
]

IID_TO_DESC = {desc.iid: desc for desc in SENSOR_DESCRIPTIONS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Powerlync Energy sensors."""
    entities = [PowerlyncSensor(hass, desc) for desc in SENSOR_DESCRIPTIONS]
    iid_to_entity = {e.entity_description.iid: e for e in entities}
    async_add_entities(entities, True)

    async def _poll(_now=None):
        hk_device = next(iter(hass.data.get(HOMEKIT_DOMAIN, {}).values()), None)
        if hk_device is None:
            _LOGGER.warning("Powerlync: HKDevice not found")
            return
        try:
            results = await hk_device.pairing.get_characteristics(CHARACTERISTICS)
            for (aid, iid), char_data in results.items():
                if iid in iid_to_entity:
                    iid_to_entity[iid].update_value(char_data.get("value"))
        except Exception as err:
            _LOGGER.warning("Powerlync: poll failed: %s", err)

    async def _on_start(_event=None):
        await _poll()
        entry.async_on_unload(
            async_track_time_interval(hass, _poll, SCAN_INTERVAL)
        )

    entry.async_on_unload(async_at_start(hass, _on_start))


class PowerlyncSensor(SensorEntity):
    """Sensor for a Powerlync energy characteristic."""

    entity_description: PowerlyncSensorDescription

    def __init__(self, hass: HomeAssistant, description: PowerlyncSensorDescription) -> None:
        self.hass = hass
        self.entity_description = description
        self._attr_unique_id = f"powerlync_energy_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "powerlync-001")},
            name="Powerlync Energy Monitor",
            manufacturer="Powerley",
            model="Powerlync",
        )
        self._attr_native_value = None

    @callback
    def update_value(self, raw: Any) -> None:
        """Update sensor value."""
        if raw is None:
            self._attr_native_value = None
        else:
            try:
                self._attr_native_value = self.entity_description.value_parser(raw)
            except Exception as err:
                _LOGGER.warning("Failed to parse %s=%r: %s", self.entity_description.key, raw, err)
                self._attr_native_value = None
        self.async_write_ha_state()
