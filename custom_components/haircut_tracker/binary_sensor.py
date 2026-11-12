"""Binary sensor platform for Haircut Tracker."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Haircut Tracker binary sensors."""
    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        HaircutTrackerOnlineCheckinBinarySensor(coordinator, entry),
    ])


class HaircutTrackerOnlineCheckinBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for store online check-in status."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)
        
        self._attr_name = f"Haircut Tracker {self._store_name} Online Check-In"
        self._attr_unique_id = f"{self._store_code}_online_checkin"
        self._attr_icon = "mdi:cellphone-check"

    @property
    def is_on(self) -> bool:
        """Return true if online check-in is enabled."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        return store_info.get("checkInLaterEnabled", True)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        return {
            "see_stylist_enabled": store_info.get("seeStylistEnabled", True),
            "store_open": store_info.get("storeState") == 10,
        }

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "TheBeardedAdmin",
            "model": "Hair Salon Location",
        }
