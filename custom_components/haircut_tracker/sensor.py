"""Sensor platform for Haircut Tracker."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HaircutTrackerDataUpdateCoordinator
from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME, CONF_EMAIL, CONF_PASSWORD
from .helpers import (
    DAY_NAMES,
    favorites_from_history,
    fmt_intervals,
    history_stats,
    hours_open,
    is_open_now,
    next_open_datetime,
    schedule_for_day,
    sorted_schedules,
    stylist_name,
    store_now,
    week_table,
)
from .const import CONF_METRICS
from .metrics import available_metrics, default_enabled


# --------------------------------------------------------------------------- #
# Data accessors
# --------------------------------------------------------------------------- #
def _store(c: HaircutTrackerDataUpdateCoordinator) -> dict:
    return (c.data or {}).get("waitboard", {}).get("storeInfo", {}) or {}


def _items(c: HaircutTrackerDataUpdateCoordinator) -> list[dict]:
    return (c.data or {}).get("waitboard", {}).get("waitBoardItems", []) or []


def _stylists(c: HaircutTrackerDataUpdateCoordinator) -> list[dict]:
    return (c.data or {}).get("stylists", {}).get("stylists", []) or []


def _history(c: HaircutTrackerDataUpdateCoordinator) -> list[dict]:
    return (c.data or {}).get("history", []) or []


def _legacy_hours(store: dict) -> list[str]:
    out = []
    for s in sorted_schedules(store.get("weeklySchedules", [])):
        ints = s.get("intervals") or []
        text = ", ".join(f"{i['start'][:5]}-{i['end'][:5]}" for i in ints) if ints else "Closed"
        out.append(f"{DAY_NAMES.get(s.get('weekday'))}: {text}")
    return out


# --------------------------------------------------------------------------- #
# Metric value / attribute functions
# --------------------------------------------------------------------------- #
def wait_time_value(c):
    store = _store(c)
    wait_info = store.get("waitInfo")
    if not wait_info:
        return "00:00:00" if store.get("storeState") == 10 else "Closed"
    return wait_info.get("waitTime", "00:00:00")


def wait_time_attrs(c):
    store = _store(c)
    addr = store.get("address", {}) or {}
    return {
        "store_name": c.store_name,
        "store_code": c.api.store_code,
        "address": f"{addr.get('street1', '')} {addr.get('street2', '') or ''}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zip', '')}".strip(),
        "phone": store.get("phone"),
        "expected_start_time": (store.get("waitInfo") or {}).get("expectedServiceStartTime"),
        "online_checkin_enabled": store.get("checkInLaterEnabled", True),
        "see_stylist_enabled": store.get("seeStylistEnabled", True),
        "store_open": store.get("storeState") == 10,
        "weekly_hours": _legacy_hours(store),
    }


def queue_size_attrs(c):
    return {
        "queue_list": [
            {
                "client": f"{i.get('clientFirstName')} {i.get('clientLastName') or ''}".strip(),
                "wait_time": i.get("waitTime"),
                "stylist": i.get("employeeDisplayName"),
                "status": i.get("displayedClientQueueStatus"),
            }
            for i in _items(c)
        ]
    }


def store_hours_value(c):
    store = _store(c)
    sched = schedule_for_day(store.get("weeklySchedules", []), store_now(store).date())
    ints = (sched or {}).get("intervals") or []
    if not ints:
        return "Closed"
    return ", ".join(f"{i['start'][:5]}-{i['end'][:5]}" for i in ints)


def store_hours_attrs(c):
    return {"weekly_hours": _legacy_hours(_store(c))}


def weekly_schedule_value(c):
    store = _store(c)
    total = sum(hours_open(s.get("intervals")) for s in store.get("weeklySchedules", []))
    return round(total, 1) if store.get("weeklySchedules") else None


def weekly_schedule_attrs(c):
    store = _store(c)
    today = store_now(store).date()
    rows = week_table(store.get("weeklySchedules", []), today)
    md = ["| Day | Date | Hours |", "|---|---|---|"]
    for r in rows:
        mark = " **(today)**" if r["is_today"] else ""
        note = f" _{r['exception_reason']}_" if r["exception_reason"] else ""
        md.append(f"| {r['day']}{mark} | {r['date']} | {r['hours']}{note} |")
    return {
        "schedule": rows,
        "summary": [f"{r['day']}: {r['hours']}" for r in rows],
        "days_open": sum(1 for r in rows if r["open"]),
        "special_hours_days": [r["date"] for r in rows if r["special_hours"]],
        "markdown": "\n".join(md),
    }


def store_status_value(c):
    store = _store(c)
    label = (store.get("displayDetails") or {}).get("statusLabel") or (store.get("pin") or {}).get("status")
    if label:
        return str(label).title()
    return "Open" if store.get("storeState") == 10 else "Closed"


def store_status_attrs(c):
    store = _store(c)
    nxt = next_open_datetime(store)
    dd = store.get("displayDetails") or {}
    return {
        "store_state_code": store.get("storeState"),
        "pin_text": (store.get("pin") or {}).get("text"),
        "open_by_schedule": is_open_now(store),
        "next_open": nxt.isoformat() if nxt else None,
        "next_open_day": dd.get("openDay"),
        "open_time": dd.get("openTime"),
        "close_time": dd.get("closeTime"),
        "wait_reason_code": (store.get("waitInfo") or {}).get("reason"),
        "stylist_available": (store.get("waitInfo") or {}).get("existsAvailableEmployee"),
        "store_time": store_now(store).isoformat(timespec="minutes"),
    }


def expected_start_value(c):
    return (_store(c).get("waitInfo") or {}).get("expectedServiceStartTime")


def queue_breakdown_value(c):
    qlen = (_store(c).get("waitInfo") or {}).get("queueLength")
    return qlen if qlen is not None else len(_items(c))


def queue_breakdown_attrs(c):
    by_status: dict[str, int] = {}
    by_stylist: dict[str, int] = {}
    for i in _items(c):
        by_status[i.get("displayedClientQueueStatus") or "UNKNOWN"] = by_status.get(i.get("displayedClientQueueStatus") or "UNKNOWN", 0) + 1
        who = i.get("employeeDisplayName") or "First available"
        by_stylist[who] = by_stylist.get(who, 0) + 1
    wi = _store(c).get("waitInfo") or {}
    return {
        "by_status": by_status,
        "by_stylist": by_stylist,
        "board_items": len(_items(c)),
        "original_wait_time": wi.get("originalWaitTime"),
        "wait_time_generated_at": wi.get("waitTimeGeneratedAt"),
    }


def checkin_rules_value(c):
    return _store(c).get("olciHardStopTimeMinutes")


def checkin_rules_attrs(c):
    s = _store(c)
    return {
        "early_arrival_minutes": s.get("earlyArrivalMinutes"),
        "online_checkin_hard_stop_minutes": s.get("olciHardStopTimeMinutes"),
        "max_wait_for_checkin_minutes": s.get("checkInMaxWaitTimeInMinutes"),
        "online_checkin_enabled": s.get("checkInLaterEnabled"),
        "see_stylist_enabled": s.get("seeStylistEnabled"),
    }


def store_info_value(c):
    return _store(c).get("name") or c.store_name


def store_info_attrs(c):
    s = _store(c)
    a = s.get("address", {}) or {}
    return {
        "store_code": s.get("shortName"),
        "store_uid": s.get("uid"),
        "street": a.get("street1"),
        "suite": a.get("street2"),
        "city": a.get("city"),
        "state": a.get("state"),
        "zip": a.get("zip"),
        "phone": s.get("phone"),
        "latitude": s.get("latitude"),
        "longitude": s.get("longitude"),
        "time_zone": s.get("timeZone"),
        "website": s.get("webSite"),
        "facebook": s.get("facebook"),
        "twitter": s.get("twitter"),
        "instagram": s.get("instagram"),
        "yelp": s.get("yelp"),
        "disclaimer": s.get("disclaimer"),
        "picture_url": s.get("pictureURL"),
    }


# ---- account metrics -------------------------------------------------------
def haircut_due_value(c):
    return "Due" if c.days_since_haircut >= c.frequency else "Ok"


def haircut_due_attrs(c):
    days, freq, last = c.days_since_haircut, c.frequency, c.last_haircut_date
    latest = (_history(c) or [None])[0]
    last_stylist = last_service = "Unknown"
    if latest:
        from .helpers import visit_details
        d = visit_details(latest)
        if d:
            last_stylist = d["stylist"] or "Unknown"
            last_service = d["service"] or "Unknown"
    return {
        "days_since_last_haircut": days,
        "haircut_frequency_days": freq,
        "days_until_due": max(0, freq - days),
        "last_haircut_date": last.isoformat() if last else "None",
        "last_stylist": last_stylist,
        "last_service": last_service,
    }


def _favorite_info(c):
    favs = favorites_from_history(_history(c))
    working, lineup, schedules = [], [], {}
    counts = {i: 0 for i in range(1, 8)}
    for s in _stylists(c):
        name = stylist_name(s)
        lineup.append({"name": name, "available": s.get("isAvailable"), "wait_time": s.get("waitTime")})
        if name in favs:
            working.append({"name": name, "available": s.get("isAvailable"), "wait_time": s.get("waitTime")})
            rows = []
            for sc in sorted_schedules(s.get("weeklySchedules", [])):
                ints = sc.get("intervals") or []
                if ints:
                    counts[sc["weekday"]] += 1
                rows.append(f"{DAY_NAMES.get(sc.get('weekday'))}: {('-'.join([ints[0]['start'][:5], ints[-1]['end'][:5]])) if ints else 'Off'}")
            schedules[name] = rows
    top = max(counts.values())
    best = [DAY_NAMES[d] for d, n in counts.items() if n == top] if top else []
    return favs, working, lineup, schedules, best


def favorite_value(c):
    _, working, *_ = _favorite_info(c)
    return working[0]["name"] if working else "None Working"


def favorite_attrs(c):
    favs, working, lineup, schedules, best = _favorite_info(c)
    return {
        "favorites": favs,
        "working_favorites": [w["name"] for w in working],
        "full_lineup": lineup,
        "favorite_schedules": schedules,
        "best_days_to_visit": best,
        "favorite_wait_time": working[0]["wait_time"] if working else "N/A",
    }


def best_day_value(c):
    best = _favorite_info(c)[4]
    return ", ".join(best) if best else "Unknown"


def days_since_value(c):
    return c.days_since_haircut if c.last_haircut_date else None


def next_due_value(c):
    if not c.last_haircut_date:
        return None
    return (c.last_haircut_date + timedelta(days=c.frequency)).date()


def visit_stats_value(c):
    return history_stats(_history(c), _store(c)).get("average_days_between_visits")


def visit_stats_attrs(c):
    return history_stats(_history(c), _store(c))


def roster_value(c):
    return len(_stylists(c)) if _stylists(c) else None


def roster_attrs(c):
    store = _store(c)
    today = store_now(store).date()
    roster = {}
    for s in _stylists(c):
        week = {}
        for row in week_table(s.get("weeklySchedules", []), today):
            week[row["day"]] = row["hours"].replace("Closed", "Off")
        roster[stylist_name(s)] = week
    return {
        "stylists": sorted(roster),
        "roster": roster,
        "live_data": (c.data or {}).get("stylists_live", False),
        "last_updated_with_stylists": c.stylists_updated.isoformat(timespec="minutes") if c.stylists_updated else None,
        "note": "Stylist schedules are only returned by the API while the store is open; the last known roster is kept in between.",
    }


def stylists_today_value(c):
    today = store_now(_store(c)).date()
    names = []
    for s in _stylists(c):
        sc = schedule_for_day(s.get("weeklySchedules", []), today)
        if sc and sc.get("intervals"):
            names.append(stylist_name(s))
    return len(names) if _stylists(c) else None


def stylists_today_attrs(c):
    today = store_now(_store(c)).date()
    working = {}
    for s in _stylists(c):
        sc = schedule_for_day(s.get("weeklySchedules", []), today)
        if sc and sc.get("intervals"):
            working[stylist_name(s)] = fmt_intervals(sc["intervals"])
    return {"working_today": working}


# --------------------------------------------------------------------------- #
# Entity descriptions (keep unique_id suffixes stable for existing entities)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Spec:
    key: str
    unique_suffix: str
    name: str  # format string; {store} replaced with store name
    icon: str
    value: Callable[[Any], Any]
    attrs: Callable[[Any], dict] | None = None
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


SPECS: tuple[Spec, ...] = (
    Spec("wait_time", "wait_time", "Haircut Tracker {store} Wait Time", "mdi:clock-outline", wait_time_value, wait_time_attrs),
    Spec("queue_size", "queue_size", "Haircut Tracker {store} Queue Size", "mdi:account-group", lambda c: len(_items(c)), queue_size_attrs, "people"),
    Spec("store_hours", "store_hours", "Haircut Tracker {store} Store Hours", "mdi:store-clock", store_hours_value, store_hours_attrs),
    Spec("weekly_schedule", "weekly_schedule", "Haircut Tracker {store} Weekly Schedule", "mdi:calendar-week", weekly_schedule_value, weekly_schedule_attrs, "h"),
    Spec("store_status", "store_status", "Haircut Tracker {store} Status", "mdi:store-check", store_status_value, store_status_attrs),
    Spec("expected_start", "expected_start", "Haircut Tracker {store} Expected Start Time", "mdi:timer-sand", expected_start_value),
    Spec("queue_breakdown", "queue_breakdown", "Haircut Tracker {store} Queue Breakdown", "mdi:format-list-numbered", queue_breakdown_value, queue_breakdown_attrs, "people"),
    Spec("checkin_rules", "checkin_rules", "Haircut Tracker {store} Check-In Cutoff", "mdi:clipboard-clock", checkin_rules_value, checkin_rules_attrs, "min"),
    Spec("store_info", "store_info", "Haircut Tracker {store} Store Info", "mdi:information-outline", store_info_value, store_info_attrs),
    Spec("haircut_due", "haircut_due_status", "Haircut Tracker Haircut Due Status", "mdi:scissors-cutting", haircut_due_value, haircut_due_attrs),
    Spec("favorite_stylists", "favorite_stylists_status", "Haircut Tracker Favorite Stylists Status", "mdi:heart-outline", favorite_value, favorite_attrs),
    Spec("best_day", "best_day_to_visit", "Haircut Tracker Best Day to Visit", "mdi:calendar-star", best_day_value),
    Spec("days_since_haircut", "days_since_haircut", "Haircut Tracker Days Since Haircut", "mdi:calendar-clock", days_since_value, None, "d", None, SensorStateClass.MEASUREMENT),
    Spec("next_due_date", "next_due_date", "Haircut Tracker Next Haircut Due", "mdi:calendar-alert", next_due_value, None, None, SensorDeviceClass.DATE),
    Spec("visit_stats", "visit_stats", "Haircut Tracker Average Days Between Visits", "mdi:chart-line", visit_stats_value, visit_stats_attrs, "d"),
    Spec("stylist_roster", "stylist_roster", "Haircut Tracker {store} Stylist Roster", "mdi:account-clock", roster_value, roster_attrs, "stylists"),
    Spec("stylists_today", "stylists_today", "Haircut Tracker {store} Stylists Working Today", "mdi:account-check", stylists_today_value, stylists_today_attrs, "stylists"),
)


def enabled_metrics(entry: ConfigEntry) -> set[str]:
    """Return the set of enabled metric keys for a config entry."""
    has_auth = bool(entry.data.get(CONF_EMAIL) and entry.data.get(CONF_PASSWORD))
    chosen = entry.options.get(CONF_METRICS)
    if chosen is None:
        chosen = default_enabled(has_auth)
    allowed = {m.key for m in available_metrics(has_auth)}
    return set(chosen) & allowed


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the enabled Haircut Tracker sensors."""
    coordinator: HaircutTrackerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    wanted = enabled_metrics(entry)
    store_code = entry.data.get(CONF_STORE_CODE)

    # Remove registry entries for metrics the user switched off
    registry = er.async_get(hass)
    for spec in SPECS:
        if spec.key not in wanted:
            ent_id = registry.async_get_entity_id("sensor", DOMAIN, f"{store_code}_{spec.unique_suffix}")
            if ent_id:
                registry.async_remove(ent_id)

    async_add_entities(
        HaircutTrackerSensor(coordinator, entry, spec) for spec in SPECS if spec.key in wanted
    )


class HaircutTrackerSensor(CoordinatorEntity, SensorEntity):
    """Generic metric sensor driven by a Spec."""

    def __init__(self, coordinator: HaircutTrackerDataUpdateCoordinator, entry: ConfigEntry, spec: Spec) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._store_code = entry.data.get(CONF_STORE_CODE)
        self._store_name = entry.data.get(CONF_STORE_NAME)
        self._attr_name = spec.name.format(store=self._store_name)
        self._attr_unique_id = f"{self._store_code}_{spec.unique_suffix}"
        self._attr_icon = spec.icon
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class

    @property
    def native_value(self):
        try:
            return self._spec.value(self.coordinator)
        except Exception:  # never let one metric break the platform
            return None

    @property
    def extra_state_attributes(self) -> dict | None:
        if not self._spec.attrs:
            return None
        try:
            return self._spec.attrs(self.coordinator)
        except Exception:
            return None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._store_code)},
            "name": f"Haircut Tracker: {self._store_name}",
            "manufacturer": "TheBeardedAdmin",
            "model": "Hair Salon Location",
        }
