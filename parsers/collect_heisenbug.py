#!/usr/bin/env python3
"""Collect all Heisenbug speakers and their talks into heisenbug_speakers.json.

Usage:
    python parsers/collect_heisenbug.py              # process all editions
    python parsers/collect_heisenbug.py --edition "2025 Spring"  # one edition only

Re-running merges new data without duplicating existing talk URLs.
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

BASE = "https://heisenbug.ru"
OUTPUT = Path(__file__).parent.parent / "heisenbug_speakers.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def get(url: str, session: requests.Session) -> requests.Response:
    r = session.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r


def next_data(html: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            return json.loads(tag.string)
        except Exception:
            pass
    return {}


def ru(v) -> str:
    if isinstance(v, dict):
        return v.get("ru") or v.get("en") or ""
    return v or ""


def en(v) -> str:
    if isinstance(v, dict):
        return v.get("en") or v.get("ru") or ""
    return v or ""


def person_profile(sp: dict) -> dict:
    name = sp.get("name", {})
    company = sp.get("company", {})
    photo = sp.get("photo") or {}
    return {
        "id": sp.get("id", ""),
        "name_ru": ru(name),
        "name_en": en(name),
        "company_ru": ru(company),
        "company_en": en(company),
        "photo_url": photo.get("url", "") if isinstance(photo, dict) else "",
    }


def get_editions(session: requests.Session) -> list[dict]:
    r = get(f"{BASE}/archive/", session)
    soup = BeautifulSoup(r.text, "lxml")
    editions, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/archive/\d{4}", href):
            full = href if href.startswith("http") else BASE + href
            if full not in seen:
                seen.add(full)
                m = re.search(r"/archive/([^/]+)/?$", full)
                label = f"Heisenbug {requests.utils.unquote(m.group(1)).strip()}" if m else full
                editions.append({"label": label, "url": full.rstrip("/")})
    return editions


def fetch_edition(edition_url: str, edition_label: str, session: requests.Session):
    """Return (profiles dict, talks_by_speaker dict) for this edition.

    profiles: {speaker_id: profile_dict}
    talks_by_speaker: {speaker_id: [talk_entry, ...]}
    """
    base = edition_url

    # --- Speaker profiles from /speakers/ page ---
    profiles = {}
    try:
        r = session.get(f"{base}/speakers/", headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = next_data(r.text)
            pp = data.get("props", {}).get("pageProps", {})
            for sp in pp.get("speakers", []) + pp.get("specialGuests", []):
                sid = sp.get("id", "")
                if sid:
                    profiles[sid] = person_profile(sp)
    except Exception as exc:
        print(f"  Warn: /speakers/ failed: {exc}")

    # --- Talks from schedule page ---
    talks_by_speaker: dict[str, list] = {}

    schedule_html = None
    for suffix in ("/schedule/table/", "/schedule/days/", "/schedule/"):
        try:
            r = session.get(base + suffix, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                schedule_html = r.text
                break
        except Exception:
            continue

    if schedule_html:
        data = next_data(schedule_html)
        pp = data.get("props", {}).get("pageProps", {})

        talks_by_day = pp.get("talksByDay", [])
        talks_flat = pp.get("talks", [])  # old seasons (2021 and earlier)

        # Collect raw talk dicts regardless of format
        raw_talks: list[dict] = []

        if talks_by_day:
            # New format: talksByDay[].talks[] = [time_info, [talk, ...]]
            for day in talks_by_day:
                for slot in day.get("talks", []):
                    if not isinstance(slot, list):
                        continue
                    for elem in slot:
                        if not isinstance(elem, list):
                            continue
                        for talk_data in elem:
                            if isinstance(talk_data, dict):
                                raw_talks.append(talk_data)

        elif talks_flat:
            # Old format: flat list of talks
            raw_talks = [t for t in talks_flat if isinstance(t, dict)]

        for talk_data in raw_talks:
            if talk_data.get("isServiceTalk"):
                continue

            talk_id = talk_data.get("id", "")
            title_val = talk_data.get("name", {})
            title_ru = ru(title_val)
            if not talk_id or not title_ru:
                continue

            # Slides: new seasons may not have materials in schedule data;
            # old seasons always have it here
            slides_url = ""
            for mat in talk_data.get("materials", []):
                if mat.get("materialType") in ("presentation", "slides") or \
                   mat.get("fileType") == "pdf" or \
                   re.search(r"\.pdf$", mat.get("url", ""), re.I):
                    slides_url = mat.get("url", "")
                    break

            talk_entry = {
                "title_ru": title_ru,
                "title_en": en(title_val),
                "url": f"{base}/talks/{talk_id}/",
                "edition": edition_label,
                "date": (
                    talk_data.get("talkStartTime")
                    or talk_data.get("time")
                    or ""
                )[:10],
                "slides_url": slides_url,
            }

            # Only actual speakers get talks linked; experts/hosts are profiles only
            for sp in talk_data.get("speakers", []):
                sid = sp.get("id", "")
                if not sid:
                    continue
                if sid not in profiles:
                    profiles[sid] = person_profile(sp)
                talks_by_speaker.setdefault(sid, []).append(talk_entry)

            # Collect profiles for experts/hosts but don't link talks to them
            for sp in talk_data.get("experts", []) + talk_data.get("hosts", []):
                sid = sp.get("id", "")
                if sid and sid not in profiles:
                    profiles[sid] = person_profile(sp)

    return profiles, talks_by_speaker


def merge_into(existing: dict, profiles: dict, talks_by_speaker: dict) -> tuple[int, int]:
    """Merge edition data into existing speakers dict. Returns (new_speakers, new_talks)."""
    new_speakers = new_talks = 0

    for sid, profile in profiles.items():
        if sid not in existing:
            existing[sid] = {**profile, "talks": []}
            new_speakers += 1
        else:
            # Fill any empty fields
            for field in ("name_ru", "name_en", "company_ru", "company_en", "photo_url"):
                if not existing[sid].get(field) and profile.get(field):
                    existing[sid][field] = profile[field]

    for sid, talks in talks_by_speaker.items():
        if sid not in existing:
            existing[sid] = {**profiles.get(sid, {"id": sid, "name_ru": "", "name_en": "",
                                                   "company_ru": "", "company_en": "", "photo_url": ""}),
                             "talks": []}
            new_speakers += 1

        existing_urls = {t["url"] for t in existing[sid]["talks"]}
        for talk in talks:
            if talk["url"] not in existing_urls:
                existing[sid]["talks"].append(talk)
                existing_urls.add(talk["url"])
                new_talks += 1

    return new_speakers, new_talks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--edition",
        help='Filter editions by name, e.g. "2025 Spring"',
    )
    args = parser.parse_args()

    # Load existing data
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

    session = requests.Session()

    print("Fetching editions list from heisenbug.ru/archive/ ...")
    editions = get_editions(session)
    if not editions:
        print("ERROR: no editions found.")
        sys.exit(1)

    if args.edition:
        needle = args.edition.lower()
        editions = [e for e in editions if needle in e["label"].lower() or needle in e["url"].lower()]
        if not editions:
            print(f"No editions matched '{args.edition}'")
            sys.exit(1)

    print(f"Processing {len(editions)} editions: {[e['label'] for e in editions]}")

    total_new_speakers = total_new_talks = 0

    for edition in editions:
        print(f"\n--- {edition['label']} ---")
        time.sleep(1)

        try:
            profiles, talks_by_speaker = fetch_edition(edition["url"], edition["label"], session)
        except Exception as exc:
            print(f"  Skip: {exc}")
            continue

        talk_count = sum(len(v) for v in talks_by_speaker.values())
        print(f"  Speakers: {len(profiles)}, talk-speaker links: {talk_count}")

        ns, nt = merge_into(existing, profiles, talks_by_speaker)
        total_new_speakers += ns
        total_new_talks += nt
        print(f"  Added: {ns} new speakers, {nt} new talks")

    # Save
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