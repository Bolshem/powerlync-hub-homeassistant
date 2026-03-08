"""Powerlync Energy Monitor - exposes energy characteristics from Powerlync hub."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "powerlync_energy"
PLATFORMS = ["sensor"]

# Custom HAP service / characteristic UUIDs from Powerlync
POWERLYNC_SERVICE_UUID = "DBDE3C5B-D7EA-434B-8684-356FAFAFD1A6"

CHAR_INSTANTANEOUS_DEMAND      = "E9F68B13-07D7-4BFD-AC36-A4EB822F0CBE"  # iid 21 string "0.859 kW"
CHAR_SUMMATION_DELIVERED       = "63C37691-74BD-49B7-8E70-D616B0358019"  # iid 22 string "064732.4 kWh"
CHAR_SUMMATION_RECEIVED        = "46BBA308-315C-43AF-9399-4ABDF3189011"  # iid 23 string "0.1 kWh"
CHAR_LOCAL_DEMAND              = "0F6A4870-D722-4746-B5F6-5A8592F332B2"  # iid 24 float watts
CHAR_LOCAL_SUMMATION_DELIVERED = "8746F293-608A-4694-BAFD-A51F67A7A979"  # iid 25 float kWh
CHAR_LOCAL_TIME                = "EB6FAD18-9873-4D2C-A0E4-E86BC8FD7EDD"  # iid 26 int UTC
CHAR_METER_TIME                = "B8780157-1BC7-470F-B611-61200442517A"  # iid 27 int UTC
CHAR_ZIGBEE_MAC                = "CD4DF6DC-8EAC-4818-92BF-AA408F2D8F33"  # iid 28 string



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Powerlync Energy from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok