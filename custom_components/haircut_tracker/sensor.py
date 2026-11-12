"""Sensor platform for Haircut Tracker."""
from __future__ import annotations
from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME, CONF_EMAIL, CONF_PASSWORD, CONF_FREQUENCY, DEFAULT_FREQUENCY
from .__init__ import HaircutTrackerDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haircut Tracker sensor entities."""
    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        HaircutTrackerStoreWaitTimeSensor(coordinator, entry),
        HaircutTrackerStoreQueueSensor(coordinator, entry),
        HaircutTrackerStoreHoursSensor(coordinator, entry),
    ]

    # Only add history-related sensors if authenticated
    if entry.data.get(CONF_EMAIL) and entry.data.get(CONF_PASSWORD):
        entities.extend([
            HaircutTrackerHaircutDueStatusSensor(coordinator, entry),
            HaircutTrackerFavoriteStylistsSensor(coordinator, entry),
            HaircutTrackerBestDaySensor(coordinator, entry),
        ])

    async_add_entities(entities)


class HaircutTrackerBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Haircut Tracker sensors."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "Haircut Tracker",
            "model": "Hair Salon Location",
        }


class HaircutTrackerStoreWaitTimeSensor(HaircutTrackerBaseSensor):
    """Sensor that exposes next available wait time at the store."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the wait time sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = f"Haircut Tracker {self._store_name} Wait Time"
        self._attr_unique_id = f"{self._store_code}_wait_time"
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str | None:
        """Return the next available wait time."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        wait_info = store_info.get("waitInfo")
        
        if not wait_info:
            # 10 is the code for Open
            if store_info.get("storeState") == 10:
                return "00:00:00"
            return "Closed"
            
        return wait_info.get("waitTime", "00:00:00")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        address = store_info.get("address", {})
        
        # Parse store hours weekly schedule
        weekly_hours = []
        days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
        for s in store_info.get("weeklySchedules", []):
            wday = s.get("weekday")
            intervals = s.get("intervals", [])
            int_str = ", ".join([f"{i.get('start')[:5]}-{i.get('end')[:5]}" for i in intervals]) if intervals else "Closed"
            weekly_hours.append(f"{days_map.get(wday)}: {int_str}")

        return {
            "store_name": self._store_name,
            "store_code": self._store_code,
            "address": f"{address.get('street1', '')} {address.get('street2', '') or ''}, {address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}".strip(),
            "phone": store_info.get("phone"),
            "expected_start_time": store_info.get("waitInfo", {}).get("expectedServiceStartTime"),
            "online_checkin_enabled": store_info.get("checkInLaterEnabled", True),
            "see_stylist_enabled": store_info.get("seeStylistEnabled", True),
            "store_open": store_info.get("storeState") == 10,
            "weekly_hours": weekly_hours,
        }


class HaircutTrackerStoreQueueSensor(HaircutTrackerBaseSensor):
    """Sensor that exposes number of clients in queue."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the queue sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = f"Haircut Tracker {self._store_name} Queue Size"
        self._attr_unique_id = f"{self._store_code}_queue_size"
        self._attr_icon = "mdi:account-group"
        self._attr_native_unit_of_measurement = "people"

    @property
    def native_value(self) -> int | None:
        """Return the number of checked-in clients."""
        items = self.coordinator.data.get("waitboard", {}).get("waitBoardItems", [])
        return len(items)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        items = self.coordinator.data.get("waitboard", {}).get("waitBoardItems", [])
        queue_list = []
        for item in items:
            queue_list.append({
                "client": f"{item.get('clientFirstName')} {item.get('clientLastName') or ''}".strip(),
                "wait_time": item.get("waitTime"),
                "stylist": item.get("employeeDisplayName"),
                "status": item.get("displayedClientQueueStatus"),
            })
        return {
            "queue_list": queue_list
        }


class HaircutTrackerHaircutDueStatusSensor(HaircutTrackerBaseSensor):
    """Sensor that tracks if the user is due for a haircut based on configured frequency."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the due status sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Haircut Tracker Haircut Due Status"
        self._attr_unique_id = f"{self._store_code}_haircut_due_status"
        self._attr_icon = "mdi:scissors-cutting"

    @property
    def native_value(self) -> str:
        """Return the due status."""
        days_since = self.coordinator.days_since_haircut
        frequency = self.coordinator.frequency
        if days_since >= frequency:
            return "Due"
        return "Ok"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        days_since = self.coordinator.days_since_haircut
        frequency = self.coordinator.frequency
        last_cut = self.coordinator.last_haircut_date
        
        # Get latest visit metadata
        history = self.coordinator.data.get("history", [])
        last_stylist = "Unknown"
        last_service = "Unknown"
        
        if history:
            client_items = history[0].get("clientItems", [])
            if client_items:
                services = client_items[0].get("services", [])
                if services:
                    emp = services[0].get("employee", {})
                    last_stylist = emp.get("displayName") or f"{emp.get('firstName', '')} {emp.get('lastName', '')}".strip()
                    last_service = services[0].get("serviceName")

        return {
            "days_since_last_haircut": days_since,
            "haircut_frequency_days": frequency,
            "days_until_due": max(0, frequency - days_since),
            "last_haircut_date": last_cut.isoformat() if last_cut else "None",
            "last_stylist": last_stylist,
            "last_service": last_service,
        }


class HaircutTrackerFavoriteStylistsSensor(HaircutTrackerBaseSensor):
    """Sensor that monitors if favorite stylists are working today and their wait times."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the favorite stylists sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Haircut Tracker Favorite Stylists Status"
        self._attr_unique_id = f"{self._store_code}_favorite_stylists_status"
        self._attr_icon = "mdi:heart-outline"

    @property
    def native_value(self) -> str:
        """Return name of first working favorite stylist, or 'None Working'."""
        working_favs = self._get_working_favorites()
        if not working_favs:
            return "None Working"
        return working_favs[0]["name"]

    def _get_favorites(self) -> list[str]:
        """Helper to get list of favorite stylist names from visit history."""
        history = self.coordinator.data.get("history", [])
        past_stylists = {}
        for visit in history:
            client_items = visit.get("clientItems", [])
            if client_items:
                services = client_items[0].get("services", [])
                if services:
                    emp = services[0].get("employee", {})
                    name = emp.get("displayName") or emp.get("firstName", "")
                    if name:
                        past_stylists[name] = past_stylists.get(name, 0) + 1
        
        # Return favorites ordered by frequency of cuts
        return [name for name, _ in sorted(past_stylists.items(), key=lambda x: x[1], reverse=True)]

    def _get_working_favorites(self) -> list[dict]:
        """Helper to get list of working favorite stylists from the active lineup."""
        favorites = self._get_favorites()

        # Match against current scheduled lineup
        lineup_data = self.coordinator.data.get("stylists", {})
        stylists_list = lineup_data.get("stylists", [])
        
        working_favs = []
        for stylist in stylists_list:
            display_name = stylist.get("displayName") or stylist.get("firstName", "")
            if display_name in favorites:
                working_favs.append({
                    "name": display_name,
                    "available": stylist.get("isAvailable"),
                    "wait_time": stylist.get("waitTime"),
                })
        
        return working_favs

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        working_favs = self._get_working_favorites()
        favorites = self._get_favorites()
        
        # Build complete lineup listing
        lineup_data = self.coordinator.data.get("stylists", {})
        stylists_list = lineup_data.get("stylists", [])
        
        full_lineup = []
        for stylist in stylists_list:
            full_lineup.append({
                "name": stylist.get("displayName") or stylist.get("firstName", ""),
                "available": stylist.get("isAvailable"),
                "wait_time": stylist.get("waitTime"),
            })

        # Calculate weekly schedules of favorite stylists
        fav_schedules = {}
        days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
        
        # Dictionary to track working favorites count per weekday (1-7)
        best_days_count = {i: 0 for i in range(1, 8)}
        
        for stylist in stylists_list:
            display_name = stylist.get("displayName") or stylist.get("firstName", "")
            if display_name in favorites:
                stylist_sched = []
                for s in stylist.get("weeklySchedules", []):
                    wday = s.get("weekday")
                    intervals = s.get("intervals", [])
                    if intervals:
                        best_days_count[wday] += 1
                        int_str = ", ".join([f"{i.get('start')[:5]}-{i.get('end')[:5]}" for i in intervals])
                        stylist_sched.append(f"{days_map.get(wday)}: {int_str}")
                    else:
                        stylist_sched.append(f"{days_map.get(wday)}: Off")
                fav_schedules[display_name] = stylist_sched

        # Determine the best days to visit (days with the highest count of working favorites)
        max_favorites = max(best_days_count.values()) if best_days_count else 0
        best_days = []
        if max_favorites > 0:
            best_days = [days_map[wday] for wday, count in best_days_count.items() if count == max_favorites]

        attributes = {
            "working_favorites": [f["name"] for f in working_favs],
            "full_lineup": full_lineup,
            "favorite_schedules": fav_schedules,
            "best_days_to_visit": best_days,
        }

        # Expose wait time of first working favorite stylist
        if working_favs:
            attributes["favorite_wait_time"] = working_favs[0]["wait_time"]
        else:
            attributes["favorite_wait_time"] = "N/A"

        return attributes


class HaircutTrackerStoreHoursSensor(HaircutTrackerBaseSensor):
    """Sensor that exposes today's store hours."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the store hours sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = f"Haircut Tracker {self._store_name} Store Hours"
        self._attr_unique_id = f"{self._store_code}_store_hours"
        self._attr_icon = "mdi:store-clock"

    @property
    def native_value(self) -> str:
        """Return today's store hours."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        weekly_schedules = store_info.get("weeklySchedules", [])
        
        # Today's day of week: Monday=1, ..., Sunday=7
        today_wday = datetime.now().isoweekday()
        
        for s in weekly_schedules:
            if s.get("weekday") == today_wday:
                intervals = s.get("intervals", [])
                if intervals:
                    return ", ".join([f"{i.get('start')[:5]}-{i.get('end')[:5]}" for i in intervals])
                break
        return "Closed"

    @property
    def extra_state_attributes(self) -> dict:
        """Return weekly store hours schedule."""
        store_info = self.coordinator.data.get("waitboard", {}).get("storeInfo", {})
        
        weekly_hours = []
        days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
        for s in store_info.get("weeklySchedules", []):
            wday = s.get("weekday")
            intervals = s.get("intervals", [])
            int_str = ", ".join([f"{i.get('start')[:5]}-{i.get('end')[:5]}" for i in intervals]) if intervals else "Closed"
            weekly_hours.append(f"{days_map.get(wday)}: {int_str}")

        return {
            "weekly_hours": weekly_hours
        }


class HaircutTrackerBestDaySensor(HaircutTrackerBaseSensor):
    """Sensor that predicts the best day to visit the store."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the best day sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Haircut Tracker Best Day to Visit"
        self._attr_unique_id = f"{self._store_code}_best_day_to_visit"
        self._attr_icon = "mdi:calendar-star"

    @property
    def native_value(self) -> str:
        """Return the best day(s) to visit."""
        # 1. Retrieve favorites list from history
        history = self.coordinator.data.get("history", [])
        past_stylists = {}
        for visit in history:
            client_items = visit.get("clientItems", [])
            if client_items:
                services = client_items[0].get("services", [])
                if services:
                    emp = services[0].get("employee", {})
                    name = emp.get("displayName") or emp.get("firstName", "")
                    if name:
                        past_stylists[name] = past_stylists.get(name, 0) + 1
        favorites = [name for name, _ in sorted(past_stylists.items(), key=lambda x: x[1], reverse=True)]

        # 2. Match schedules of working favorites
        lineup_data = self.coordinator.data.get("stylists", {})
        stylists_list = lineup_data.get("stylists", [])
        
        days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
        best_days_count = {i: 0 for i in range(1, 8)}
        
        for stylist in stylists_list:
            display_name = stylist.get("displayName") or stylist.get("firstName", "")
            if display_name in favorites:
                for s in stylist.get("weeklySchedules", []):
                    wday = s.get("weekday")
                    intervals = s.get("intervals", [])
                    if intervals:
                        best_days_count[wday] += 1

        max_favorites = max(best_days_count.values()) if best_days_count else 0
        if max_favorites > 0:
            best_days = [days_map[wday] for wday, count in best_days_count.items() if count == max_favorites]
            return ", ".join(best_days)
        
        return "Unknown"
