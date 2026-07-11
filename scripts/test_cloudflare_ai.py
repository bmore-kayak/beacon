import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")

MODEL = "@cf/meta/llama-3.1-8b-fast-v2"

EVENTS_URL = (
    "https://cantonkayakclub.com/"
    "wp-json/tribe/events/v1/events"
)

STATE_FILE = Path("data/club_event_state.json")

TIMEZONE = ZoneInfo("America/New_York")
WINDOW_DAYS = 7

MAX_DESCRIPTION_CHARS = 5000
MAX_TITLE_CHARS = 90
MAX_SUMMARY_CHARS = 180


if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")


SYSTEM_PROMPT = """
Write a short app entry for an upcoming Canton Kayak Club event.

Return JSON only:

{
  "title": "short clear title",
  "summary": "one short useful sentence",
  "notice": true or false
}

Use only the supplied event information.

Set notice to true when the event indicates:
- a closure,
- reduced kayak or equipment availability,
- restricted access,
- cancellation or a material change,
- unusual vessel traffic,
- a marine restriction,
- or another broader water-safety concern.

Otherwise set notice to false.

Fells Point or Bond Street Wharf orientation and training should normally
be marked as a notice because club kayaks are used during those sessions.

Writing rules:
- Begin the title with the location when a location is known.
- Describe the activity or practical effect after the location.
- Do not include dates or times in the title or summary; they are displayed separately.
- Do not repeat the full venue name when a shorter location name is clear.
- Keep the title under 60 characters.
- Keep the summary to one short factual sentence under 140 characters.
- For notices, describe the practical effect on members.
- For ordinary events, summarize the activity, skill level, or notable destination.
- Do not include RSVP limits unless they are the main useful detail.
- Do not use promotional phrases such as "join us," "lovely," or "memorable."
- Do not invent facts, restrictions, closures, or traffic impacts.
""".strip()


def clean_html(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_local_datetime(value):
    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=TIMEZONE)


def fetch_events(now):
    end = now + timedelta(days=WINDOW_DAYS)

    response = requests.get(
        EVENTS_URL,
        params={
            "per_page": 50,
            "start_date": now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "end_date": end.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "status": "publish",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("events", [])


def normalize_event(raw):
    venue = raw.get("venue") or {}

    if not isinstance(venue, dict):
        venue = {}

    categories = raw.get("categories") or []

    return {
        "event_id": raw.get("id"),
        "title": clean_html(raw.get("title")),
        "description": clean_html(
            raw.get("description")
        )[:MAX_DESCRIPTION_CHARS],
        "start": raw.get("start_date"),
        "end": raw.get("end_date"),
        "modified_utc": raw.get("modified_utc"),
        "url": raw.get("url"),
        "venue": {
            "name": clean_html(
                venue.get("venue")
            ),
            "address": clean_html(
                venue.get("address")
            ),
            "city": clean_html(
                venue.get("city")
            ),
            "slug": venue.get("slug"),
        },
        "categories": [
            {
                "name": clean_html(
                    category.get("name")
                ),
                "slug": category.get("slug"),
            }
            for category in categories
        ],
    }


def fingerprint(event):
    relevant_fields = {
        "title": event["title"],
        "description": event["description"],
        "start": event["start"],
        "end": event["end"],
        "venue": event["venue"],
        "categories": event["categories"],
    }

    encoded = json.dumps(
        relevant_fields,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def parse_ai_json(value):
    if isinstance(value, dict):
        return value

    text = str(value or "").strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError(
            "Cloudflare did not return JSON"
        )

    return json.loads(text[start : end + 1])


def classify_event(event):
    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{ACCOUNT_ID}/ai/run/{MODEL}"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": (
                f"Bearer {API_TOKEN}"
            ),
            "Content-Type": "application/json",
        },
        json={
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        event,
                        ensure_ascii=False,
                    ),
                },
            ],
            "max_tokens": 180,
            "temperature": 0,
        },
        timeout=30,
    )

    response.raise_for_status()

    result = response.json().get(
        "result",
        {},
    )

    content = result.get("response")

    if not content:
        content = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )

    return parse_ai_json(content)


def validate_ai_result(result):
    title = str(
        result.get("title") or ""
    ).strip()

    summary = str(
        result.get("summary") or ""
    ).strip()

    notice = bool(result.get("notice"))

    if not title:
        raise ValueError(
            "AI result is missing title"
        )

    if not summary:
        raise ValueError(
            "AI result is missing summary"
        )

    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(
            "AI title is too long"
        )

    if len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError(
            "AI summary is too long"
        )

    return {
        "title": title,
        "summary": summary,
        "notice": notice,
    }


now = datetime.now(TIMEZONE)

state = load_state()
events = [
    normalize_event(raw)
    for raw in fetch_events(now)
]

items = []

print(f"Upcoming events found: {len(events)}")


for event in events:
    event_id = str(event["event_id"])
    current_fingerprint = fingerprint(event)

    saved = state.get(event_id)

    if (
        saved
        and saved.get("fingerprint")
        == current_fingerprint
    ):
        ai_result = saved["ai_result"]
        source = "cached"

    else:
        try:
            ai_result = validate_ai_result(
                classify_event(event)
            )
        except (
            requests.RequestException,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            print(
                f"{event['title']}: failed: {exc}"
            )
            continue

        state[event_id] = {
            "fingerprint": current_fingerprint,
            "source_modified_at": (
                event["modified_utc"]
            ),
            "reviewed_at": now.isoformat(
                timespec="seconds"
            ),
            "ai_result": ai_result,
        }

        source = "cloudflare"

    print(
        f"{event['title']}: "
        f"{'notice' if ai_result['notice'] else 'event'} "
        f"({source})"
    )

    starts_at = parse_local_datetime(
        event["start"]
    )

    ends_at = parse_local_datetime(
        event["end"]
    )

    items.append(
        {
            "event_id": event["event_id"],
            "title": ai_result["title"],
            "summary": ai_result["summary"],
            "notice": ai_result["notice"],
            "location": (
                event["venue"]["name"]
                or None
            ),
            "address": (
                event["venue"]["address"]
                or None
            ),
            "starts_at": starts_at.isoformat(
                timespec="seconds"
            ),
            "ends_at": ends_at.isoformat(
                timespec="seconds"
            ),
            "source_modified_at": (
                event["modified_utc"]
            ),
            "reviewed_at": state[event_id][
                "reviewed_at"
            ],
            "source_url": event["url"],
        }
    )


save_state(state)

items.sort(
    key=lambda item: item["starts_at"]
)


latest_fragment = {
    "club": {
        "icon": "🛶",
        "label": "Club",
        "detail": (
            f"{len(items)} upcoming event"
            if len(items) == 1
            else f"{len(items)} upcoming events"
            if items
            else "No upcoming events"
        ),
        "items": items,
        "source": {
            "label": "Canton Kayak Club",
            "url": (
                "https://cantonkayakclub.com/"
                "events/"
            ),
        },
        "reviewed_at": now.isoformat(
            timespec="seconds"
        ),
    }
}


print()
print(
    json.dumps(
        latest_fragment,
        indent=2,
        ensure_ascii=False,
    )
)
