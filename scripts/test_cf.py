import json
import os
import sys

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")

MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"

if not ACCOUNT_ID:
    sys.exit("Missing environment variable: CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing environment variable: CF_AI_WORKERS")


url = (
    f"https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/ai/run/{MODEL}"
)

payload = {
    "messages": [
        {
            "role": "system",
            "content": (
                "You write concise status summaries for a Baltimore "
                "Inner Harbor paddling-safety app. Never invent facts."
            ),
        },
        {
            "role": "user",
            "content": (
                "Write one sentence based only on these facts: "
                "overall status is caution; wind is 7 mph; "
                "no nearby lightning is detected; thunderstorms may "
                "develop later this afternoon."
            ),
        },
    ],
    "max_tokens": 100,
    "temperature": 0.2,
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

try:
    body = response.json()
except ValueError:
    print(response.text)
    response.raise_for_status()
    raise

if not response.ok:
    print(json.dumps(body, indent=2))
    response.raise_for_status()

print(json.dumps(body, indent=2))
