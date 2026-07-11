import json
import os
import sys

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")
MODEL = "@cf/meta/llama-3.1-8b-fast-v2"

if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")


system_prompt = """
You are writing today's harbor note.

This text appears directly in the app.
Return only the note itself.

Write in a calm, understated voice.
Favor observation over instruction.
Let the facts carry the weight.

Use only the supplied data.
Never invent conditions, measurements, causes, or timing.

Write the shortest useful note possible.
Use one sentence when one sentence is enough.
Use two or three short sentences only when the conditions are genuinely mixed.

The note should answer, when relevant:
- What are conditions like now?
- What is likely to change?
- What uncertainty matters?

Avoid bureaucratic phrases, dramatic language, and weather-broadcast style.
Do not mention Beacon, JSON, APIs, AI, your task, or the reader.
Return plain text only.
""".strip()


samples = [
    {
        "name": "Good now, storms later",
        "data": {
            "overall": {
                "status": "caution",
                "label": "Use caution",
            },
            "current": {
                "wind_mph": 5,
                "gust_mph": 8,
                "waves_ft": 0.3,
                "lightning_within_25_miles": False,
                "rain": "none",
            },
            "forecast": {
                "storm_risk": True,
                "storm_window": "6 PM–1 AM",
                "wind_trend": "increasing after 5 PM",
            },
            "water_quality": {
                "status": "acceptable",
            },
        },
    },
    {
        "name": "Multiple current hazards",
        "data": {
            "overall": {
                "status": "no_go",
                "label": "Stay off the water",
            },
            "current": {
                "wind_mph": 16,
                "gust_mph": 27,
                "waves_ft": 1.4,
                "lightning_nearest_miles": 8,
                "rain": "heavy",
            },
            "alerts": [
                "Severe Thunderstorm Warning",
            ],
            "water_quality": {
                "status": "unknown",
            },
        },
    },
    {
        "name": "Mixed water quality and weather",
        "data": {
            "overall": {
                "status": "no_go",
                "label": "Stay off the water",
            },
            "current": {
                "wind_mph": 4,
                "gust_mph": 7,
                "waves_ft": 0.2,
                "lightning_within_25_miles": False,
                "rain": "none",
            },
            "forecast": {
                "storm_risk": False,
            },
            "water_quality": {
                "status": "advisory",
                "bacteria_count_mpn_100ml": 1354,
                "sample_age_days": 2,
            },
        },
    },
    {
        "name": "Conditions improving",
        "data": {
            "overall": {
                "status": "caution",
                "label": "Use caution",
            },
            "current": {
                "wind_mph": 12,
                "gust_mph": 18,
                "waves_ft": 0.9,
                "lightning_within_25_miles": False,
                "rain": "ending",
            },
            "trend": {
                "wind": "decreasing",
                "waves": "subsiding",
                "rain": "ending within the next hour",
            },
            "water_quality": {
                "status": "acceptable",
            },
        },
    },
    {
        "name": "Uncertain data",
        "data": {
            "overall": {
                "status": "caution",
                "label": "Use caution",
            },
            "current": {
                "wind_mph": 6,
                "gust_mph": 9,
                "waves_ft": None,
                "lightning_data": "unavailable",
                "rain": "none",
            },
            "forecast": {
                "storm_risk": "possible after 4 PM",
            },
            "water_quality": {
                "status": "unavailable",
            },
        },
    },
    {
        "name": "Calm but cold water",
        "data": {
            "overall": {
                "status": "caution",
                "label": "Use caution",
            },
            "current": {
                "wind_mph": 3,
                "gust_mph": 5,
                "waves_ft": 0.2,
                "lightning_within_25_miles": False,
                "rain": "none",
                "air_temperature_f": 61,
                "water_temperature_f": 48,
            },
            "forecast": {
                "storm_risk": False,
            },
            "water_quality": {
                "status": "acceptable",
            },
        },
    },
]


url = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/ai/run/{MODEL}"
)


for sample in samples:
    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    sample["data"],
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": 140,
        "temperature": 0.15,
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    print()
    print("=" * 60)
    print(sample["name"])
    print("HTTP status:", response.status_code)

    body = response.json()

    if not response.ok:
        print(json.dumps(body, indent=2))
        continue

    summary = body["result"].get("response")

    if not summary:
        summary = (
            body["result"]["choices"][0]["message"]["content"]
        )

    print("Input:")
    print(json.dumps(sample["data"], indent=2, ensure_ascii=False))
    print()
    print("Harbor note:")
    print(" ".join(summary.split()))
