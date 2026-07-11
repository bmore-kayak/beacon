import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

OUT = Path("data/latest.json")
HISTORY = Path("data/history.jsonl")

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

    sample_dates = [
        s["date"]
        for s in stations
        if s["date"] is not None
    ]
    
    latest_sample = (
        datetime.fromtimestamp(
            max(sample_dates) / 1000,
            tz=ZoneInfo("America/New_York"),
        ).isoformat()
        if sample_dates else None
    )
    
    return {
        "icon": "🦠",
        "label": "Bacteria",
        "status": "🔴" if failing else "🟢",
        "detail": f"{min(counts)}–{max(counts)} MPN" if counts else "Unavailable",
    
        "source": {
            "provider": "Waterfront Partnership",
            "updated": latest_sample,
        },
    
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
    direction = row.get("d")

    return {
        "icon": "🌬",
        "label": "Wind",
        "status": score_wind(gust),
        "detail": f"{speed} kt, gusts {gust}",
        "speed_kt": speed,
        "gust_kt": gust,
        "direction_deg": (
            round(float(direction), 1)
            if direction not in (None, "")
            else None
        ),
        "source": {
            "provider": "NOAA CO-OPS",
            "location": "Baltimore",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
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
            "source": {
                "provider": "NOAA NDBC",
                "location": "BLTM2",
                "updated": sample_time.astimezone(
                    ZoneInfo("America/New_York")
                ).isoformat(),
            },
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
    direction = values.get("wind_from_direction")

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
        "direction_deg": (
            round(float(direction), 1)
            if direction is not None
            else None
        ),
        "source": {
            "provider": "NOAA CBIBS",
            "location": "Baltimore Harbor Buoy",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
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
        "source": {
            "provider": "NOAA CBIBS",
            "location": "Baltimore Harbor Buoy",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
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
        "source": {
            "provider": "NOAA CBIBS",
            "location": "Baltimore Harbor Buoy",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
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
        "source": {
            "provider": "NOAA CBIBS",
            "location": "Baltimore Harbor Buoy",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
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
        "source": {
            "provider": "National Weather Service",
            "location": "Baltimore Harbor",
            "updated": periods[0]["startTime"],
        },
    }


def forecast_waves():
    text = get_text(NWS_MARINE_TEXT_URL)
    match = re.search(r"waves?\s+([^.,;]+)", text, re.I)

    return {
        "icon": "🌊",
        "label": "Waves",
        "status": "🟢",
        "detail": match.group(1).strip() if match else "Unavailable",
        "source": {
            "provider": "National Weather Service",
            "location": "ANZ538",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
    }


def storm_condition(periods):
    storm_periods = [
        p for p in periods
        if "thunderstorm" in p.get("shortForecast", "").lower()
        or "thunderstorm" in p.get("detailedForecast", "").lower()
    ]

    source = {
        "provider": "National Weather Service",
        "location": "Baltimore Inner Harbor",
        "updated": periods[0]["startTime"] if periods else None,
    }

    if not storm_periods:
        return {
            "icon": "⛈",
            "label": "Storms",
            "status": "🟢",
            "detail": "None noted",
            "source": source,
        }

    now = datetime.now(timezone.utc)
    first_start = datetime.fromisoformat(storm_periods[0]["startTime"])
    window_end = datetime.fromisoformat(storm_periods[0]["endTime"])

    # Extend through consecutive hourly storm periods.
    for period in storm_periods[1:]:
        period_start = datetime.fromisoformat(period["startTime"])

        if period_start > window_end:
            break

        window_end = datetime.fromisoformat(period["endTime"])

    start_text = first_start.strftime("%-I %p")
    end_text = window_end.strftime("%-I %p")

    if now < first_start - timedelta(hours=2):
        status = "🟡"
        detail = f"Possible after {start_text}"
    else:
        status = "🟠"
        detail = f"Storm risk {start_text}–{end_text}"

    return {
        "icon": "⛈",
        "label": "Storms",
        "status": status,
        "detail": detail,
        "starts": first_start.isoformat(),
        "ends": window_end.isoformat(),
        "source": source,
    }

def marine_text_alert_names():
    text = safe_call(lambda: get_text(NWS_MARINE_TEXT_URL), "") or ""
    upper = text.upper()

    alerts = []

    checks = [
        ("Special Marine Warning", "SPECIAL MARINE WARNING"),
        ("Storm Warning", "STORM WARNING"),
        ("Gale Warning", "GALE WARNING"),
        ("Hurricane Force Wind Warning", "HURRICANE FORCE WIND WARNING"),
        ("Small Craft Advisory", "SMALL CRAFT ADVISORY"),
        ("Tornado Warning", "TORNADO WARNING"),
        ("Severe Thunderstorm Warning", "SEVERE THUNDERSTORM WARNING"),
        ("Tornado Watch", "TORNADO WATCH"),
        ("Severe Thunderstorm Watch", "SEVERE THUNDERSTORM WATCH"),
        ("Flash Flood Warning", "FLASH FLOOD WARNING"),
        ("Flash Flood Watch", "FLASH FLOOD WATCH"),
        ("Hazardous Weather Outlook", "HAZARDOUS WEATHER OUTLOOK"),
    ]

    for label, phrase in checks:
        if phrase in upper:
            alerts.append(label)

    return alerts
    
def advisory_condition(api_alerts, marine_text_names=None):
    marine_text_names = marine_text_names or []

    priority = [
        "Tornado Warning",
        "Special Marine Warning",
        "Severe Thunderstorm Warning",
        "Storm Warning",
        "Gale Warning",
        "Hurricane Force Wind Warning",
        "Small Craft Advisory",
        "Flash Flood Warning",
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Flash Flood Watch",
        "Hazardous Weather Outlook",
    ]

    red_events = {
        "Tornado Warning",
        "Special Marine Warning",
        "Severe Thunderstorm Warning",
        "Storm Warning",
        "Gale Warning",
        "Hurricane Force Wind Warning",
        "Small Craft Advisory",
        "Flash Flood Warning",
    }

    orange_events = {
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Flash Flood Watch",
    }

    items_by_event = {}

    # Official NWS Alerts API results.
    for alert in api_alerts:
        properties = alert.get("properties", {})
        event = properties.get("event")

        if event not in priority:
            continue

        items_by_event[event] = {
            "event": event,
            "ends": (
                properties.get("ends")
                or properties.get("expires")
            ),
        }

    # Products found in the marine forecast page, including HWO.
    for event in marine_text_names:
        if event in priority and event not in items_by_event:
            items_by_event[event] = {
                "event": event,
                "ends": None,
            }

    items = [
        items_by_event[event]
        for event in priority
        if event in items_by_event
    ]

    names = [item["event"] for item in items]

    if any(name in red_events for name in names):
        status = "🔴"
    elif any(name in orange_events for name in names):
        status = "🟠"
    elif names:
        status = "🟡"
    else:
        status = "🟢"

    return {
        "icon": "🚨",
        "label": "Alerts",
        "status": status,
        "detail": names[0] if names else "None",
        "items": items,
        "source": {
            "provider": "National Weather Service",
            "location": "ANZ538",
            "updated": datetime.now(
                ZoneInfo("America/New_York")
            ).isoformat(),
        },
    }

def format_alert(item):
    event = item.get("event")
    ends = item.get("ends")

    if not event:
        return None

    if ends:
        end_time = datetime.fromisoformat(ends).strftime("%-I:%M %p")
        return f"{event} until {end_time}."

    return f"{event}."
    
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
    marine_alert_names = safe_call(marine_text_alert_names, [])

    return {
        "advisories": advisory_condition(alerts, marine_alert_names),
        "wind": cbibs_wind(cbibs) or safe_call(coops_wind) or unavailable("Wind"),
        "waves": cbibs_waves(cbibs) or safe_call(forecast_waves) or unavailable("Waves"),
        "storms": storm_condition(periods),
        "air_temp": cbibs_air_temp(cbibs) or forecast_air_temp(periods),
        "water_temp": cbibs_water_temp(cbibs) or safe_call(ndbc_water_temp) or unavailable("Water Temp"),
    }


def overall_status(conditions):
    statuses = [c["status"] for c in conditions.values()]

    if "🔴" in statuses:
        return {"status": "🔴", "label": "Don't go"}
    if "🟠" in statuses:
        return {"status": "🟠", "label": "Use caution"}
    if "🟡" in statuses:
        return {"status": "🟡", "label": "Heads up"}

    return {"status": "🟢", "label": "Good conditions"}


def note(conditions, water):
    advisories = conditions["advisories"].get("items", [])

    actionable_advisories = [
        advisory
        for advisory in advisories
        if advisory.get("properties", {}).get("event") != "Hazardous Weather Outlook"
    ]
    
    if actionable_advisories:
        lines = [
            formatted
            for item in actionable_advisories
            if (formatted := format_alert(item))
        ]
    
        return "\n".join(lines)

    if conditions["storms"]["status"] == "🔴":
        return conditions["storms"]["detail"] + "."
    
    if conditions["storms"]["status"] == "🟠":
        return conditions["storms"]["detail"] + "."

    if conditions["storms"]["status"] == "🟡":
        return conditions["storms"]["detail"] + "."
        
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

    return ""

def append_history(data):
    conditions = data["conditions"]

    def number(value):
        if value is None:
            return None

        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else None

    def source_info(condition):
        source = condition.get("source") or {}

        return {
            "provider": source.get("provider"),
            "location": source.get("location"),
            "observed": source.get("updated"),
        }

    wind = conditions["wind"]
    waves = conditions["waves"]
    air_temp = conditions["air_temp"]
    water_temp = conditions["water_temp"]
    bacteria = conditions["bacteria"]
    advisories = conditions["advisories"]

    history = {
        "schema": 1,
        "timestamp": datetime.now(
            ZoneInfo("America/New_York")
        ).isoformat(),

        "overall": data["overall"]["status"],

        "advisories": {
            "status": advisories["status"],
            "items": advisories.get("items", []),
            "source": source_info(advisories),
        },

        "storms": {
            "status": conditions["storms"]["status"],
            "detail": conditions["storms"]["detail"],
            "source": source_info(conditions["storms"]),
        },

        "wind": {
            "status": wind["status"],
            "speed_kt": wind.get("speed_kt")
                or number(wind.get("detail")),
            "gust_kt": wind.get("gust_kt")
                or (
                    number(wind["detail"].split("gusts", 1)[1])
                    if "gusts" in wind.get("detail", "")
                    else None
                ),
            "direction_deg": wind.get("direction_deg"),
            "source": source_info(wind),
        },

        "waves": {
            "status": waves["status"],
            "height_ft": waves.get("height_ft")
                or number(waves.get("detail")),
            "source": source_info(waves),
        },

        "air_temp": {
            "status": air_temp["status"],
            "temp_f": air_temp.get("temp_f")
                or number(air_temp.get("detail")),
            "source": source_info(air_temp),
        },

        "water_temp": {
            "status": water_temp["status"],
            "temp_f": water_temp.get("temp_f")
                or number(water_temp.get("detail")),
            "source": source_info(water_temp),
        },

        "bacteria": {
            "status": bacteria["status"],
            "passing": bacteria["passing"],
            "failing": bacteria["failing"],
            "stations": bacteria["stations"],
            "source": source_info(bacteria),
        },
    }

    with HISTORY.open("a", encoding="utf-8") as file:
        file.write(json.dumps(history) + "\n")


def main():
    water = waterfront_conditions()
    marine = marine_conditions()

    conditions = {
        "advisories": marine["advisories"],
        "storms": marine["storms"],
        "wind": marine["wind"],
        "waves": marine["waves"],
        "air_temp": marine["air_temp"],
        "water_temp": marine["water_temp"],
        "bacteria": water,
    }

    data = {
        "location": "Baltimore Inner Harbor",
        "overall": overall_status(conditions),
        "updated": datetime.now(
            ZoneInfo("America/New_York")
        ).strftime("%Y-%m-%d %I:%M %p %Z"),
        "conditions": conditions,
        "note": note(conditions, water),
    }

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")

    append_history(data)


if __name__ == "__main__":
    main()
