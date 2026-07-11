import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


ACCOUNT_ID = os.getenv("CF_ACCT_ID")
API_TOKEN = os.getenv("CF_AI_WORKERS")

MODEL = "@cf/meta/llama-3.1-8b-fast-v2"

CKC_EVENTS_URL = (
    "https://cantonkayakclub.com/"
    "wp-json/tribe/events/v1/events"
)

TIMEZONE = ZoneInfo("America/New_York")
NOTICE_WINDOW_DAYS = 7


if not ACCOUNT_ID:
    sys.exit("Missing CF_ACCT_ID")

if not API_TOKEN:
    sys.exit("Missing CF_AI_WORKERS")


def clean_html(value):
    if not value:
        return ""

    text = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        value,
        flags=re.DOTALL | re.IGNORECASE,
    )

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def parse_local_datetime(value):
    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=TIMEZONE)


def iso_local(value):
    return value.isoformat(timespec="seconds")


def event_fingerprint(event):
    meaningful_fields = {
        "title": event.get("title"),
        "description": event.get("description"),
        "start_date": event.get("start_date"),
        "end_date": event.get("end_date"),
        "venue": event.get("venue"),
        "categories": event.get("categories"),
        "status": event.get("status"),
    }

    encoded = json.dumps(
        meaningful_fields,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def extract_json_object(text):
    if not text:
        raise ValueError("Empty AI response")

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s*```$", "", text)

    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace == -1 or last_brace == -1:
        raise ValueError(
            f"AI did not return a JSON object: {text}"
        )

    return json.loads(
        text[first_brace:last_brace + 1]
    )


def fetch_upcoming_events():
    now = datetime.now(TIMEZONE)
    end = now + timedelta(days=NOTICE_WINDOW_DAYS)

    params = {
        "page": 1,
        "per_page": 10,
        "start_date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "publish",
    }

    events = []

    while True:
        response = requests.get(
            CKC_EVENTS_URL,
            params=params,
            timeout=30,
        )

        print(
            f"CKC page {params['page']} status:",
            response.status_code,
        )

        response.raise_for_status()
        body = response.json()

        events.extend(body.get("events", []))

        total_pages = body.get("total_pages", 1)

        if params["page"] >= total_pages:
            break

        params["page"] += 1

    return events


def normalize_event(event):
    venue = event.get("venue") or {}
    categories = event.get("categories") or []

    if isinstance(venue, list):
        venue = {}

    return {
        "event_id": event.get("id"),
        "title": clean_html(event.get("title")),
        "description": clean_html(
            event.get("description")
        ),
        "start": event.get("start_date"),
        "end": event.get("end_date"),
        "modified_utc": event.get("modified_utc"),
        "url": event.get("url"),
        "venue": {
            "name": clean_html(venue.get("venue")),
            "slug": venue.get("slug"),
            "address": clean_html(venue.get("address")),
            "city": clean_html(venue.get("city")),
            "state": clean_html(
                venue.get("state")
                or venue.get("province")
            ),
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


SYSTEM_PROMPT = """
Classify an upcoming Canton Kayak Club event for Beacon.

Beacon should show only notices that affect a member's ability to use
club docks, kayaks, equipment, or safely navigate the surrounding water.

Allowed notice types:
- closure
- equipment_conflict
- restricted_access
- water_safety
- increased_boat_traffic
- cancellation_or_change
- none

Create a notice only when the event indicates one of the following:

- A dock, launch, kayak, or other club equipment is closed, unavailable,
  reserved, restricted, or likely to be heavily in use.
- A training session or organized activity at a club location is likely
  to reduce kayak or equipment availability.
- Access to the launch or location is restricted.
- The event describes a cancellation, postponement, registration problem,
  or material logistics change.
- The event identifies a broader water-safety issue such as a marine
  restriction, safety zone, unusually heavy vessel traffic, boat parade,
  regatta, fireworks zone, tall-ship event, or similar public activity.

Do not create a notice merely because:
- a normal small club paddle is scheduled,
- participants are told to check the weather,
- the route may encounter ordinary boat traffic,
- an event requires an RSVP,
- an event has limited participant capacity,
- the event is social, instructional, or recreational without affecting
  general member access or safety.

Special guidance:
- New-member orientation or training at Fells Point / Bond Street Wharf
  should normally be an equipment conflict because trainees use club
  kayaks and launch from that location.
- Do not call something a closure unless the source explicitly says it
  is closed.
- Do not invent the number of kayaks affected.
- Do not invent broader boat traffic impacts from a small club outing.
- Dates, times, venue, and source URL are stored separately by code.
  Do not repeat them unless needed for the short summary.

Return one JSON object with exactly these fields:

{
  "relevant": true or false,
  "type": "closure | equipment_conflict | restricted_access |
           water_safety | increased_boat_traffic |
           cancellation_or_change | none",
  "severity": "info | caution | critical",
  "title": "short notice title or null",
  "summary": "one short factual sentence or null",
  "reason": "brief explanation of the classification",
  "confidence": "low | medium | high"
}

The title and summary appear directly in the app.
Keep them calm, specific, and concise.

Return JSON only.
""".strip()


def classify_event(event):
    cloudflare_url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{ACCOUNT_ID}/ai/run/{MODEL}"
    )

    payload = {
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
        "max_tokens": 250,
        "temperature": 0.0,
    }

    response = requests.post(
        cloudflare_url,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not response.ok:
        print(
            json.dumps(
                response.json(),
                indent=2,
                ensure_ascii=False,
            )
        )
        response.raise_for_status()

    body = response.json()
    result = body.get("result", {})

    content = result.get("response")

    if not content:
        content = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )

    return extract_json_object(content)


events = fetch_upcoming_events()

print()
print(f"Upcoming events found: {len(events)}")


reviewed_at = datetime.now(TIMEZONE)
notices = []


for raw_event in events:
    event = normalize_event(raw_event)

    print()
    print("=" * 70)
    print(event["title"])
    print(
        f"{event['start']} to {event['end']}"
    )
    print(
        "Venue:",
        event["venue"]["name"] or "Not specified",
    )

    try:
        ai_result = classify_event(event)
    except (
        requests.RequestException,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print("Classification failed:", exc)
        continue

    print()
    print("AI result:")
    print(
        json.dumps(
            ai_result,
            indent=2,
            ensure_ascii=False,
        )
    )

    if not ai_result.get("relevant"):
        continue

    notice_type = ai_result.get("type")

    allowed_types = {
        "closure",
        "equipment_conflict",
        "restricted_access",
        "water_safety",
        "increased_boat_traffic",
        "cancellation_or_change",
    }

    if notice_type not in allowed_types:
        print(
            "Skipped because notice type was invalid:",
            notice_type,
        )
        continue

    starts_at = parse_local_datetime(
        event["start"]
    )
    ends_at = parse_local_datetime(
        event["end"]
    )

    notices.append(
        {
            "event_id": event["event_id"],
            "type": notice_type,
            "severity": ai_result.get(
                "severity",
                "info",
            ),
            "title": ai_result.get("title"),
            "summary": ai_result.get("summary"),
            "location": (
                event["venue"]["name"]
                or None
            ),
            "address": (
                event["venue"]["address"]
                or None
            ),
            "starts_at": iso_local(starts_at),
            "ends_at": iso_local(ends_at),
            "show_from": iso_local(
                starts_at
                - timedelta(
                    days=NOTICE_WINDOW_DAYS
                )
            ),
            "source_modified_at": (
                event["modified_utc"]
            ),
            "reviewed_at": iso_local(
                reviewed_at
            ),
            "source_url": event["url"],
            "fingerprint": event_fingerprint(
                raw_event
            ),
            "confidence": ai_result.get(
                "confidence"
            ),
            "classification_reason": (
                ai_result.get("reason")
            ),
        }
    )


notices.sort(
    key=lambda notice: notice["starts_at"]
)


latest_fragment = {
    "club_notices": {
        "icon": "🛶",
        "label": "Club notices",
        "status": (
            "🟡"
            if notices
            else "🟢"
        ),
        "detail": (
            f"{len(notices)} upcoming notice"
            if len(notices) == 1
            else f"{len(notices)} upcoming notices"
            if notices
            else "No current club notices"
        ),
        "items": notices,
        "source": {
            "label": "Canton Kayak Club",
            "url": (
                "https://cantonkayakclub.com/events/"
            ),
        },
        "reviewed_at": iso_local(reviewed_at),
    }
}


print()
print("=" * 70)
print("PROPOSED latest.json FRAGMENT")
print("=" * 70)

print(
    json.dumps(
        latest_fragment,
        indent=2,
        ensure_ascii=False,
    )
)
