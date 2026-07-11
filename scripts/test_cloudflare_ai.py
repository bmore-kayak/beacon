import json
import os
import sys
from datetime import datetime

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")
MODEL = "@cf/meta/llama-3.1-8b-fast-v2"

if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")


# Approximate Inner Harbor coordinates.
LATITUDE = 39.285
LONGITUDE = -76.612

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "hourly": ",".join(
        [
            "temperature_2m",
            "precipitation_probability",
            "precipitation",
            "rain",
            "showers",
            "weather_code",
            "cloud_cover",
            "visibility",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "cape",
        ]
    ),
    "forecast_hours": 12,
    "temperature_unit": "fahrenheit",
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

print()
print("Raw Open-Meteo JSON:")
print(json.dumps(weather, indent=2))


hourly = weather["hourly"]
hour_count = min(6, len(hourly["time"]))

next_hours = []

for index in range(hour_count):
    next_hours.append(
        {
            "time": hourly["time"][index],
            "temperature_f": hourly["temperature_2m"][index],
            "precipitation_probability_percent":
                hourly["precipitation_probability"][index],
            "precipitation_in": hourly["precipitation"][index],
            "rain_in": hourly["rain"][index],
            "showers_in": hourly["showers"][index],
            "weather_code": hourly["weather_code"][index],
            "cloud_cover_percent": hourly["cloud_cover"][index],
            "visibility_ft": hourly["visibility"][index],
            "wind_mph": hourly["wind_speed_10m"][index],
            "gust_mph": hourly["wind_gusts_10m"][index],
            "wind_direction_degrees":
                hourly["wind_direction_10m"][index],
            "cape_j_kg": hourly["cape"][index],
        }
    )


ai_input = {
    "location": "Baltimore Inner Harbor",
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "forecast_type": "hourly",
    "hours": next_hours,
}


system_prompt = """
Write a short harbor forecast note from the supplied hourly forecast.

This is an experimental forecast summary, not Beacon's final safety
assessment.

Return only the note itself.

Focus on:
- what conditions are like during the first hour,
- meaningful changes over the following hours,
- the timing of rain, storms, wind, or reduced visibility.

Rules:
- Use only the supplied information.
- Do not claim that conditions are safe or unsafe.
- Do not infer lightning from weather codes, CAPE, clouds, or rain.
- Do not invent storm timing.
- Do not describe a trend unless the hourly values support it.
- Prefer meaningful changes over listing every measurement.
- Use one to three short sentences.
- Clearly distinguish current or near-term conditions from later conditions.
- Avoid bureaucratic, dramatic, or weather-broadcast language.
- Do not mention JSON, APIs, AI, or the prompt.
- Return plain text only.
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
    "max_tokens": 140,
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
    print(json.dumps(body, indent=2))
    sys.exit(1)

summary = body["result"].get("response")

if not summary:
    summary = (
        body["result"]["choices"][0]["message"]["content"]
    )

print()
print("Forecast input:")
print(json.dumps(ai_input, indent=2))

print()
print("Harbor forecast note:")
print(" ".join(summary.split()))
