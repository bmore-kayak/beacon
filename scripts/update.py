import json
import re
from datetime import datetime
from pathlib import Path

import requests

WATERFRONT_URL = "https://services2.arcgis.com/orhH6cbKzLjUCxfK/arcgis/rest/services/Baltimore_Harbor_2024_Water_Quality_Data_with_2023_Historic_Data/FeatureServer/0/query?where=1%3D1&outFields=Site_Name,New_Sample_Date,New_Sample_Status,New_Sample_BacteriaCount,Rain_amount_past7days&returnGeometry=false&f=json"
MARINE_URL = "https://forecast.weather.gov/shmrn.php?mz=anz538&syn=anz500"

OUT = Path("data/latest.json")
PASS_LIMIT = 104


def fetch_json(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_text(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def clean_count(value):
    return None if value is None else int(float(value))


def score_station(advisory, count):
    if advisory:
        return "🟢" if "pass" in advisory.lower() else "🔴"

    if count is None:
        return "🟡"

    return "🟢" if count <= PASS_LIMIT else "🔴"


def waterfront_conditions():
    raw = fetch_json(WATERFRONT_URL)

    stations = []
    for feature in raw["features"]:
        a = feature["attributes"]

        count = clean_count(a.get("New_Sample_BacteriaCount"))
        advisory = a.get("New_Sample_Status")

        stations.append({
            "site": a.get("Site_Name"),
            "date": a.get("New_Sample_Date"),
            "status": score_station(advisory, count),
            "advisory": advisory,
            "bacteria": count,
        })

    counts = [s["bacteria"] for s in stations if s["bacteria"] is not None]
    passing = sum(s["status"] == "🟢" for s in stations)
    failing = sum(s["status"] == "🔴" for s in stations)

    return {
        "icon": "🦠",
        "label": "Water Contact",
        "status": "🔴" if failing else "🟢",
        "detail": f"{min(counts)}–{max(counts)} MPN" if counts else "Unavailable",
        "passing": passing,
        "failing": failing,
        "stations": stations,
    }


def first_match(patterns, text, fallback="Pending"):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return fallback


def marine_conditions():
    text = fetch_text(MARINE_URL)
    lower = text.lower()

    wind = first_match([
        r"winds?\s+([^\.]+)",
    ], text)

    waves = first_match([
        r"waves?\s+([^\.]+)",
        r"seas?\s+([^\.]+)",
    ], text)

    storms = "Thunderstorms possible" if (
        "tstm" in lower or "thunderstorm" in lower
    ) else "None noted"

    small_craft = "Advisory" if "small craft advisory" in lower else "None"

    return {
        "wind": {
            "icon": "🌬",
            "label": "Wind",
            "status": "🟢",
            "detail": wind,
        },
        "waves": {
            "icon": "🌊",
            "label": "Waves",
            "status": "🟢",
            "detail": waves,
        },
        "storms": {
            "icon": "⛈",
            "label": "Storms",
            "status": "🟠" if storms != "None noted" else "🟢",
            "detail": storms,
        },
        "small_craft": {
            "icon": "🚩",
            "label": "Small Craft",
            "status": "🟠" if small_craft != "None" else "🟢",
            "detail": small_craft,
        },
    }


def overall_status(conditions):
    statuses = [c["status"] for c in conditions.values()]

    if "🔴" in statuses:
        return {"status": "🔴", "label": "Don't Go"}

    if "🟠" in statuses:
        return {"status": "🟠", "label": "Poor"}

    if "🟡" in statuses:
        return {"status": "🟡", "label": "Caution"}

    return {"status": "🟢", "label": "Good"}


def main():
    marine = marine_conditions()
    water_contact = waterfront_conditions()

    conditions = {
        "wind": marine["wind"],
        "waves": marine["waves"],
        "storms": marine["storms"],
        "small_craft": marine["small_craft"],
        "water_contact": water_contact,
        "water_temp": {
            "icon": "🌡",
            "label": "Water Temp",
            "status": "🟢",
            "detail": "Pending",
        },
    }

    data = {
        "location": "Baltimore Harbor",
        "overall": overall_status(conditions),
        "updated": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "conditions": conditions,
        "note": (
            "All sampled stations are passing."
            if water_contact["failing"] == 0
            else f"Water contact is the limiting factor: "
                 f"{water_contact['passing']}/{len(water_contact['stations'])} passing, "
                 f"{water_contact['failing']}/{len(water_contact['stations'])} failing."
        ),
    }

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
