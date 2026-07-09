import json
from datetime import datetime
from pathlib import Path

import requests

WATERFRONT_URL = "https://services2.arcgis.com/orhH6cbKzLjUCxfK/arcgis/rest/services/Baltimore_Harbor_2024_Water_Quality_Data_with_2023_Historic_Data/FeatureServer/0/query?where=1%3D1&outFields=Site_Name,New_Sample_Date,New_Sample_Status,New_Sample_BacteriaCount,Rain_amount_past7days&returnGeometry=false&f=json"

OUT = Path("data/latest.json")
PASS_LIMIT = 104


def fetch_json(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def clean_count(value):
    return None if value is None else int(float(value))


def score_station(status, count):
    if status:
        return "🟢" if "pass" in status.lower() else "🔴"
    if count is None:
        return "🟡"
    return "🟢" if count <= PASS_LIMIT else "🔴"


def main():
    raw = fetch_json(WATERFRONT_URL)

    stations = []
    for feature in raw["features"]:
        a = feature["attributes"]
        count = clean_count(a.get("New_Sample_BacteriaCount"))
        advisory = a.get("New_Sample_Status")

        stations.append({
            "site": a.get("Site_Name"),
            "date": a.get("New_Sample_Date"),
            "status": score_station(advisory, count),
            "advisory": advisory,
            "bacteria": count,
        })

    counts = [s["bacteria"] for s in stations if s["bacteria"] is not None]
    passing = sum(s["status"] == "🟢" for s in stations)
    failing = sum(s["status"] == "🔴" for s in stations)

    data = {
        "location": "Baltimore Harbor",
        "overall": "🔴 Don't Go" if failing else "🟢 Good",
        "updated": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "conditions": [
            ["🌬 Wind", "🟢", "Pending"],
            ["🌊 Waves", "🟢", "Pending"],
            ["⛈ Storms", "🟢", "Pending"],
            ["🚩 Small Craft", "🟢", "Pending"],
            ["🦠 Water Contact", "🔴" if failing else "🟢", f"{min(counts)}–{max(counts)} MPN" if counts else "Unavailable"],
            ["🌡 Water Temp", "🟢", "Pending"],
        ],
        "note": f"Water contact: {passing}/{len(stations)} passing, {failing}/{len(stations)} failing.",
        "stations": stations,
    }

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
