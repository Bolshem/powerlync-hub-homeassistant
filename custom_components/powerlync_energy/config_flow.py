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

        # Extract serial from title e.g. "Powerlync-001-000528" -> "000528"
        # Fall back to the full slugified title, then to homekit_entry_id
        parts = hk_entry.title.replace(" ", "-").split("-")
        serial = parts[-1] if len(parts) >= 3 and parts[-1].isdigit() else hk_entry.title.replace(" ", "-")

        return self.async_create_entry(
            title=f"Powerlync Energy Monitor ({hk_entry.title})",
            data={
                "homekit_entry_id": hk_entry.entry_id,
                "serial": serial,
                "accessory_id": hk_entry.data.get("AccessoryPairingID", ""),
            },
        )
