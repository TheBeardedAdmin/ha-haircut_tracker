"""Pure helper functions for Haircut Tracker (no Home Assistant dependencies)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


def store_now(store_info: dict) -> datetime:
    """Return the current (naive) wall-clock time in the store's own time zone."""
    tz_name = (store_info or {}).get("timeZone")
    try:
        if tz_name:
            return datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
    except Exception:  # unknown zone name / missing tzdata
        pass
    return datetime.now()


def fmt_time(value: str | None) -> str:
    """'09:00:00' -> '9:00 AM'."""
    if not value:
        return "--"
    try:
        return datetime.strptime(value[:5], "%H:%M").strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return value


def fmt_intervals(intervals: list[dict] | None) -> str:
    """Format a list of start/end intervals as a human readable string."""
    if not intervals:
        return "Closed"
    return ", ".join(f"{fmt_time(i.get('start'))} - {fmt_time(i.get('end'))}" for i in intervals)


def schedule_for_day(schedules: list[dict], day: date) -> dict | None:
    """Find the schedule entry for a calendar date (falls back to weekday match)."""
    iso = day.isoformat()
    for s in schedules or []:
        if str(s.get("date", ""))[:10] == iso:
            return s
    for s in schedules or []:
        if s.get("weekday") == day.isoweekday():
            return s
    return None


def sorted_schedules(schedules: list[dict]) -> list[dict]:
    """Return schedule entries ordered by date (then weekday)."""
    return sorted(schedules or [], key=lambda s: (str(s.get("date", "")), s.get("weekday", 0)))


def week_table(schedules: list[dict], today: date) -> list[dict]:
    """Build a friendly per-day table for the whole schedule window."""
    rows = []
    for s in sorted_schedules(schedules):
        intervals = s.get("intervals") or []
        day_str = str(s.get("date", ""))[:10]
        rows.append({
            "day": DAY_NAMES.get(s.get("weekday"), "?"),
            "date": day_str,
            "open": fmt_time(intervals[0]["start"]) if intervals else None,
            "close": fmt_time(intervals[-1]["end"]) if intervals else None,
            "hours": fmt_intervals(intervals),
            "is_today": day_str == today.isoformat(),
            "special_hours": bool(s.get("exceptionReason")),
            "exception_reason": s.get("exceptionReason"),
        })
    return rows


def hours_open(intervals: list[dict] | None) -> float:
    """Total number of open hours in a list of intervals."""
    total = 0.0
    for i in intervals or []:
        try:
            start = datetime.strptime(i["start"][:5], "%H:%M")
            end = datetime.strptime(i["end"][:5], "%H:%M")
            total += (end - start).seconds / 3600
        except (KeyError, ValueError, TypeError):
            pass
    return round(total, 2)


def is_open_at(store_info: dict, moment: datetime) -> bool:
    """True when a (naive, store-local) moment falls inside opening hours."""
    sched = schedule_for_day(store_info.get("weeklySchedules", []), moment.date())
    if not sched:
        return False
    current = moment.strftime("%H:%M:%S")
    return any(i.get("start", "") <= current <= i.get("end", "") for i in sched.get("intervals") or [])


def is_open_now(store_info: dict) -> bool:
    """True when the store's current local time is inside today's opening hours."""
    return is_open_at(store_info, store_now(store_info))


def next_open_datetime(store_info: dict, after: datetime | None = None) -> datetime | None:
    """Return the next (naive, store-local) opening datetime after `after` (default now)."""
    now = after or store_now(store_info)
    schedules = store_info.get("weeklySchedules", [])
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        sched = schedule_for_day(schedules, day)
        for interval in (sched or {}).get("intervals") or []:
            try:
                opening = datetime.combine(day, datetime.strptime(interval["start"][:8], "%H:%M:%S").time())
            except (KeyError, ValueError):
                continue
            if opening > now:
                return opening
    return None


def stylist_name(stylist: dict) -> str:
    return stylist.get("displayName") or stylist.get("alias") or stylist.get("firstName") or ""


def visit_details(visit: dict) -> dict | None:
    """Flatten a history visit into date/stylist/service/price (None if not parseable)."""
    created = visit.get("createdAtUtc")
    try:
        when = datetime.fromisoformat(str(created).replace("Z", ""))
    except (TypeError, ValueError):
        return None
    stylist = service = None
    price = None
    items = visit.get("clientItems") or []
    if items:
        services = items[0].get("services") or []
        if services:
            first = services[0]
            emp = first.get("employee") or {}
            stylist = emp.get("displayName") or emp.get("firstName")
            service = first.get("serviceName")
            price = (first.get("service") or {}).get("price")
    store = None
    store_resp = (visit.get("storeInfo") or {}).get("response") or []
    if store_resp:
        store = store_resp[0].get("name")
    return {"date": when, "stylist": stylist, "service": service, "price": price, "store": store}


def favorites_from_history(history: list[dict]) -> list[str]:
    """Stylist display names ordered by how often they cut your hair."""
    counts = Counter(d["stylist"] for d in map(visit_details, history or []) if d and d["stylist"])
    return [name for name, _ in counts.most_common()]


def history_stats(history: list[dict], store_info: dict | None = None) -> dict:
    """Aggregate statistics over the full visit history."""
    visits = sorted((d for d in map(visit_details, history or []) if d), key=lambda d: d["date"])
    stats: dict = {"total_visits": len(visits)}
    if not visits:
        return stats

    dates = [v["date"] for v in visits]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if gaps:
        stats["average_days_between_visits"] = round(sum(gaps) / len(gaps), 1)
        stats["shortest_gap_days"] = min(gaps)
        stats["longest_gap_days"] = max(gaps)
        stats["predicted_next_visit"] = (dates[-1] + timedelta(days=round(sum(gaps) / len(gaps)))).date().isoformat()
    stats["first_visit"] = dates[0].date().isoformat()
    stats["last_visit"] = dates[-1].date().isoformat()

    prices = [v["price"] for v in visits if isinstance(v["price"], (int, float))]
    if prices:
        stats["total_spent"] = round(sum(prices), 2)
        stats["average_price"] = round(sum(prices) / len(prices), 2)

    stats["stylist_counts"] = dict(Counter(v["stylist"] for v in visits if v["stylist"]).most_common())
    stats["service_counts"] = dict(Counter(v["service"] for v in visits if v["service"]).most_common())
    stats["store_counts"] = dict(Counter(v["store"] for v in visits if v["store"]).most_common())
    if stats["stylist_counts"]:
        stats["most_frequent_stylist"] = next(iter(stats["stylist_counts"]))
    if stats["service_counts"]:
        stats["most_frequent_service"] = next(iter(stats["service_counts"]))

    # Visit timing, converted to the store's time zone when known
    tz = None
    try:
        tz = ZoneInfo((store_info or {}).get("timeZone") or "")
    except Exception:
        pass
    local = []
    for d in dates:
        if tz:
            from datetime import timezone
            d = d.replace(tzinfo=timezone.utc).astimezone(tz)
        local.append(d)
    weekday_counts = Counter(DAY_NAMES[d.isoweekday()] for d in local)
    stats["visits_by_weekday"] = dict(weekday_counts.most_common())
    stats["favorite_weekday"] = weekday_counts.most_common(1)[0][0]
    stats["favorite_hour"] = Counter(d.hour for d in local).most_common(1)[0][0]
    return stats
