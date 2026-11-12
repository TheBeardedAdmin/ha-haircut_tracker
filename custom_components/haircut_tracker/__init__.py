"""The Haircut Tracker integration."""
from __future__ import annotations
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_STORE_CODE, CONF_EMAIL, CONF_PASSWORD, CONF_FREQUENCY, DEFAULT_FREQUENCY, LOGGER
from .api import HaircutTrackerAPI

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Haircut Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    session = async_get_clientsession(hass)
    store_code = entry.data.get(CONF_STORE_CODE)
    email = entry.data.get(CONF_EMAIL)
    password = entry.data.get(CONF_PASSWORD)
    # Read from options first, fallback to initial config data
    frequency = entry.options.get(CONF_FREQUENCY, entry.data.get(CONF_FREQUENCY, DEFAULT_FREQUENCY))

    api = HaircutTrackerAPI(session, store_code, email, password)

    # Initialize Coordinator
    coordinator = HaircutTrackerDataUpdateCoordinator(hass, api, frequency)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class HaircutTrackerDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Haircut Tracker data."""

    def __init__(self, hass: HomeAssistant, api: HaircutTrackerAPI, frequency: int) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            # Start with a default 15 minute interval
            update_interval=timedelta(minutes=15),
        )
        self.api = api
        self.frequency = frequency
        self.last_haircut_date = None
        self.days_since_haircut = 999

    async def _async_update_data(self) -> dict:
        """Fetch data from Haircut Tracker API."""
        data = {}
        
        # 1. Fetch public waitboard (anonymous)
        waitboard = await self.api.get_waitboard()
        data["waitboard"] = waitboard

        # 2. Fetch authenticated data if credentials exist
        if self.api.email and self.api.password:
            # Login if no token
            if not self.api.bearer_token:
                await self.api.authenticate()

            if self.api.bearer_token:
                try:
                    # Fetch history
                    history = await self.api.get_visit_history()
                    data["history"] = history
                    
                    # Update last haircut details
                    if history:
                        # Find the first visit in the list with a valid date
                        latest_visit = history[0]
                        created_date_str = latest_visit.get("createdAtUtc")
                        if created_date_str:
                            # format: e.g. "2026-07-20T17:30:20Z"
                            try:
                                # Clean Z at the end for compatibility
                                clean_date = created_date_str.replace("Z", "")
                                self.last_haircut_date = datetime.fromisoformat(clean_date)
                                self.days_since_haircut = (datetime.utcnow() - self.last_haircut_date).days
                            except Exception as parse_err:
                                LOGGER.warning("Failed to parse visit date: %s", parse_err)
                    
                    # Fetch complete stylist lineup
                    stylists = await self.api.get_stylist_lineup()
                    data["stylists"] = stylists

                except Exception as err:
                    LOGGER.error("Error fetching authenticated data: %s", err)

        # 3. Dynamic polling rate adjustment (Hammering Protection)
        self._adjust_polling_interval(waitboard)

        return data

    def _is_during_store_hours(self, waitboard: dict) -> bool:
        """Helper to check if the current local time is within the store's scheduled hours."""
        store_info = waitboard.get("storeInfo", {})
        weekly_schedules = store_info.get("weeklySchedules", [])
        
        now = datetime.now()
        today_wday = now.isoweekday()
        current_time_str = now.strftime("%H:%M:%S")
        
        for s in weekly_schedules:
            if s.get("weekday") == today_wday:
                intervals = s.get("intervals", [])
                if not intervals:
                    return False  # Closed all day
                for interval in intervals:
                    start = interval.get("start")
                    end = interval.get("end")
                    if start <= current_time_str <= end:
                        return True
                break
        return False

    def _calculate_time_until_open(self, waitboard: dict) -> timedelta:
        """Calculate the time remaining until the store opens next."""
        store_info = waitboard.get("storeInfo", {})
        weekly_schedules = store_info.get("weeklySchedules", [])
        
        now = datetime.now()
        for day_offset in range(8):
            check_date = now + timedelta(days=day_offset)
            wday = check_date.isoweekday()
            
            sched = next((s for s in weekly_schedules if s.get("weekday") == wday), None)
            if sched:
                intervals = sched.get("intervals", [])
                for interval in intervals:
                    start_str = interval.get("start")
                    try:
                        open_time = datetime.strptime(start_str, "%H:%M:%S").time()
                        open_dt = datetime.combine(check_date.date(), open_time)
                        if open_dt > now:
                            return open_dt - now
                    except Exception:
                        pass
        return timedelta(hours=4)

    def _adjust_polling_interval(self, waitboard: dict) -> None:
        """Dynamically adjust the polling interval based on haircut due status and store hours."""
        # Determine if store is currently open
        is_open = self._is_during_store_hours(waitboard)
        
        # In addition, check the live storeState code (10 = Open)
        store_state = waitboard.get("storeInfo", {}).get("storeState", 10)
        if store_state != 10:
            is_open = False

        if not is_open:
            # If closed, sleep exactly until it opens next plus a 5 minute buffer
            time_until_open = self._calculate_time_until_open(waitboard)
            self.update_interval = time_until_open + timedelta(minutes=5)
            LOGGER.debug("Haircut Tracker: Store is closed. Scheduling next poll in %s (when store opens next + 5m).", self.update_interval)
            return

        # If store is open, determine rate based on haircut due status
        if self.days_since_haircut < (self.frequency - 3):
            # Not due: poll very infrequently (every 12 hours)
            self.update_interval = timedelta(hours=12)
            LOGGER.debug("Haircut Tracker: User not due yet (%s days since last cut). Setting update interval to 12 hours.", self.days_since_haircut)
        else:
            # Due or approaching: poll frequently (every 15 minutes) during open hours
            self.update_interval = timedelta(minutes=15)
            LOGGER.debug("Haircut Tracker: User is due / approaching due (%s days since last cut) and store is open. Setting update interval to 15 minutes.", self.days_since_haircut)
