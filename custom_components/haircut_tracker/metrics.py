"""Registry of every metric (entity) the integration can expose.

Each metric can be switched on/off from the integration's *Configure* dialog.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    platform: str  # "sensor" | "binary_sensor"
    requires_auth: bool = False
    default: bool = True


METRICS: tuple[Metric, ...] = (
    # ---- Store (public, no account needed) ----
    Metric("wait_time", "Store: Wait time", "sensor"),
    Metric("queue_size", "Store: Queue size (+ live lineup)", "sensor"),
    Metric("store_hours", "Store: Today's hours", "sensor"),
    Metric("weekly_schedule", "Store: Full weekly schedule", "sensor"),
    Metric("store_status", "Store: Status & next opening", "sensor"),
    Metric("expected_start", "Store: Expected service start time", "sensor", default=False),
    Metric("queue_breakdown", "Store: Queue breakdown by status/stylist", "sensor", default=False),
    Metric("checkin_rules", "Store: Check-in rules (cutoff, early arrival)", "sensor", default=False),
    Metric("store_info", "Store: Address, phone, location, links", "sensor", default=False),
    Metric("online_checkin", "Store: Online check-in enabled", "binary_sensor"),
    Metric("see_stylist", "Store: 'See a stylist' enabled", "binary_sensor", default=False),
    Metric("store_open", "Store: Open now", "binary_sensor", default=False),
    # ---- Your account (requires login) ----
    Metric("haircut_due", "You: Haircut due status", "sensor", True),
    Metric("favorite_stylists", "You: Favorite stylists status", "sensor", True),
    Metric("best_day", "You: Best day to visit", "sensor", True),
    Metric("days_since_haircut", "You: Days since last haircut", "sensor", True, False),
    Metric("next_due_date", "You: Next haircut due date", "sensor", True, False),
    Metric("visit_stats", "You: Visit statistics (spend, averages, habits)", "sensor", True, False),
    Metric("stylist_roster", "Store: All stylists & their weekly schedules", "sensor", True),
    Metric("stylists_today", "Store: Stylists working today", "sensor", True, False),
)

METRICS_BY_KEY = {m.key: m for m in METRICS}


def available_metrics(has_auth: bool) -> list[Metric]:
    return [m for m in METRICS if has_auth or not m.requires_auth]


def default_enabled(has_auth: bool) -> list[str]:
    return [m.key for m in available_metrics(has_auth) if m.default]
