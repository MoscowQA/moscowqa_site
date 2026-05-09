#!/usr/bin/env python3
"""Parse heisenbug.ru/archive and add found talks to speaker .md files.

Usage:
    python parsers/parse_heisenbug.py [--dry-run]

    --dry-run   Print matches without modifying files.
"""
import re
import sys
import argparse
import requests
from bs4 import BeautifulSoup
from common import (
    HEADERS,
    load_speakers,
    build_name_index,
    find_speaker,
    save_speaker,
    polite_sleep,
)

BASE = "https://heisenbug.ru"


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    r = session.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def get_editions(session: requests.Session) -> list[dict]:
    """Return list of {name, url} for every conference edition."""
    soup = get_soup(f"{BASE}/archive/", session)
    editions = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Match /archive/2023 Spring/ or /archive/2024%20Autumn/ style paths
        if re.search(r"/archive/\d{4}", href):
            full = href if href.startswith("http") else BASE + href
            if full not in seen:
                seen.add(full)
                # Derive human-readable name from the link text or URL
                label = a.get_text(strip=True) or re.sub(r".*/archive/", "", href).strip("/")
                editions.append({"name": label or full, "url": full})

    return editions


def get_talks_from_edition(edition_url: str, edition_name: str, session: requests.Session) -> list[dict]:
    """Parse a single edition page and return list of talk dicts."""
    soup = get_soup(edition_url, session)
    talks = []

    # Heisenbug talk cards usually contain a link to /talks/{hash}/
    # and speaker name(s) nearby.
    talk_links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/talks/[0-9a-f]{10,}/", href):
            full = href if href.startswith("http") else BASE + href
            if full not in talk_links:
                talk_links[full] = a

    for url, anchor in talk_links.items():
        # Walk up to the card container to extract title + speakers
        card = anchor.find_parent(class_=re.compile(r"card|talk|session|item", re.I)) or anchor.parent

        title = anchor.get_text(strip=True)
        # Try to find a larger title element within the card
        h = card.find(re.compile(r"h[1-4]"))
        if h:
            title = h.get_text(strip=True)

        # Collect speaker names from the card
        speakers = []
        for el in card.find_all(class_=re.compile(r"speaker|author|presenter", re.I)):
            name = el.get_text(strip=True)
            if name and name not in speakers:
                speakers.append(name)

        talks.append(
            {
                "title": title,
                "speakers": speakers,
                "url": url,
                "edition": edition_name,
            }
        )

    return talks


def get_talk_details(talk_url: str, session: requests.Session) -> dict:
    """Fetch an individual talk page to get title, speakers, date, slides."""
    soup = get_soup(talk_url, session)

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Speakers
    speakers = []
    for el in soup.find_all(class_=re.compile(r"speaker|author|presenter", re.I)):
        # Avoid grabbing large blocks; limit to short text
        text = el.get_text(strip=True)
        if text and len(text) < 80 and text not in speakers:
            speakers.append(text)

    # Date — look for <time> or meta
    date = ""
    time_el = soup.find("time")
    if time_el:
        date = time_el.get("datetime", "") or time_el.get_text(strip=True)
        date = date[:10]  # keep only YYYY-MM-DD part

    # Slides — links to PDF/slides hosts
    slides_url = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(slides|pdf|speakerdeck|slideshare|squidex)", href, re.I):
            slides_url = href
            break

    return {
        "title": title,
        "speakers": speakers,
        "date": date,
        "slides_url": slides_url,
    }


def derive_edition_label(url: str) -> str:
    """Turn 'https://heisenbug.ru/archive/2024%20Autumn/' into 'Heisenbug 2024 Autumn'."""
    m = re.search(r"/archive/([^/]+)/?$", url)
    if m:
        raw = requests.utils.unquote(m.group(1)).strip()
        return f"Heisenbug {raw}"
    return "Heisenbug"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Do not modify files")
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Fetch each talk page for accurate title/date/slides (slow)",
    )
    args = parser.parse_args()

    speakers = load_speakers()
    name_index = build_name_index(speakers)
    print(f"Loaded {len(speakers)} speakers")

    session = requests.Session()

    print("Fetching editions list from heisenbug.ru/archive/ ...")
    editions = get_editions(session)
    if not editions:
        print("ERROR: no editions found — the page structure may have changed.")
        sys.exit(1)
    print(f"Found {len(editions)} editions: {[e['name'] for e in editions]}")

    total_added = 0

    for edition in editions:
        edition_label = derive_edition_label(edition["url"])
        print(f"\n--- {edition_label} ---")
        polite_sleep(1)

        try:
            talks = get_talks_from_edition(edition["url"], edition_label, session)
        except Exception as exc:
            print(f"  Skip {edition['url']}: {exc}")
            continue

        print(f"  Found {len(talks)} talk links")

        for talk in talks:
            # If card parsing gave us no speakers, fetch the detail page
            if args.detail or not talk["speakers"]:
                polite_sleep(0.8)
                try:
                    details = get_talk_details(talk["url"], session)
                    if details["title"]:
                        talk["title"] = details["title"]
                    if details["speakers"]:
                        talk["speakers"] = details["speakers"]
                    talk["date"] = details.get("date", "")
                    talk["slides_url"] = details.get("slides_url", "")
                except Exception as exc:
                    print(f"    Warn: detail page failed for {talk['url']}: {exc}")

            for candidate in talk["speakers"]:
                speaker = find_speaker(name_index, candidate)
                if not speaker:
                    continue

                new_entry = {
                    "title": talk["title"],
                    "event": edition_label,
                    "date": talk.get("date", ""),
                    "url": talk["url"],
                    "slides_url": talk.get("slides_url", ""),
                }

                if talk["url"] in speaker["existing_urls"]:
                    continue  # already recorded

                print(f"  MATCH: {speaker['name']} → {talk['title'][:60]}")

                if not args.dry_run:
                    added = save_speaker(speaker, [new_entry])
                    total_added += added

    print(f"\nDone. Total new talks added: {total_added}")
    if args.dry_run:
        print("(dry-run mode — no files were modified)")


if __name__ == "__main__":
    main()
