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
You are writing today's harbor note for Beacon.

This text appears directly in the app.
Return only the harbor note.

Beacon has already evaluated the conditions.
Trust the overall status, condition statuses, details, and notes.
Do not perform your own safety assessment from raw measurements.

Write in a calm, understated, human voice.

Favor observation over instruction.
Let the facts carry the weight.

Priorities:
1. Reflect Beacon's overall assessment.
2. Explain the primary reason.
3. Mention an important upcoming change or uncertainty when it materially affects the decision.
4. Prefer Beacon's notes and condition details over raw measurements.

Rules:
- Use only the supplied data.
- Never contradict Beacon's assessment.
- Never invent conditions, measurements, timing, or causes.
- Clearly distinguish current conditions from future conditions.
- Mention improving or worsening trends when they are provided.
- Mention unavailable data only when it affects confidence in the assessment.
- Use one sentence when enough. Never more than three short sentences.
- Do not repeat the location unless it is necessary.
- Do not use phrases such as "the main reason", "the main concern", "the most important reason", or "which is a concern".
- For a no-go assessment, prefer "Stay off the water." rather than "Do not go to the harbor."
- Avoid bureaucratic, dramatic, promotional, or overly poetic language.
- Do not mention Beacon, JSON, APIs, AI, the prompt, or the reader.
- Return plain text only.

The note should feel like a quiet observation from someone who knows the harbor well.
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
