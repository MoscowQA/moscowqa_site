#!/usr/bin/env python3
"""Collect all SQA Days speakers and their talks into sqadays_speakers.json.

Usage:
    python parsers/collect_sqadays.py              # all conferences
    python parsers/collect_sqadays.py --event 144051   # one conference only

Re-running merges new data without duplicating existing talk URLs.
When a new SQA Days is published, add its eventId to CONFERENCE_IDS and re-run.
"""

import json
import re
import sys
import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import date
from pathlib import Path

BASE = "https://sqadays.com"
OUTPUT = Path(__file__).parent.parent / "sqadays_speakers.json"

CONFERENCE_IDS = [
    "149374", "144051", "137316", "130253",
    "117475", "116665", "110410", "105727",
    "99183",  "93746",  "86867",  "82473",
    "79352",  "72247",  "69279",  "62415",
    "55692",  "52247",  "45127",  "40015",
    "38947",  "36565",  "33044",  "23908",
    "15080",  "8058",   "11151",  "7995",
    "301",    "285",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def conf_name_from_soup(soup: BeautifulSoup) -> str:
    logo = soup.find(class_="logo__name")
    if not logo:
        return "SQA Days"
    text = re.sub(r"\s+", " ", logo.get_text(" ", strip=True))
    m = re.search(r"/\s*(\d+)", text)
    return f"SQA Days #{m.group(1)}" if m else f"SQA Days {text.strip()}"


def fetch_conference(event_id: str, session: requests.Session) -> tuple[dict, dict]:
    """Return (profiles, talks_by_speaker) for this conference."""
    url = f"{BASE}/ru/talks/{event_id}"
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        print(f"  Skip {event_id}: {exc}")
        return {}, {}, "SQA Days"

    soup = BeautifulSoup(r.text, "lxml")
    conf_name = conf_name_from_soup(soup)

    profiles: dict[str, dict] = {}
    talks_by_speaker: dict[str, list] = {}

    for card in soup.select("ul.report-list li div.report"):
        title_el = card.select_one(".report__title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)

        # Archived talks have <a href>, current submissions use objid
        talk_href = title_el.get("href") if title_el.name == "a" else None
        if not talk_href:
            btn = card.select_one(".rating-block")
            objid = btn.get("objid") if btn else None
            if not objid:
                continue
            talk_href = f"/ru/talk/{objid}"

        talk_url = talk_href if talk_href.startswith("http") else BASE + talk_href

        talk_entry = {
            "title": title,
            "url": talk_url,
            "event": conf_name,
            "date": "",
        }

        for member in card.select(".report__authors .member"):
            name_el = member.select_one(".member__name")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            profile_href = name_el.get("href", "")
            m = re.search(r"/profile/(\d+)", profile_href)
            if not m:
                continue
            pid = m.group(1)

            if pid not in profiles:
                company_el = member.select_one(".member__post")
                profiles[pid] = {
                    "id": pid,
                    "name": name,
                    "company": company_el.get_text(strip=True) if company_el else "",
                    "profile_url": (BASE + profile_href) if not profile_href.startswith("http") else profile_href,
                }
            talks_by_speaker.setdefault(pid, []).append(talk_entry)

    return profiles, talks_by_speaker, conf_name


def merge_into(existing: dict, profiles: dict, talks_by_speaker: dict) -> tuple[int, int]:
    new_speakers = new_talks = 0

    for pid, profile in profiles.items():
        if pid not in existing:
            existing[pid] = {**profile, "talks": []}
            new_speakers += 1
        else:
            for field in ("name", "company", "profile_url"):
                if not existing[pid].get(field) and profile.get(field):
                    existing[pid][field] = profile[field]

    for pid, talks in talks_by_speaker.items():
        if pid not in existing:
            existing[pid] = {
                **profiles.get(pid, {"id": pid, "name": "", "company": "", "profile_url": ""}),
                "talks": [],
            }
            new_speakers += 1

        existing_urls = {t["url"].lower() for t in existing[pid]["talks"]}
        seen_in_batch: set[str] = set()
        for talk in talks:
            key = talk["url"].lower()
            if key not in existing_urls and key not in seen_in_batch:
                existing[pid]["talks"].append(talk)
                existing_urls.add(key)
                seen_in_batch.add(key)
                new_talks += 1

    return new_speakers, new_talks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", help="Process only this event ID, e.g. 144051")
    args = parser.parse_args()

    existing: dict = {}
    if OUTPUT.exists():
        try:
            raw = json.loads(OUTPUT.read_text(encoding="utf-8"))
            existing = raw.get("speakers", {})
            print(f"Loaded {len(existing)} existing speakers from {OUTPUT.name}")
        except Exception as exc:
            print(f"Warn: could not load {OUTPUT}: {exc}")
    else:
        print(f"No existing file — will create {OUTPUT.name}")

    ids = [args.event] if args.event else CONFERENCE_IDS
    session = requests.Session()

    total_new_speakers = total_new_talks = 0

    for event_id in ids:
        print(f"\n--- eventId={event_id} ---")
        time.sleep(1)

        profiles, talks_by_speaker, conf_name = fetch_conference(event_id, session)
        if not profiles and not talks_by_speaker:
            continue

        talk_count = sum(len(v) for v in talks_by_speaker.values())
        print(f"  {conf_name}: speakers={len(profiles)}, talk-speaker links={talk_count}")

        ns, nt = merge_into(existing, profiles, talks_by_speaker)
        total_new_speakers += ns
        total_new_talks += nt
        print(f"  Added: {ns} new speakers, {nt} new talks")

    OUTPUT.write_text(
        json.dumps(
            {"last_updated": str(date.today()), "speakers": existing},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nDone. New speakers: {total_new_speakers}, new talks: {total_new_talks}")
    print(f"Total speakers in DB: {len(existing)}")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
