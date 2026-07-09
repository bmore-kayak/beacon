import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

OUT = Path("data/latest.json")

CBIBS_API_KEY = os.getenv("CBIBS_API_KEY")

CBIBS_URL = "https://mw.buoybay.noaa.gov/api/v1/json/station/BH"
WATERFRONT_URL = "https://services2.arcgis.com/orhH6cbKzLjUCxfK/arcgis/rest/services/Baltimore_Harbor_2024_Water_Quality_Data_with_2023_Historic_Data/FeatureServer/0/query?where=1%3D1&outFields=Site_Name,New_Sample_Date,New_Sample_Status,New_Sample_BacteriaCount,Rain_amount_past7days&returnGeometry=false&f=json"
NWS_POINTS_URL = "https://api.weather.gov/points/39.2826,-76.6107"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone=ANZ538"
NWS_MARINE_TEXT_URL = "https://forecast.weather.gov/shmrn.php?mz=anz538"
COOPS_WIND_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?station=8574680&product=wind&date=latest&units=english&time_zone=lst_ldt&format=json"
NDBC_URL = "https://www.ndbc.noaa.gov/data/realtime2/BLTM2.txt"

PASS_LIMIT = 104
WINDOW_HOURS = 8


def get_json(url, params=None):
    response = requests.get(
        url,
        params=params,
        timeout=30,
        headers={"User-Agent": "Beacon / bmore-kayak"},
    )
    response.raise_for_status()
    return response.json()


def get_text(url):
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Beacon / bmore-kayak"},
    )
    response.raise_for_status()
    return response.text


def c_to_f(c):
    return round((c * 9 / 5) + 32)


def mps_to_kt(mps):
    return round(mps * 1.94384)


def meters_to_ft(meters):
    return round(meters * 3.28084, 1)


def clean_count(value):
    return None if value is None else int(float(value))


def station_status(advisory, count):
    if advisory:
        return "🟢" if "pass" in advisory.lower() else "🔴"
    if count is None:
        return "🟡"
    return "🟢" if count <= PASS_LIMIT else "🔴"


def safe_call(fn, fallback=None):
    try:
        return fn()
    except Exception:
        return fallback


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


def cbibs_measurements():
    if not CBIBS_API_KEY:
        return {}

    raw = get_json(CBIBS_URL, params={"key": CBIBS_API_KEY})
    variables = raw.get("stations", [{}])[0].get("variable", [])

    values = {}
    for item in variables:
        name = item.get("actualName")
        measurements = item.get("measurements", [])
        if name and measurements:
            values[name] = measurements[0].get("value")

    return values


def nws_hourly_periods():
    points = get_json(NWS_POINTS_URL)
    hourly_url = points["properties"]["forecastHourly"]
    periods = get_json(hourly_url)["properties"]["periods"]

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=WINDOW_HOURS)

    return [
        p for p in periods
        if datetime.fromisoformat(p["endTime"]) > now
        and datetime.fromisoformat(p["startTime"]) < end
    ]


def nws_alerts():
    return get_json(NWS_ALERTS_URL).get("features", [])


def coops_wind():
    raw = get_json(COOPS_WIND_URL)
    row = raw.get("data", [{}])[0]

    speed = round(float(row["s"]))
    gust = round(float(row["g"]))
    direction = row.get("dr", "")

    return {
        "icon": "🌬",
        "label": "Wind",
        "status": score_wind(gust),
        "detail": f"{direction} {speed} kt, gusts {gust}",
        "speed_kt": speed,
        "gust_kt": gust,
        "source": "CO-OPS",
    }


def ndbc_water_temp():
    text = get_text(NDBC_URL)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = lines[0].lstrip("#").split()

    for line in lines[2:]:
        values = line.split()
        row = dict(zip(header, values))

        if row.get("WTMP") == "MM":
            continue

        sample_time = datetime(
            int(row["YY"]),
            int(row["MM"]),
            int(row["DD"]),
            int(row["hh"]),
            int(row["mm"]),
            tzinfo=timezone.utc,
        )

        if datetime.now(timezone.utc) - sample_time > timedelta(hours=24):
            return None

        temp_f = c_to_f(float(row["WTMP"]))

        return {
            "icon": "🌡",
            "label": "Water Temp",
            "status": "🟢",
            "detail": f"{temp_f}°F",
            "source": "NDBC",
        }

    return None


def score_wind(gust_kt):
    if gust_kt >= 18:
        return "🔴"
    if gust_kt >= 14:
        return "🟠"
    if gust_kt >= 10:
        return "🟡"
    return "🟢"


def score_waves(waves_ft):
    if waves_ft >= 2:
        return "🔴"
    if waves_ft >= 1.5:
        return "🟠"
    if waves_ft >= 1:
        return "🟡"
    return "🟢"


def cbibs_wind(values):
    speed = values.get("wind_speed")
    gust = values.get("wind_speed_of_gust")

    if speed is None or gust is None:
        return None

    speed_kt = mps_to_kt(float(speed))
    gust_kt = mps_to_kt(float(gust))

    return {
        "icon": "🌬",
        "label": "Wind",
        "status": score_wind(gust_kt),
        "detail": f"{speed_kt} kt, gusts {gust_kt}",
        "speed_kt": speed_kt,
        "gust_kt": gust_kt,
        "source": "CBIBS",
    }


def cbibs_waves(values):
    waves = values.get("sea_surface_wave_significant_height")

    if waves is None:
        return None

    waves_ft = meters_to_ft(float(waves))

    return {
        "icon": "🌊",
        "label": "Waves",
        "status": score_waves(waves_ft),
        "detail": f"{waves_ft} ft",
        "height_ft": waves_ft,
        "source": "CBIBS",
    }


def cbibs_air_temp(values):
    temp = values.get("air_temperature")

    if temp is None:
        return None

    temp_f = c_to_f(float(temp))

    return {
        "icon": "🌡",
        "label": "Air Temp",
        "status": "🟢",
        "detail": f"{temp_f}°F",
        "source": "CBIBS",
    }


def cbibs_water_temp(values):
    temp = values.get("sea_water_temperature")

    if temp is None:
        return None

    temp_f = c_to_f(float(temp))

    return {
        "icon": "🌡",
        "label": "Water Temp",
        "status": "🟢",
        "detail": f"{temp_f}°F",
        "source": "CBIBS",
    }


def forecast_air_temp(periods):
    temps = [p.get("temperature") for p in periods if p.get("temperature") is not None]

    if not temps:
        return {
            "icon": "🌡",
            "label": "Air Temp",
            "status": "🟡",
            "detail": "Unavailable",
        }

    return {
        "icon": "🌡",
        "label": "Air Temp",
        "status": "🟢",
        "detail": f"{temps[0]}°F",
        "source": "NWS",
    }


def forecast_waves():
    text = get_text(NWS_MARINE_TEXT_URL)
    match = re.search(r"waves?\s+([^.,;]+)", text, re.I)

    return {
        "icon": "🌊",
        "label": "Waves",
        "status": "🟢",
        "detail": match.group(1).strip() if match else "Unavailable",
        "source": "NWS",
    }


def storm_condition(periods):
    storm_periods = [
        p for p in periods
        if "thunderstorm" in p.get("shortForecast", "").lower()
        or "thunderstorm" in p.get("detailedForecast", "").lower()
    ]

    if not storm_periods:
        return {
            "icon": "⛈",
            "label": "Storms",
            "status": "🟢",
            "detail": "None noted",
        }

    first = datetime.fromisoformat(storm_periods[0]["startTime"])
    hour = first.strftime("%-I %p")

    return {
        "icon": "⛈",
        "label": "Storms",
        "status": "🟠",
        "detail": f"Possible after {hour}",
    }


def small_craft_condition(alerts):
    names = [
        a.get("properties", {}).get("event", "")
        for a in alerts
        if a.get("properties", {}).get("event")
    ]

    marine_alerts = [
        name for name in names
        if name in [
            "Small Craft Advisory",
            "Special Marine Warning",
            "Gale Warning",
            "Storm Warning",
            "Hurricane Force Wind Warning",
        ]
    ]

    return {
        "icon": "🚩",
        "label": "Small Craft",
        "status": "🔴" if marine_alerts else "🟢",
        "detail": ", ".join(marine_alerts) if marine_alerts else "None",
    }


def unavailable(label):
    return {
        "icon": "🌡",
        "label": label,
        "status": "🟡",
        "detail": "Unavailable",
    }


def marine_conditions():
    cbibs = safe_call(cbibs_measurements, {})
    periods = safe_call(nws_hourly_periods, [])
    alerts = safe_call(nws_alerts, [])

    return {
        "small_craft": small_craft_condition(alerts),
        "wind": cbibs_wind(cbibs) or safe_call(coops_wind) or unavailable("Wind"),
        "waves": cbibs_waves(cbibs) or safe_call(forecast_waves) or unavailable("Waves"),
        "storms": storm_condition(periods),
        "air_temp": cbibs_air_temp(cbibs) or forecast_air_temp(periods),
        "water_temp": cbibs_water_temp(cbibs) or safe_call(ndbc_water_temp) or unavailable("Water Temp"),
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


def note(conditions, water):
    if conditions["small_craft"]["status"] == "🔴":
        return "Marine advisory."

    if conditions["storms"]["status"] == "🔴":
        return "Thunderstorms expected."

    if conditions["storms"]["status"] == "🟠":
        return "Thunderstorms possible."

    if water["status"] == "🔴":
        return "Avoid water contact."

    if conditions["wind"]["status"] == "🔴":
        return "Strong winds."

    if conditions["waves"]["status"] == "🔴":
        return "Rough harbor."

    if conditions["wind"]["status"] == "🟠":
        return "Elevated winds."

    if conditions["waves"]["status"] == "🟠":
        return "Choppy water."

    return "Favorable conditions."


def main():
    water = waterfront_conditions()
    marine = marine_conditions()

    conditions = {
        "small_craft": marine["small_craft"],
        "storms": marine["storms"],
        "wind": marine["wind"],
        "waves": marine["waves"],
        "air_temp": marine["air_temp"],
        "water_temp": marine["water_temp"],
        "water_contact": water,
    }

    data = {
        "location": "Baltimore Harbor",
        "overall": overall_status(conditions),
        "updated": datetime.now(
            ZoneInfo("America/New_York")
        ).strftime("%Y-%m-%d %I:%M %p %Z")
        "conditions": conditions,
        "note": note(conditions, water),
    }

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
