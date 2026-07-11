import json
import os
import sys
from pathlib import Path

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")
MODEL = "@cf/meta/llama-3.1-8b-fast-v2"
LATEST_JSON = Path("data/latest.json")

if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")

if not LATEST_JSON.exists():
    sys.exit(f"Could not find {LATEST_JSON}")

with LATEST_JSON.open("r", encoding="utf-8") as file:
    latest = json.load(file)

system_prompt = """
You write the harbor note for Beacon.

Write as someone quietly observing Baltimore's Inner Harbor.
Favor observation over instruction. Let the facts carry the weight.

Rules:
- Use only the supplied data.
- Never invent conditions, measurements, causes, or timing.
- Write no more than three short sentences.
- Mention only what matters most.
- Clearly separate current conditions from later conditions.
- Preserve uncertainty.
- Avoid bureaucratic, alarmist, or overly poetic language.
- Do not mention JSON, APIs, data processing, or AI.
- Return plain text only.

The note should feel calm, grounded, and human.
""".strip()

url = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/ai/run/{MODEL}"
)

payload = {
    "messages": [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Write Beacon's current harbor note from this data:\n\n"
                + json.dumps(latest, ensure_ascii=False)
            ),
        },
    ],
    "max_tokens": 120,
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

print("HTTP status:", response.status_code)

body = response.json()

if not response.ok:
    print(json.dumps(body, indent=2))
    sys.exit(1)

summary = body["result"].get("response")

if not summary:
    summary = body["result"]["choices"][0]["message"]["content"]

print()
print("Beacon harbor note:")
print(" ".join(summary.split()))
