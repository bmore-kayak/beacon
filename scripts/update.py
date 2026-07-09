import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path("data/latest.json")

WATERFRONT_URL = "https://services2.arcgis.com/orhH6cbKzLjUCxfK/arcgis/rest/services/Baltimore_Harbor_2024_Water_Quality_Data_with_2023_Historic_Data/FeatureServer/0/query?where=1%3D1&outFields=Site_Name,New_Sample_Date,New_Sample_Status,New_Sample_BacteriaCount,Rain_amount_past7days&returnGeometry=false&f=json"
NOAA_FORECAST_URL = "https://api.weather.gov/zones/forecast/ANZ538/forecast"
NOAA_ALERTS_URL = "https://api.weather.gov/alerts/active?zone=ANZ538"

PASS_LIMIT = 104


def get_json(url):
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Beacon / bmore-kayak"},
    )
    response.raise_for_status()
    return response.json()


def clean_count(value):
    return None if value is None else int(float(value))


def station_status(advisory, count):
    if advisory:
        return "🟢" if "pass" in advisory.lower() else "🔴"
    if count is None:
        return "🟡"
    return "🟢" if count <= PASS_LIMIT else "🔴"


def waterfront_conditions():
    raw = get_json(WATERFRONT_URL)

    stations = []
    for feature in raw.get("features", []):
        a = feature.get("attributes", {})
        count = clean_count(a.get("New_Sample_BacteriaCount"))
        advisory = a.get("New_Sample_Status")

        stations.append({
            "site": a.get("Site_Name"),
            "date": a.get("New_Sample_Date"),
            "status": station_status(advisory, count),
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


def first_period():
    periods = get_json(NOAA_FORECAST_URL).get("properties", {}).get("periods", [])
    return periods[0] if periods else {}


def active_alerts():
    return get_json(NOAA_ALERTS_URL).get("features", [])


def extract_waves(text):
    match = re.search(r"waves?\s+([^.,;]+)", text, re.I)
    return match.group(1).strip() if match else "Pending"


def noaa_conditions():
    period = first_period()
    alerts = active_alerts()

    forecast = period.get("detailedForecast", "")
    wind = period.get("windSpeed", "Pending")
    waves = extract_waves(forecast)

    text = forecast.lower()
    storms = "Thunderstorms possible" if "thunderstorm" in text or "tstm" in text else "None noted"

    alert_names = [
        a.get("properties", {}).get("event", "")
        for a in alerts
    ]

    small_craft = any("Small Craft Advisory" in name for name in alert_names)
    severe_marine = any(
        name in ["Special Marine Warning", "Gale Warning"]
        for name in alert_names
    )

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
            "status": "🔴" if severe_marine else "🟠" if small_craft else "🟢",
            "detail": ", ".join(alert_names) if alert_names else "None",
        },
        "water_temp": {
            "icon": "🌡",
            "label": "Water Temp",
            "status": "🟢",
            "detail": "Pending",
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


def note(water):
    total = len(water["stations"])

    if water["failing"] == 0:
        return f"All sampled stations are passing: {water['passing']}/{total}."

    return (
        f"Water contact is the limiting factor: "
        f"{water['passing']}/{total} passing, "
        f"{water['failing']}/{total} failing."
    )


def main():
    water = waterfront_conditions()
    marine = noaa_conditions()

    conditions = {
        "wind": marine["wind"],
        "waves": marine["waves"],
        "storms": marine["storms"],
        "small_craft": marine["small_craft"],
        "water_contact": water,
        "water_temp": marine["water_temp"],
    }

    data = {
        "location": "Baltimore Harbor",
        "overall": overall_status(conditions),
        "updated": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "conditions": conditions,
        "note": note(water),
    }

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
