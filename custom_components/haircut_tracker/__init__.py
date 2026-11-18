"""The Haircut Tracker integration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_STORE_CODE,
    CONF_STORE_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_FREQUENCY,
    DEFAULT_FREQUENCY,
    LOGGER,
)
from .api import HaircutTrackerAPI
from .helpers import is_open_at, is_open_now, next_open_datetime, store_now, stylist_name

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CALENDAR]


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

    coordinator = HaircutTrackerDataUpdateCoordinator(
        hass, api, frequency, entry.data.get(CONF_STORE_NAME, store_code)
    )
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options (frequency / enabled metrics) change
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

    def __init__(self, hass: HomeAssistant, api: HaircutTrackerAPI, frequency: int, store_name: str = "") -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.api = api
        self.frequency = frequency
        self.store_name = store_name
        self.last_haircut_date = None
        self.days_since_haircut = 999
        # The stylist endpoint only returns people while the store is open, so keep the last roster.
        self.stylists_cache: dict = {}
        self.stylists_updated: datetime | None = None
        self._store = Store(hass, 1, f"{DOMAIN}_{api.store_code}_stylists")

    async def async_load_cache(self) -> None:
        """Restore the last known stylist roster (survives restarts) and seed known stylists."""
        saved = await self._store.async_load()
        if saved and saved.get("lineup"):
            self.stylists_cache = saved["lineup"]
            try:
                self.stylists_updated = datetime.fromisoformat(saved.get("updated"))
            except (TypeError, ValueError):
                self.stylists_updated = None

        # Seed known stylists if not yet in cache
        now = datetime.now()
        sunday = now.date() - timedelta(days=(now.isoweekday() % 7))
        from .seeds import get_seed_stylists
        seeds = get_seed_stylists(self.api.store_code, sunday)
        if seeds:
            merged = {
                (s.get("uid") or stylist_name(s)): s
                for s in self.stylists_cache.get("stylists", [])
                if (s.get("uid") or stylist_name(s))
            }
            added = False
            for seed in seeds:
                key = seed.get("uid") or stylist_name(seed)
                if key and key not in merged:
                    merged[key] = seed
                    added = True
            if added:
                self.stylists_cache.setdefault("services", [])
                self.stylists_cache["stylists"] = list(merged.values())
                if not self.stylists_updated:
                    self.stylists_updated = now
                await self._store.async_save(
                    {"lineup": self.stylists_cache, "updated": self.stylists_updated.isoformat()}
                )
                LOGGER.info(
                    "Haircut Tracker: Seeded initial stylists into cache for store %s",
                    self.api.store_code,
                )

    async def _async_update_data(self) -> dict:
        """Fetch data from Haircut Tracker API."""
        data = {}

        # 1. Fetch public waitboard (anonymous)
        waitboard = await self.api.get_waitboard()
        data["waitboard"] = waitboard
        store_info = waitboard.get("storeInfo", {})

        # 2. Fetch authenticated data if credentials exist
        if self.api.email and self.api.password:
            if not self.api.bearer_token:
                await self.api.authenticate()

            if self.api.bearer_token:
                try:
                    history = await self.api.get_visit_history()
                    data["history"] = history

                    if history:
                        created_date_str = history[0].get("createdAtUtc")
                        if created_date_str:
                            try:
                                self.last_haircut_date = datetime.fromisoformat(created_date_str.replace("Z", ""))
                                self.days_since_haircut = (
                                    datetime.now(timezone.utc).replace(tzinfo=None) - self.last_haircut_date
                                ).days
                            except Exception as parse_err:
                                LOGGER.warning("Failed to parse visit date: %s", parse_err)

                    # Stylist lineup: only worth asking while the store is open (or if we have nothing yet)
                    if is_open_now(store_info) or not self.stylists_cache:
                        lineup = await self.api.get_stylist_lineup()
                        if lineup.get("stylists"):
                            # Merge newly fetched stylists into persistent cache by UID / name
                            merged = {
                                (s.get("uid") or stylist_name(s)): s
                                for s in self.stylists_cache.get("stylists", [])
                                if (s.get("uid") or stylist_name(s))
                            }
                            for s in lineup.get("stylists", []):
                                key = s.get("uid") or stylist_name(s)
                                if key:
                                    merged[key] = s
                            lineup["stylists"] = list(merged.values())
                            self.stylists_cache = lineup
                            self.stylists_updated = datetime.now()
                            await self._store.async_save(
                                {"lineup": lineup, "updated": self.stylists_updated.isoformat()}
                            )
                            data["stylists_live"] = True

                except Exception as err:
                    LOGGER.error("Error fetching authenticated data: %s", err)

            data["stylists"] = self.stylists_cache
            data.setdefault("stylists_live", False)

        # 3. Dynamic polling rate adjustment (hammering protection)
        self._adjust_polling_interval(waitboard)

        return data

    def _adjust_polling_interval(self, waitboard: dict) -> None:
        """Poll only during store hours; sleep until opening when closed."""
        store_info = waitboard.get("storeInfo", {})

        is_open = is_open_now(store_info)
        # Also honour the live storeState code (10 = Open)
        if store_info and store_info.get("storeState", 10) != 10:
            is_open = False

        if not is_open:
            nxt = next_open_datetime(store_info)
            if nxt:
                wait = max(nxt - store_now(store_info), timedelta(minutes=5)) + timedelta(minutes=5)
            else:
                wait = timedelta(hours=4)
            self.update_interval = wait
            LOGGER.debug("Haircut Tracker: store closed, next poll in %s", wait)
            return

        if self.days_since_haircut < (self.frequency - 3):
            interval = timedelta(hours=12)
        else:
            interval = timedelta(minutes=15)

        # Never schedule a poll that would land outside opening hours: jump to the next opening instead.
        now = store_now(store_info)
        if not is_open_at(store_info, now + interval):
            nxt = next_open_datetime(store_info, after=now)
            if nxt:
                interval = (nxt - now) + timedelta(minutes=5)
        self.update_interval = interval
        LOGGER.debug("Haircut Tracker: store open, next poll in %s", self.update_interval)
