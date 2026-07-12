import hashlib
import html
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")

MODEL = "@cf/meta/llama-3.1-8b-fast-v2"
PROMPT_VERSION = 1

EVENTS_URL = (
    "https://cantonkayakclub.com/"
    "wp-json/tribe/events/v1/events"
)
EVENTS_PAGE_URL = "https://cantonkayakclub.com/events/"

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "data" / "club_event_state.json"

TIMEZONE = ZoneInfo("America/New_York")
WINDOW_DAYS = 7

MAX_DESCRIPTION_CHARS = 5000
MAX_TITLE_CHARS = 60
MAX_SUMMARY_CHARS = 140


SYSTEM_PROMPT = """
Summarize an upcoming Canton Kayak Club event for Beacon.

Return only valid JSON:

{
  "notice": true,
  "title": "...",
  "summary": "..."
}

Set notice to true when the event may affect members beyond the event itself,
including:

- dock, launch, kayak, or equipment availability,
- a closure or access restriction,
- a cancellation or material operational change,
- unusual vessel traffic,
- a marine restriction,
- or another broader water-safety concern.

Fells Point or Bond Street Wharf orientation and training should normally
be a notice because club kayaks are used during those sessions.

Otherwise set notice to false.

Writing rules:

- Use only the supplied event information.
- When a recognizable location exists, begin the title with:
  "<Location>: "
- Use a short, natural location name.
- If no location can be determined, omit the location prefix.
- Do not include dates or times in the title or summary.
- Do not repeat RSVP limits, contact details, or weather reminders.
- Do not begin the summary with "Join."
- Keep the title under 60 characters.
- Keep the summary to one factual sentence under 140 characters.
- Do not invent closures, restrictions, equipment conflicts, or traffic impacts.

For notice=true:
- Describe the practical effect on members.
- The summary should explain why the effect exists.

Example:

{
  "notice": true,
  "title": "Fells Point: Kayak availability may be limited",
  "summary": "New-member orientation will use club kayaks."
}

For notice=false:
- Preserve the event's distinguishing activity, route, or destination.
- Avoid promotional language.

Return JSON only.
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


def format_time(value):
    return value.strftime("%-I:%M %p").replace(":00", "")


def format_time_window(starts_at, ends_at):
    return (
        f"{format_time(starts_at)}–"
        f"{format_time(ends_at)}"
    )


def fetch_events(now):
    end = now + timedelta(days=WINDOW_DAYS)

    params = {
        "per_page": 50,
        "start_date": now.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "end_date": end.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "status": "publish",
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Beacon/1.0 "
            "(https://github.com/bmore-kayak/beacon)"
        ),
    }

    last_response = None

    for attempt in range(3):
        response = requests.get(
            EVENTS_URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        last_response = response

        if response.ok:
            return response.json().get("events", [])

        if attempt < 2:
            time.sleep(2)

    last_response.raise_for_status()
    return []


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
            "state": clean_html(
                venue.get("state")
                or venue.get("province")
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


def event_fingerprint(event):
    meaningful_fields = {
        "title": event["title"],
        "description": event["description"],
        "start": event["start"],
        "end": event["end"],
        "venue": event["venue"],
        "categories": event["categories"],
    }

    encoded = json.dumps(
        meaningful_fields,
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
            "Cloudflare did not return a JSON object"
        )

    return json.loads(text[start:end + 1])


def classify_event(event):
    if not ACCOUNT_ID or not API_TOKEN:
        raise RuntimeError(
            "Missing CF_ACCT_ID or CF_AI_WORKERS"
        )

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{ACCOUNT_ID}/ai/run/{MODEL}"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
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

    result = response.json().get("result", {})
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

    notice = result.get("notice")

    if not isinstance(notice, bool):
        raise ValueError(
            "AI result has an invalid notice value"
        )

    if not title:
        raise ValueError(
            "AI result is missing a title"
        )

    if not summary:
        raise ValueError(
            "AI result is missing a summary"
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
        "notice": notice,
        "title": title,
        "summary": summary,
    }


def is_today(starts_at, ends_at, now):
    start_of_day = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    end_of_day = start_of_day + timedelta(days=1)

    return (
        starts_at < end_of_day
        and ends_at >= start_of_day
    )


def unavailable_condition(now, detail):
    return {
        "icon": "🛶",
        "label": "Club Notices",
        "status": "⚪",
        "detail": detail,
        "items": [],
        "source": {
            "label": "Canton Kayak Club",
            "url": EVENTS_PAGE_URL,
        },
        "checked_at": now.isoformat(
            timespec="seconds"
        ),
    }


def get_club_notices(now=None):
    """
    Return:
        condition: latest.json-compatible Club Notices condition
        note_lines: notice titles and time windows for today
    """

    now = now or datetime.now(TIMEZONE)

    if now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE)
    else:
        now = now.astimezone(TIMEZONE)

    try:
        raw_events = fetch_events(now)
    except (requests.RequestException, ValueError):
        return (
            unavailable_condition(
                now,
                "Club events unavailable",
            ),
            [],
        )

    state = load_state()
    items = []
    active_ids = set()

    for raw in raw_events:
        event = normalize_event(raw)
        event_id = str(event["event_id"])
        active_ids.add(event_id)

        fingerprint = event_fingerprint(event)
        saved = state.get(event_id)

        cache_valid = (
            saved
            and saved.get("fingerprint") == fingerprint
            and saved.get("prompt_version")
            == PROMPT_VERSION
            and isinstance(
                saved.get("ai_result"),
                dict,
            )
        )

        if cache_valid:
            ai_result = saved["ai_result"]

        else:
            try:
                ai_result = validate_ai_result(
                    classify_event(event)
                )
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                json.JSONDecodeError,
            ):
                # Reuse an older result when AI fails,
                # rather than dropping a known event.
                if saved and isinstance(
                    saved.get("ai_result"),
                    dict,
                ):
                    ai_result = saved["ai_result"]
                else:
                    continue

            state[event_id] = {
                "prompt_version": PROMPT_VERSION,
                "fingerprint": fingerprint,
                "source_modified_at": (
                    event["modified_utc"]
                ),
                "reviewed_at": now.isoformat(
                    timespec="seconds"
                ),
                "ai_result": ai_result,
            }

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

    # Remove cached events no longer returned in the
    # active seven-day window.
    state = {
        event_id: value
        for event_id, value in state.items()
        if event_id in active_ids
    }

    save_state(state)

    items.sort(
        key=lambda item: item["starts_at"]
    )

    today_notices = []

    for item in items:
        if not item["notice"]:
            continue

        starts_at = datetime.fromisoformat(
            item["starts_at"]
        )
        ends_at = datetime.fromisoformat(
            item["ends_at"]
        )

        if is_today(starts_at, ends_at, now):
            today_notices.append(item)

    upcoming_notices = [
        item
        for item in items
        if item["notice"]
    ]

    if today_notices:
        status = "🟡"
        detail = today_notices[0]["title"]
    elif upcoming_notices:
        status = "⚪"
        count = len(upcoming_notices)
        detail = (
            "1 upcoming club notice"
            if count == 1
            else f"{count} upcoming club notices"
        )
    elif items:
        status = "⚪"
        count = len(items)
        detail = (
            "1 upcoming club event"
            if count == 1
            else f"{count} upcoming club events"
        )
    else:
        status = "⚪"
        detail = "No upcoming club events"

    note_lines = []

    for item in today_notices:
        starts_at = datetime.fromisoformat(
            item["starts_at"]
        )
        ends_at = datetime.fromisoformat(
            item["ends_at"]
        )

        note_lines.append(
            f"{item['title']} · "
            f"{format_time_window(starts_at, ends_at)}"
        )

    condition = {
        "icon": "🛶",
        "label": "Club Notices",
        "status": status,
        "detail": detail,
        "items": items,
        "source": {
            "label": "Canton Kayak Club",
            "url": EVENTS_PAGE_URL,
        },
        "checked_at": now.isoformat(
            timespec="seconds"
        ),
    }

    return condition, note_lines
