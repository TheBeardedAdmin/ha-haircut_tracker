"""Known historical/seed schedules for store rosters."""
from __future__ import annotations
from datetime import date, timedelta

# Shift intervals per weekday (1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun)
SEED_ROSTERS = {
    "OH209": [
        {
            "uid": "db0000c3-378a-4207-9271-3caa254a74ae",
            "firstName": "Emily",
            "lastName": "Howard",
            "displayName": "Emily",
            "shifts": {
                1: [("09:00:00", "20:00:00")],
                2: [("12:00:00", "20:00:00")],
                3: [("09:00:00", "17:00:00")],
                4: [],
                5: [("09:00:00", "20:00:00")],
                6: [("09:00:00", "18:00:00")],
                7: [],
            },
        },
        {
            "uid": "76a55cd1-0a82-4721-826c-3c1814ef1c0c",
            "firstName": "Jacob",
            "lastName": "Bell",
            "displayName": "J.B.",
            "shifts": {
                1: [("12:00:00", "20:00:00")],
                2: [],
                3: [("09:00:00", "20:00:00")],
                4: [("09:00:00", "20:00:00")],
                5: [("09:00:00", "20:00:00")],
                6: [("09:00:00", "18:00:00")],
                7: [],
            },
        },
        {
            "uid": "6cdf127f-64af-46a9-a76b-bf59c1b16d56",
            "firstName": "Gery",
            "lastName": "Huelseman",
            "displayName": "Gery",
            "shifts": {
                1: [],
                2: [("14:30:00", "20:00:00")],
                3: [("10:00:00", "17:00:00")],
                4: [],
                5: [],
                6: [],
                7: [],
            },
        },
        {
            "uid": "kenmar-oh209",
            "firstName": "Kenmar",
            "lastName": "",
            "displayName": "Kenmar",
            "shifts": {
                1: [],
                2: [("09:00:00", "17:00:00")],
                3: [("09:00:00", "17:00:00")],
                4: [],
                5: [("09:00:00", "20:00:00")],
                6: [("09:00:00", "18:00:00")],
                7: [("10:00:00", "17:00:00")],
            },
        },
    ]
}


def get_seed_stylists(store_code: str, week_start: date) -> list[dict]:
    """Return seed stylist objects with weeklySchedules populated for the week of week_start (Sunday)."""
    stylists = []
    for item in SEED_ROSTERS.get(store_code, []):
        schedules = []
        for day_offset in range(7):
            cur_date = week_start + timedelta(days=day_offset)
            wday = cur_date.isoweekday()
            intervals = [
                {"start": s, "end": e}
                for s, e in item["shifts"].get(wday, [])
            ]
            schedules.append({
                "date": f"{cur_date.isoformat()}T00:00:00",
                "weekday": wday,
                "intervals": intervals,
            })
        stylists.append({
            "uid": item["uid"],
            "firstName": item["firstName"],
            "lastName": item["lastName"],
            "displayName": item["displayName"],
            "weeklySchedules": schedules,
        })
    return stylists
