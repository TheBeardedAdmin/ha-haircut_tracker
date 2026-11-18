"""Calendar platform for Haircut Tracker."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HaircutTrackerDataUpdateCoordinator
from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME, CONF_EMAIL, CONF_PASSWORD
from .helpers import stylist_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Haircut Tracker calendar platform."""
    if not (entry.data.get(CONF_EMAIL) and entry.data.get(CONF_PASSWORD)):
        return

    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaircutTrackerStylistCalendar(coordinator, entry)])


class HaircutTrackerStylistCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar entity displaying stylist shifts."""

    def __init__(
        self,
        coordinator: HaircutTrackerDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)
        self._attr_name = f"Haircut Tracker {self._store_name} Stylists"
        self._attr_unique_id = f"{self._store_code}_stylists_calendar"
        self._attr_icon = "mdi:calendar-account"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or current shift event."""
        events = self._get_all_events()
        if not events:
            return None
        now = datetime.now().astimezone()
        for ev in events:
            # If current or upcoming
            if ev.end > now:
                return ev
        return events[-1]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = self._get_all_events()
        # Filter events overlapping [start_date, end_date]
        return [ev for ev in events if ev.end >= start_date and ev.start <= end_date]

    def _get_all_events(self) -> list[CalendarEvent]:
        """Build list of CalendarEvent objects from coordinator stylist schedules."""
        events: list[CalendarEvent] = []
        store_info = (self.coordinator.data or {}).get("waitboard", {}).get("storeInfo", {}) or {}
        tz_str = store_info.get("timeZone")
        tz = ZoneInfo(tz_str) if tz_str else datetime.now().astimezone().tzinfo

        stylists = (self.coordinator.data or {}).get("stylists", {}).get("stylists", []) or []
        for s in stylists:
            name = stylist_name(s)
            for sc in s.get("weeklySchedules", []) or []:
                date_str = str(sc.get("date", ""))[:10]  # "2026-11-18"
                for interval in sc.get("intervals", []) or []:
                    start_str = interval.get("start", "")[:5]  # "09:00"
                    end_str = interval.get("end", "")[:5]      # "17:00"
                    try:
                        start_dt = datetime.fromisoformat(f"{date_str}T{start_str}:00").replace(tzinfo=tz)
                        end_dt = datetime.fromisoformat(f"{date_str}T{end_str}:00").replace(tzinfo=tz)
                        events.append(
                            CalendarEvent(
                                summary=f"{name} ({start_str} - {end_str})",
                                start=start_dt,
                                end=end_dt,
                                description=f"{name} scheduled shift at {self._store_name}",
                                location=self._store_name,
                            )
                        )
                    except (ValueError, TypeError):
                        continue

        events.sort(key=lambda x: x.start)
        return events

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "TheBeardedAdmin",
            "model": "Hair Salon Location",
        }
