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
Write the short harbor note shown directly in Beacon.

Beacon has already evaluated the conditions. Trust its overall status,
condition statuses, details, and notes. Do not perform a new safety
assessment from the raw measurements.

Return only the note itself.

Write in a calm, natural, understated voice.

Priorities:
1. Reflect Beacon's overall assessment.
2. Explain the most important reason for it.
3. Mention an important upcoming change or uncertainty when relevant.
4. Prefer condition details and notes over interpreting raw numbers.

Rules:
- Use only the supplied data.
- Do not contradict the overall assessment.
- Do not invent or reinterpret conditions.
- Do not assign descriptive labels to measurements unless supplied.
- Clearly distinguish current conditions from future conditions.
- Use one sentence when enough, and no more than three short sentences.
- Avoid bureaucratic, dramatic, promotional, or overly poetic language.
- Do not mention Beacon, JSON, APIs, AI, the prompt, or the reader.
- Return plain text only.
""".strip()


samples = [
    {
        "name": "Good now, storms later",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🟠",
                "label": "Use caution",
            },
            "updated": "2026-07-11 12:00 PM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🟡",
                    "detail": "Storm risk from 6 PM to 1 AM",
                    "items": [
                        {
                            "event": "Hazardous Weather Outlook",
                            "starts": "6 PM",
                            "ends": "1 AM",
                        }
                    ],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🟢",
                    "detail": "5 mph, gusting to 8 mph",
                    "trend": "Increasing after 5 PM",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "🟢",
                    "detail": "0.3 ft",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "🟢",
                    "detail": "None detected within 25 miles",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "🟢",
                    "detail": "Acceptable",
                },
            },
            "notes": [
                "Conditions are favorable now.",
                "Storm risk begins around 6 PM.",
                "Winds are expected to increase after 5 PM.",
            ],
        },
    },
    {
        "name": "Multiple current hazards",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🔴",
                "label": "Do not go",
            },
            "updated": "2026-07-11 4:30 PM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🔴",
                    "detail": "Severe Thunderstorm Warning",
                    "items": [
                        {
                            "event": "Severe Thunderstorm Warning",
                            "ends": "5:15 PM",
                        }
                    ],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🔴",
                    "detail": "16 mph, gusting to 27 mph",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "🟠",
                    "detail": "1.4 ft",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "🔴",
                    "detail": "Nearest strike 8 miles away",
                },
                "rain": {
                    "icon": "🌧️",
                    "label": "Rain",
                    "status": "🔴",
                    "detail": "Heavy rain",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "⚪",
                    "detail": "Unavailable",
                },
            },
            "notes": [
                "A Severe Thunderstorm Warning is in effect.",
                "Lightning is 8 miles from the harbor.",
                "Strong gusts and heavy rain are occurring.",
            ],
        },
    },
    {
        "name": "Calm weather, water advisory",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🔴",
                "label": "Do not go",
            },
            "updated": "2026-07-11 9:00 AM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🟢",
                    "detail": "No active weather alerts",
                    "items": [],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🟢",
                    "detail": "4 mph, gusting to 7 mph",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "🟢",
                    "detail": "0.2 ft",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "🟢",
                    "detail": "None detected within 25 miles",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "🔴",
                    "detail": "Water Contact Advisory",
                    "items": [
                        {
                            "bacteria_count_mpn_100ml": 1354,
                            "sample_age_days": 2,
                        }
                    ],
                },
            },
            "notes": [
                "Weather conditions are favorable.",
                "A Water Contact Advisory remains in effect.",
                "The latest bacteria count is 1,354 MPN/100 mL.",
            ],
        },
    },
    {
        "name": "Conditions improving",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🟠",
                "label": "Use caution",
            },
            "updated": "2026-07-11 2:00 PM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🟢",
                    "detail": "No active alerts",
                    "items": [],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🟠",
                    "detail": "12 mph, gusting to 18 mph",
                    "trend": "Decreasing",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "🟠",
                    "detail": "0.9 ft",
                    "trend": "Subsiding",
                },
                "rain": {
                    "icon": "🌧️",
                    "label": "Rain",
                    "status": "🟡",
                    "detail": "Ending within the next hour",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "🟢",
                    "detail": "None detected within 25 miles",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "🟢",
                    "detail": "Acceptable",
                },
            },
            "notes": [
                "Wind and waves remain elevated.",
                "Conditions are gradually improving.",
                "Rain should end within the next hour.",
            ],
        },
    },
    {
        "name": "Important data unavailable",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🟠",
                "label": "Use caution",
            },
            "updated": "2026-07-11 11:00 AM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🟡",
                    "detail": "Storms possible after 4 PM",
                    "items": [],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🟢",
                    "detail": "6 mph, gusting to 9 mph",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "⚪",
                    "detail": "Unavailable",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "⚪",
                    "detail": "Data unavailable",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "⚪",
                    "detail": "Data unavailable",
                },
            },
            "notes": [
                "Storms are possible after 4 PM.",
                "Lightning and water-quality data are unavailable.",
                "Conditions cannot be fully assessed.",
            ],
        },
    },
    {
        "name": "Calm surface, cold water",
        "data": {
            "location": "Baltimore Inner Harbor",
            "overall": {
                "status": "🟠",
                "label": "Use caution",
            },
            "updated": "2026-03-18 10:00 AM EDT",
            "conditions": {
                "advisories": {
                    "icon": "🚨",
                    "label": "Alerts",
                    "status": "🟢",
                    "detail": "No active alerts",
                    "items": [],
                },
                "wind": {
                    "icon": "💨",
                    "label": "Wind",
                    "status": "🟢",
                    "detail": "3 mph, gusting to 5 mph",
                },
                "waves": {
                    "icon": "🌊",
                    "label": "Waves",
                    "status": "🟢",
                    "detail": "0.2 ft",
                },
                "weather": {
                    "icon": "🌤️",
                    "label": "Weather",
                    "status": "🟢",
                    "detail": "Air temperature 61°F",
                },
                "water_temperature": {
                    "icon": "🌡️",
                    "label": "Water temperature",
                    "status": "🟠",
                    "detail": "48°F",
                },
                "lightning": {
                    "icon": "⚡",
                    "label": "Lightning",
                    "status": "🟢",
                    "detail": "None detected within 25 miles",
                },
                "water_quality": {
                    "icon": "🧪",
                    "label": "Water quality",
                    "status": "🟢",
                    "detail": "Acceptable",
                },
            },
            "notes": [
                "Surface conditions are favorable.",
                "Water temperature remains cold at 48°F.",
            ],
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
        "max_tokens": 120,
        "temperature": 0.1,
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
        print(json.dumps(body, indent=2, ensure_ascii=False))
        continue

    summary = body["result"].get("response")

    if not summary:
        summary = (
            body["result"]["choices"][0]["message"]["content"]
        )

    print()
    print("Harbor note:")
    print(" ".join(summary.split()))
