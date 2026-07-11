import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")

MODEL = "@cf/meta/llama-3.1-8b-fast-v2"

LATITUDE = 39.285
LONGITUDE = -76.612

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")


params = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "hourly": ",".join(
        [
            "precipitation_probability",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
        ]
    ),
    "forecast_hours": 6,
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
    "timezone": "America/New_York",
    "models": "gfs_hrrr",
}


weather_response = requests.get(
    OPEN_METEO_URL,
    params=params,
    timeout=30,
)

print("Open-Meteo status:", weather_response.status_code)
weather_response.raise_for_status()

weather = weather_response.json()
hourly = weather["hourly"]


def format_hour(value: str) -> str:
    timestamp = datetime.fromisoformat(value)
    return timestamp.strftime("%-I %p")


hours = []

for index, timestamp in enumerate(hourly["time"]):
    hours.append(
        {
            "time": format_hour(timestamp),
            "wind_mph": hourly["wind_speed_10m"][index],
            "gust_mph": hourly["wind_gusts_10m"][index],
            "wind_direction_degrees":
                hourly["wind_direction_10m"][index],
            "rain_chance_percent":
                hourly["precipitation_probability"][index],
            "forecast_rain_in":
                hourly["precipitation"][index],
            "weather_code":
                hourly["weather_code"][index],
        }
    )


first = hours[0]

highest_wind = max(
    hours,
    key=lambda hour: hour["wind_mph"],
)

highest_gust = max(
    hours,
    key=lambda hour: hour["gust_mph"],
)

highest_rain_chance = max(
    hours,
    key=lambda hour: hour["rain_chance_percent"],
)

total_forecast_rain = round(
    sum(hour["forecast_rain_in"] for hour in hours),
    3,
)


derived_changes = []


if highest_wind["wind_mph"] > first["wind_mph"] + 2:
    derived_changes.append(
        f"Wind rises from {first['wind_mph']} mph at "
        f"{first['time']} to {highest_wind['wind_mph']} mph at "
        f"{highest_wind['time']}."
    )
elif highest_wind["wind_mph"] < first["wind_mph"] - 2:
    derived_changes.append(
        f"Wind decreases from {first['wind_mph']} mph at "
        f"{first['time']} to {highest_wind['wind_mph']} mph at "
        f"{highest_wind['time']}."
    )
else:
    derived_changes.append(
        "Wind speed remains relatively steady during the forecast period."
    )


if highest_gust["gust_mph"] > first["gust_mph"] + 3:
    derived_changes.append(
        f"Gusts increase from {first['gust_mph']} mph at "
        f"{first['time']} to {highest_gust['gust_mph']} mph at "
        f"{highest_gust['time']}."
    )
else:
    derived_changes.append(
        f"The strongest forecast gust is "
        f"{highest_gust['gust_mph']} mph at "
        f"{highest_gust['time']}."
    )


derived_changes.append(
    f"Rain probability peaks at "
    f"{highest_rain_chance['rain_chance_percent']}% around "
    f"{highest_rain_chance['time']}."
)


if total_forecast_rain == 0:
    derived_changes.append(
        "No measurable rain is forecast during this period."
    )
else:
    derived_changes.append(
        f"Forecast rainfall totals approximately "
        f"{total_forecast_rain} inches during this period."
    )


ai_input = {
    "forecast_updated": datetime.now(
        ZoneInfo("America/New_York")
    ).strftime("%-I:%M %p"),
    "period": "next 6 hours",
    "hours": hours,
    "derived_changes": derived_changes,
}


print()
print("Forecast input:")
print(
    json.dumps(
        ai_input,
        indent=2,
        ensure_ascii=False,
    )
)


system_prompt = """
Write a short note about meaningful changes over the next six hours.

Use the supplied derived changes as the source of truth.
Do not reinterpret the raw values.
Do not convert, alter, or invent times.
Do not describe wind, rain, or other measurements with qualitative labels
unless those labels are explicitly supplied.

Focus on:
- when conditions noticeably worsen or improve,
- the strongest wind or gust period,
- meaningful rain timing.

Mention only what matters most.
Use one or two short sentences.
Write in a calm, clear, understated voice.

Do not mention JSON, APIs, AI, the prompt, or the reader.
Return only the note.
""".strip()


cloudflare_url = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/ai/run/{MODEL}"
)

payload = {
    "messages": [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": json.dumps(
                ai_input,
                ensure_ascii=False,
            ),
        },
    ],
    "max_tokens": 100,
    "temperature": 0.1,
}


ai_response = requests.post(
    cloudflare_url,
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=30,
)

print()
print("Cloudflare status:", ai_response.status_code)

body = ai_response.json()

if not ai_response.ok:
    print(
        json.dumps(
            body,
            indent=2,
            ensure_ascii=False,
        )
    )
    sys.exit(1)


summary = body["result"].get("response")

if not summary:
    summary = (
        body["result"]["choices"][0]
        ["message"]["content"]
    )


print()
print("Harbor forecast note:")
print(" ".join(summary.split()))
