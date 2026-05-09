#!/usr/bin/env python3
"""Parse sqadays.com and add found talks to speaker .md files.

Strategy:
  1. Fetch paginated talks listing at /ru/talks?page=N
  2. For each talk card extract title + speaker names
  3. If speakers are missing from the card, fetch the talk detail page
  4. Match against our speaker list and update .md files

Usage:
    python parsers/parse_sqadays.py [--dry-run] [--pages 1-50]

    --dry-run        Print matches without modifying files.
    --pages 1-50     Page range to fetch (default: all until empty page).
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

BASE = "https://sqadays.com"
TALKS_URL = f"{BASE}/ru/talks"
PAGE_SIZE = 100  # request as many as possible per page


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    r = session.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def get_talks_page(page: int, session: requests.Session) -> list[dict]:
    """Fetch one listing page and return raw talk dicts."""
    url = f"{TALKS_URL}?page={page}&page_size={PAGE_SIZE}"
    soup = get_soup(url, session)

    talks = []
    # SQA Days talk cards usually wrap in an <article> or .talk-card / .card element
    cards = (
        soup.find_all("article")
        or soup.find_all(class_=re.compile(r"talk.?card|report.?card|card", re.I))
    )

    if not cards:
        # Fallback: grab all links matching /ru/talk/{id}
        for a in soup.find_all("a", href=re.compile(r"/ru/talk/\d+")):
            href = a["href"]
            full = href if href.startswith("http") else BASE + href
            talks.append(
                {
                    "title": a.get_text(strip=True),
                    "speakers": [],
                    "url": full,
                    "event": "",
                    "date": "",
                    "slides_url": "",
                }
            )
        return talks

    for card in cards:
        # Talk URL
        a = card.find("a", href=re.compile(r"/ru/talk/\d+"))
        if not a:
            continue
        href = a["href"]
        url = href if href.startswith("http") else BASE + href

        # Title
        h = card.find(re.compile(r"h[1-4]"))
        title = h.get_text(strip=True) if h else a.get_text(strip=True)

        # Event / conference name (e.g. "SQA Days #35")
        event_el = card.find(class_=re.compile(r"event|conference|conf", re.I))
        event = event_el.get_text(strip=True) if event_el else "SQA Days"

        # Date
        date = ""
        time_el = card.find("time")
        if time_el:
            date = time_el.get("datetime", "") or time_el.get_text(strip=True)
            date = date[:10]

        # Speakers
        speakers = []
        for el in card.find_all(class_=re.compile(r"speaker|author|presenter", re.I)):
            name = el.get_text(strip=True)
            if name and len(name) < 80 and name not in speakers:
                speakers.append(name)

        talks.append(
            {
                "title": title,
                "speakers": speakers,
                "url": url,
                "event": event or "SQA Days",
                "date": date,
                "slides_url": "",
            }
        )

    return talks


def get_talk_details(talk_url: str, session: requests.Session) -> dict:
    """Fetch individual talk page to extract speakers, date, slides, event."""
    soup = get_soup(talk_url, session)

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Speakers — SQA Days typically has a dedicated speaker block
    speakers = []
    for el in soup.find_all(class_=re.compile(r"speaker|author|presenter", re.I)):
        name = el.get_text(strip=True)
        if name and len(name) < 80 and name not in speakers:
            speakers.append(name)

    # Date
    date = ""
    time_el = soup.find("time")
    if time_el:
        date = time_el.get("datetime", "") or time_el.get_text(strip=True)
        date = date[:10]

    # Event name (e.g. "SQA Days #35")
    event = "SQA Days"
    for el in soup.find_all(class_=re.compile(r"event|conference|edition", re.I)):
        text = el.get_text(strip=True)
        if text and len(text) < 60:
            event = text
            break

    # Slides
    slides_url = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(slides|pdf|speakerdeck|slideshare|squidex|drive\.google)", href, re.I):
            slides_url = href
            break

    return {
        "title": title,
        "speakers": speakers,
        "date": date,
        "event": event,
        "slides_url": slides_url,
    }


def parse_page_range(arg: str):
    """Parse '1-50' or '5' into (start, end)."""
    if "-" in arg:
        parts = arg.split("-", 1)
        return int(parts[0]), int(parts[1])
    n = int(arg)
    return n, n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--pages",
        default=None,
        help="Page range, e.g. '1-20'. Default: crawl until empty.",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Always fetch talk detail pages (more accurate, slower).",
    )
    args = parser.parse_args()

    speakers = load_speakers()
    name_index = build_name_index(speakers)
    print(f"Loaded {len(speakers)} speakers")

    session = requests.Session()

    page_start, page_end = (1, 9999) if not args.pages else parse_page_range(args.pages)

    total_added = 0
    page = page_start

    while page <= page_end:
        print(f"\nPage {page} ...")
        polite_sleep(1)

        try:
            talks = get_talks_page(page, session)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                print("  404 — reached end of listing.")
                break
            raise

        if not talks:
            print("  Empty page — done.")
            break

        print(f"  Got {len(talks)} talks")

        for talk in talks:
            if args.detail or not talk["speakers"]:
                polite_sleep(0.5)
                try:
                    details = get_talk_details(talk["url"], session)
                    if details["title"]:
                        talk["title"] = details["title"]
                    if details["speakers"]:
                        talk["speakers"] = details["speakers"]
                    if details["date"]:
                        talk["date"] = details["date"]
                    if details["event"] and details["event"] != "SQA Days":
                        talk["event"] = details["event"]
                    if details["slides_url"]:
                        talk["slides_url"] = details["slides_url"]
                except Exception as exc:
                    print(f"    Warn: {talk['url']}: {exc}")

            for candidate in talk["speakers"]:
                speaker = find_speaker(name_index, candidate)
                if not speaker:
                    continue
                if talk["url"] in speaker["existing_urls"]:
                    continue

                new_entry = {
                    "title": talk["title"],
                    "event": talk["event"],
                    "date": talk.get("date", ""),
                    "url": talk["url"],
                    "slides_url": talk.get("slides_url", ""),
                }

                print(f"  MATCH: {speaker['name']} → {talk['title'][:60]}")

                if not args.dry_run:
                    added = save_speaker(speaker, [new_entry])
                    total_added += added

        page += 1

    print(f"\nDone. Total new talks added: {total_added}")
    if args.dry_run:
        print("(dry-run mode — no files were modified)")


if __name__ == "__main__":
    main()
