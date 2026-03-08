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


def _find_powerlync_entry(hass: HomeAssistant) -> config_entries.ConfigEntry | None:
    """Find the homekit_controller config entry for the Powerlync device."""
    for entry in hass.config_entries.async_entries(HOMEKIT_CONTROLLER_DOMAIN):
        if POWERLYNC_MODEL.lower() in entry.title.lower():
            return entry
    return None


class PowerlyncEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Powerlync Energy Monitor."""

    VERSION = 1

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id("powerlync_energy")
        self._abort_if_unique_id_configured()

        hk_entry = _find_powerlync_entry(self.hass)

        if hk_entry is None:
            return self.async_abort(reason="no_powerlync_found")

        return self.async_create_entry(
            title="Powerlync Energy Monitor",
            data={
                "homekit_entry_id": hk_entry.entry_id,
                "accessory_id": hk_entry.data.get("AccessoryPairingID", ""),
            },
        )
