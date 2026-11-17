"""Binary sensor platform for Haircut Tracker."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HaircutTrackerDataUpdateCoordinator
from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME
from .sensor import enabled_metrics, _store


@dataclass(frozen=True)
class BinarySpec:
    key: str
    unique_suffix: str
    name: str
    icon: str
    value: Callable[[HaircutTrackerDataUpdateCoordinator], bool]
    attrs: Callable[[HaircutTrackerDataUpdateCoordinator], dict] | None = None
    device_class: BinarySensorDeviceClass | None = None


BINARY_SPECS: tuple[BinarySpec, ...] = (
    BinarySpec(
        "online_checkin", "online_checkin", "Haircut Tracker {store} Online Check-In", "mdi:cellphone-check",
        lambda c: bool(_store(c).get("checkInLaterEnabled", True)),
        lambda c: {
            "see_stylist_enabled": _store(c).get("seeStylistEnabled", True),
            "store_open": _store(c).get("storeState") == 10,
        },
    ),
    BinarySpec(
        "see_stylist", "see_stylist", "Haircut Tracker {store} See Stylist Enabled", "mdi:account-star",
        lambda c: bool(_store(c).get("seeStylistEnabled", True)),
    ),
    BinarySpec(
        "store_open", "store_open", "Haircut Tracker {store} Open", "mdi:store",
        lambda c: _store(c).get("storeState") == 10,
        lambda c: {"store_state_code": _store(c).get("storeState")},
        BinarySensorDeviceClass.OPENING,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the enabled Haircut Tracker binary sensors."""
    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    wanted = enabled_metrics(entry)
    store_code = entry.data.get(CONF_STORE_CODE)

    registry = er.async_get(hass)
    for spec in BINARY_SPECS:
        if spec.key not in wanted:
            ent_id = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{store_code}_{spec.unique_suffix}")
            if ent_id:
                registry.async_remove(ent_id)

    async_add_entities(
        HaircutTrackerBinarySensor(coordinator, entry, spec) for spec in BINARY_SPECS if spec.key in wanted
    )


class HaircutTrackerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Generic metric binary sensor driven by a BinarySpec."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry, spec: BinarySpec) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)
        self._attr_name = spec.name.format(store=self._store_name)
        self._attr_unique_id = f"{self._store_code}_{spec.unique_suffix}"
        self._attr_icon = spec.icon
        self._attr_device_class = spec.device_class

    @property
    def is_on(self) -> bool | None:
        try:
            return self._spec.value(self.coordinator)
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._spec.attrs(self.coordinator) if self._spec.attrs else None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "TheBeardedAdmin",
            "model": "Hair Salon Location",
        }
