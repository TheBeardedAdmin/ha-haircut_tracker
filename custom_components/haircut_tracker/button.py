"""Button platform for Haircut Tracker."""
from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME
from .__init__ import HaircutTrackerDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haircut Tracker button entities."""
    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([HaircutTrackerForceRefreshButton(coordinator, entry)])


class HaircutTrackerForceRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to force refresh data from the API."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)
        
        self._attr_name = f"Haircut Tracker {self._store_name} Force Refresh"
        self._attr_unique_id = f"{self._store_code}_force_refresh_button"
        self._attr_icon = "mdi:refresh"

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "TheBeardedAdmin",
            "model": "Hair Salon Location",
        }

    async def async_press(self) -> None:
        """Press the button to trigger updates."""
        await self.coordinator.async_request_refresh()
