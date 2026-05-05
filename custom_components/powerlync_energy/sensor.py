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
    (AID, 26),  # Local Time (UTC)
    (AID, 27),  # Meter Time (UTC)
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
    # If True, a parsed value of 0 is treated as a failed read and the last
    # known good value is retained. Useful for cumulative energy sensors where
    # 0 is never a valid reading once the meter has accumulated any usage.
    retain_on_zero: bool = False


SENSOR_DESCRIPTIONS: list[PowerlyncSensorDescription] = [
    PowerlyncSensorDescription(
        key="instantaneous_demand",
        name="Grid Instantaneous Demand",
        iid=21,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_parser=_parse_kw_to_watts,
        retain_on_zero=False,  # 0W is a valid reading (nothing running)
    ),
    PowerlyncSensorDescription(
        key="total_energy_consumed",
        name="Grid Total Energy Consumed",
        iid=22,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-import",
        value_parser=_parse_kwh,
        retain_on_zero=True,  # meter reading of 0 means the read failed
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
        retain_on_zero=True,
    ),
    PowerlyncSensorDescription(
        key="local_instantaneous_demand",
        name="Plug Instantaneous Demand",
        iid=24,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-outline",
        value_parser=_parse_float,
        retain_on_zero=False,
    ),
    PowerlyncSensorDescription(
        key="local_energy_delivered",
        name="Plug Energy Delivered",
        iid=25,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:home-lightning-bolt",
        value_parser=_parse_float,
        retain_on_zero=True,
    ),
    PowerlyncSensorDescription(
        key="local_time",
        name="Local Time",
        iid=26,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_parser=_parse_timestamp,
        retain_on_zero=False,
    ),
    PowerlyncSensorDescription(
        key="meter_last_updated",
        name="Meter Last Updated",
        iid=27,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check",
        value_parser=_parse_timestamp,
        retain_on_zero=False,
    ),
]

IID_TO_DESC = {desc.iid: desc for desc in SENSOR_DESCRIPTIONS}


def _find_hk_device(hass: HomeAssistant, homekit_entry_id: str) -> Any | None:
    """Find the HKDevice for a homekit_controller config entry by exact entry_id."""
    devices: dict = hass.data.get(HOMEKIT_DOMAIN, {})
    for device in devices.values():
        try:
            if device.config_entry.entry_id == homekit_entry_id:
                return device
        except AttributeError:
            continue
    return None


def _resolve_homekit_entry_id(
    hass: HomeAssistant, homekit_entry_id: str, accessory_id: str
) -> str | None:
    """Resolve the live homekit_controller entry_id for the paired Powerlync.

    Used once at startup to detect and heal a stale stored homekit_entry_id
    (e.g. after the HomeKit Device integration was deleted and re-added).

    Match order: exact entry_id → AccessoryPairingID → title contains "Powerlync"
    → first available device (last resort, with warning).
    Returns None only when hass.data has no HKDevices at all.
    """
    devices: dict = hass.data.get(HOMEKIT_DOMAIN, {})
    if not devices:
        return None

    for device in devices.values():
        try:
            if device.config_entry.entry_id == homekit_entry_id:
                return homekit_entry_id
        except AttributeError:
            pass

    if accessory_id:
        for device in devices.values():
            try:
                if device.config_entry.data.get("AccessoryPairingID") == accessory_id:
                    return device.config_entry.entry_id
            except AttributeError:
                pass

    for device in devices.values():
        try:
            if "powerlync" in device.config_entry.title.lower():
                return device.config_entry.entry_id
        except AttributeError:
            pass

    _LOGGER.warning(
        "Powerlync: no device matched homekit_entry_id=%s or accessory_id=%s; "
        "using first HKDevice. Multiple HomeKit devices may resolve incorrectly.",
        homekit_entry_id, accessory_id,
    )
    return next(iter(devices.values())).config_entry.entry_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Powerlync Energy sensors."""
    homekit_entry_id: str = entry.data.get("homekit_entry_id", entry.entry_id)
    accessory_id: str = entry.data.get("accessory_id", "")
    serial: str = entry.data.get("serial", "powerlync-001")
    entities = [PowerlyncSensor(hass, desc, serial, homekit_entry_id) for desc in SENSOR_DESCRIPTIONS]
    iid_to_entity = {e.entity_description.iid: e for e in entities}
    async_add_entities(entities, True)

    # resolved_entry_id may be updated once in _on_start if the stored id is stale.
    # Declared here so _poll closes over the same variable.
    resolved_entry_id = homekit_entry_id

    async def _poll(_now=None):
        hk_device = _find_hk_device(hass, resolved_entry_id)
        if hk_device is None:
            _LOGGER.warning("Powerlync: HKDevice not found (homekit_entry_id=%s)", resolved_entry_id)
            return
        try:
            results = await hk_device.pairing.get_characteristics(CHARACTERISTICS)
            for (aid, iid), char_data in results.items():
                if iid in iid_to_entity:
                    iid_to_entity[iid].update_value(char_data.get("value"))
        except Exception as err:
            _LOGGER.warning("Powerlync: poll failed: %s", err)

    async def _on_start(_event=None):
        nonlocal resolved_entry_id
        found_id = _resolve_homekit_entry_id(hass, homekit_entry_id, accessory_id)
        if found_id is None:
            _LOGGER.warning(
                "Powerlync: no HomeKit devices found at startup "
                "(homekit_entry_id=%s). Sensors will be unavailable until HA restarts.",
                homekit_entry_id,
            )
        elif found_id != homekit_entry_id:
            _LOGGER.warning(
                "Powerlync: stored homekit_entry_id %s is stale (HomeKit Device "
                "integration was likely re-added). Resolved to %s via AccessoryPairingID "
                "or device title. Updating config entry so this only logs once.",
                homekit_entry_id, found_id,
            )
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, "homekit_entry_id": found_id}
            )
            resolved_entry_id = found_id

        await _poll()
        entry.async_on_unload(
            async_track_time_interval(hass, _poll, SCAN_INTERVAL)
        )

    entry.async_on_unload(async_at_start(hass, _on_start))


class PowerlyncSensor(SensorEntity):
    """Sensor for a Powerlync energy characteristic."""

    entity_description: PowerlyncSensorDescription

    def __init__(
        self,
        hass: HomeAssistant,
        description: PowerlyncSensorDescription,
        serial: str = "powerlync-001",
        homekit_entry_id: str = "",
    ) -> None:
        self.hass = hass
        self.entity_description = description
        # unique_id always includes serial so entity IDs are human-readable
        # and consistent regardless of how many hubs are installed.
        # Falls back to homekit_entry_id only if serial is somehow empty.
        uid_discriminator = serial if serial else homekit_entry_id
        self._attr_unique_id = f"powerlync_energy_{uid_discriminator}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, homekit_entry_id)},
            name=f"Powerlync Energy Monitor ({serial})",
            manufacturer="Powerley",
            model="Powerlync",
            serial_number=serial,
        )
        self._attr_native_value = None
        self._retaining_zero = False

    @callback
    def update_value(self, raw: Any) -> None:
        """Update sensor value, retaining last known value on failed or zero reads."""
        if raw is None:
            _LOGGER.debug(
                "Powerlync: %s received None, retaining last value=%s",
                self.entity_description.key,
                self._attr_native_value,
            )
            return

        try:
            parsed = self.entity_description.value_parser(raw)
        except Exception as err:
            _LOGGER.warning(
                "Powerlync: failed to parse %s=%r: %s",
                self.entity_description.key, raw, err,
            )
            return

        if parsed is None:
            _LOGGER.debug(
                "Powerlync: %s parse returned None for raw=%r, retaining last value",
                self.entity_description.key, raw,
            )
            return

        # Retain last known non-zero value when the device returns 0, but only
        # if a non-zero value was previously established — this lets sensors
        # that legitimately read 0 (e.g. unused plug, no solar) pass through.
        # Log only on the first consecutive zero-retain; suppress repeats until
        # a real non-zero reading arrives to avoid log spam.
        if self.entity_description.retain_on_zero and parsed == 0 and self._attr_native_value:
            if not self._retaining_zero:
                _LOGGER.warning(
                    "Powerlync: %s read 0 (raw=%r) while last known value is %s — "
                    "likely a failed read, retaining. Will not log again until "
                    "a non-zero value is received.",
                    self.entity_description.key,
                    raw,
                    self._attr_native_value,
                )
                self._retaining_zero = True
            return

        self._retaining_zero = False
        self._attr_native_value = parsed
        if self.hass is not None:
            self.async_write_ha_state()
