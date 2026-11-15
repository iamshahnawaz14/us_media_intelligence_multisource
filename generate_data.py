"""Create a reproducible, entirely synthetic U.S. media audience dataset.

No proprietary Nielsen information or real viewership numbers are included.
"""
from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "data" / "media_ratings_synthetic.csv"
START = dt.date(2024, 1, 1)
END = dt.date(2025, 12, 31)

REGIONS = {
    "Northeast": 32_000_000,
    "Midwest": 27_000_000,
    "South": 42_000_000,
    "West": 37_000_000,
}

# These are fictional programming labels, not actual ratings reports.
PROGRAMS = [
    {"program": "NBA Primetime", "network": "ABC", "platform": "Broadcast TV", "genre": "Sports", "base": 850_000, "days": {5}, "months": set(range(1, 7)) | {10, 11, 12}},
    {"program": "NBA Tonight", "network": "ESPN", "platform": "Cable TV", "genre": "Sports", "base": 430_000, "days": {2, 4}, "months": set(range(1, 7)) | {10, 11, 12}},
    {"program": "NFL Sunday Game", "network": "FOX", "platform": "Broadcast TV", "genre": "Sports", "base": 1_300_000, "days": {6}, "months": {1, 2, 9, 10, 11, 12}},
    {"program": "Hockey Night", "network": "ESPN", "platform": "Cable TV", "genre": "Sports", "base": 300_000, "days": {1, 3}, "months": set(range(1, 7)) | {10, 11, 12}},
    {"program": "Baseball Spotlight", "network": "FS1", "platform": "Cable TV", "genre": "Sports", "base": 270_000, "days": {0, 4}, "months": {4, 5, 6, 7, 8, 9, 10}},
    {"program": "Soccer Matchday", "network": "Apple TV+", "platform": "Streaming", "genre": "Sports", "base": 200_000, "days": {5}, "months": {3, 4, 5, 6, 7, 8, 9, 10}},
    {"program": "Evening News", "network": "CNN", "platform": "Cable TV", "genre": "News", "base": 360_000, "days": set(range(7)), "months": set(range(1, 13))},
    {"program": "City Stories", "network": "NBC", "platform": "Broadcast TV", "genre": "Entertainment", "base": 490_000, "days": {0, 3}, "months": set(range(1, 13))},
    {"program": "Streaming Original", "network": "Netflix", "platform": "Streaming", "genre": "Entertainment", "base": 570_000, "days": set(range(7)), "months": set(range(1, 13))},
    {"program": "Family Favorites", "network": "Disney+", "platform": "Streaming", "genre": "Entertainment", "base": 380_000, "days": set(range(7)), "months": set(range(1, 13))},
    {"program": "Original Movies", "network": "Prime Video", "platform": "Streaming", "genre": "Movies", "base": 410_000, "days": set(range(7)), "months": set(range(1, 13))},
]

FIELDS = ["date", "region", "platform", "network", "program", "genre", "viewers", "impressions", "rating_pct", "ad_spend_usd", "watch_minutes", "data_source"]


def build_rows(seed: int = 2026) -> list[dict]:
    rnd = random.Random(seed)
    rows: list[dict] = []
    current = START
    while current <= END:
        for p in PROGRAMS:
            if current.weekday() not in p["days"] or current.month not in p["months"]:
                continue
            for region, universe in REGIONS.items():
                growth = 1.0 + ((current.year - START.year) * 0.055)
                seasonality = 1.0 + 0.12 * (current.month in (11, 12))
                viewers = int(p["base"] * rnd.uniform(.65, 1.35) * growth * seasonality)
                impressions = int(viewers * rnd.uniform(1.15, 1.85))
                rating = round(100.0 * viewers / universe, 3)
                ad_spend = 0 if p["network"] in {"Netflix", "Disney+", "Prime Video", "Apple TV+"} else int(viewers * rnd.uniform(.035, .09))
                minutes = int(viewers * rnd.uniform(35, 115))
                rows.append({
                    "date": current.isoformat(), "region": region,
                    "platform": p["platform"], "network": p["network"],
                    "program": p["program"], "genre": p["genre"],
                    "viewers": viewers, "impressions": impressions,
                    "rating_pct": rating, "ad_spend_usd": ad_spend,
                    "watch_minutes": minutes, "data_source": "Synthetic demo data",
                })
        current += dt.timedelta(days=1)
    return rows


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {len(rows):,} synthetic records: {OUTPUT}")


if __name__ == "__main__":
    main()
