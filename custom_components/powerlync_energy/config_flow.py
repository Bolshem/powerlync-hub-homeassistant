"""Config flow for Powerlync Energy Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

HOMEKIT_CONTROLLER_DOMAIN = "homekit_controller"
POWERLYNC_MODEL = "Powerlync"


def _find_powerlync_entries(hass: HomeAssistant) -> list[config_entries.ConfigEntry]:
    """Return all homekit_controller config entries for Powerlync devices."""
    return [
        entry
        for entry in hass.config_entries.async_entries(HOMEKIT_CONTROLLER_DOMAIN)
        if POWERLYNC_MODEL.lower() in entry.title.lower()
    ]


def _get_serial_from_device_registry(hass: HomeAssistant, hk_entry: config_entries.ConfigEntry) -> str | None:
    """Read serial from the HA device registry for the homekit_controller entry."""
    try:
        from homeassistant.helpers import device_registry as dr
        dev_reg = dr.async_get(hass)
        for device in dev_reg.devices.values():
            if hk_entry.entry_id in device.config_entries:
                # serial_number or name may be "001-000528" or "Powerlync-001-000528"
                # Always take just the last numeric segment
                raw = device.serial_number or device.name or ""
                parts = raw.split("-")
                last = parts[-1].strip()
                if last.isdigit():
                    return last
                if raw.strip():
                    return raw.strip()
    except Exception as err:
        _LOGGER.debug("Powerlync: device registry serial lookup failed: %s", err)
    return None


def _get_accessory_serial(hass: HomeAssistant, hk_entry: config_entries.ConfigEntry) -> str:
    """Extract the serial number from the HomeKit accessory data.

    homekit_controller stores the full accessory list in the config entry data.
    We deserialize it with aiohomekit and read the standard serial_number
    characteristic from the AccessoryInformation service.

    Falls back to a short slice of entry_id if not found.
    """
    from aiohomekit.model import Accessories

    # homekit_controller stores accessories under one of these keys
    for key in ("accessories", "AccessoryInfo", "pairing_data"):
        try:
            data = hk_entry.data.get(key)
            if not data:
                continue
            # data may be a list of accessories or a dict wrapping them
            if isinstance(data, dict):
                data = data.get("accessories", [])
            if not isinstance(data, list) or not data:
                continue
            accessories = Accessories.from_list(data)
            serial = accessories.aid(1).serial_number
            if serial and serial.strip():
                _LOGGER.debug("Powerlync: got serial %s from key %s", serial, key)
                return serial.strip()
        except Exception as err:
            _LOGGER.debug("Powerlync: serial read from %s failed: %s", key, err)

    # Try device registry — serial is stored there by homekit_controller
    serial = _get_serial_from_device_registry(hass, hk_entry)
    if serial:
        _LOGGER.debug("Powerlync: got serial %s from device registry", serial)
        return serial

    # Last resort: short unique slice of entry_id
    _LOGGER.warning(
        "Powerlync: could not read serial from pairing data for entry %s, "
        "using entry_id fallback. Entity IDs may not be human-readable.",
        hk_entry.entry_id,
    )
    return hk_entry.entry_id[:8]


def _already_configured_entry_ids(hass: HomeAssistant) -> set[str]:
    """Return homekit_entry_ids already managed by an existing powerlync_energy entry."""
    return {
        entry.data.get("homekit_entry_id")
        for entry in hass.config_entries.async_entries(DOMAIN)
    }


class PowerlyncEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Powerlync Energy Monitor.

    Creates one config entry per paired Powerlync hub. Triggered from
    Settings → Devices & Services → Add Integration — no configuration.yaml needed.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle setup from the UI.

        Finds all paired Powerlync hubs and creates one config entry per hub.
        """
        hk_entries = _find_powerlync_entries(self.hass)
        already_configured = _already_configured_entry_ids(self.hass)
        new_entries = [e for e in hk_entries if e.entry_id not in already_configured]

        if not hk_entries:
            return self.async_abort(reason="no_powerlync_found")

        if not new_entries:
            return self.async_abort(reason="already_configured")

        # Spawn separate flows for hubs 2+ so each gets its own config entry.
        # Pass the specific entry via context so the flow doesn't re-run discovery.
        for extra in new_entries[1:]:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "single_hub", "hk_entry": extra},
                    data={},
                )
            )

        return await self._create_entry_for(new_entries[0])

    async def async_step_single_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle flow for a specific hub, passed via context by async_step_user."""
        hk_entry = self.context.get("hk_entry")
        if hk_entry is None:
            return self.async_abort(reason="no_powerlync_found")
        return await self._create_entry_for(hk_entry)

    async def _create_entry_for(
        self, hk_entry: config_entries.ConfigEntry
    ) -> FlowResult:
        """Create a powerlync_energy config entry for a specific homekit entry."""
        await self.async_set_unique_id(f"powerlync_energy_{hk_entry.entry_id}")
        self._abort_if_unique_id_configured()

        # Read the serial number directly from the HomeKit accessory data.
        # HA stores the full accessory entity map in the homekit_controller
        # config entry data under the "accessories" key.
        serial = _get_accessory_serial(self.hass, hk_entry)

        return self.async_create_entry(
            title=f"Powerlync Energy Monitor ({serial})",
            data={
                "homekit_entry_id": hk_entry.entry_id,
                "serial": serial,
                "accessory_id": hk_entry.data.get("AccessoryPairingID", ""),
            },
        )
