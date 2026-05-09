#!/usr/bin/env python3
"""Sync sqadays_speakers.json into MoscowQA speaker .md files.

Usage:
    python parsers/sync_sqadays.py             # apply changes
    python parsers/sync_sqadays.py --dry-run   # preview only
"""

import json
import sys
import argparse
from pathlib import Path
from common import (
    load_speakers,
    build_name_index,
    find_speaker,
    save_speaker,
    norm_url,
)

SQADAYS_JSON = Path(__file__).parent.parent / "sqadays_speakers.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying files")
    args = parser.parse_args()

    if not SQADAYS_JSON.exists():
        print(f"ERROR: {SQADAYS_JSON} not found. Run collect_sqadays.py first.")
        sys.exit(1)

    raw = json.loads(SQADAYS_JSON.read_text(encoding="utf-8"))
    sqadays_speakers = raw.get("speakers", {})
    print(f"Loaded {len(sqadays_speakers)} SQA Days speakers from {SQADAYS_JSON.name}")

    moscowqa_speakers = load_speakers()
    name_index = build_name_index(moscowqa_speakers)
    print(f"Loaded {len(moscowqa_speakers)} MoscowQA speakers\n")

    total_matched = 0
    total_added = 0

    for sq_speaker in sqadays_speakers.values():
        candidate = sq_speaker.get("name", "").strip()
        if not candidate:
            continue

        mq_speaker = find_speaker(name_index, candidate)
        if not mq_speaker:
            continue

        talks = sq_speaker.get("talks", [])
        if not talks:
            continue

        seen_in_batch: set[str] = set()
        new_entries = []
        for t in talks:
            url = t["url"]
            url_key = norm_url(url)
            if url_key in mq_speaker["existing_urls"] or url_key in seen_in_batch:
                continue
            seen_in_batch.add(url_key)
            new_entries.append({
                "title": t["title"],
                "event": t["event"],
                "date": t.get("date", ""),
                "url": url,
                "slides_url": "",
            })

        if not new_entries:
            continue

        total_matched += 1
        print(f"  {mq_speaker['name']} ← '{candidate}'")
        for e in new_entries:
            print(f"    + [{e['event']}] {e['title'][:65]}")

        if not args.dry_run:
            added = save_speaker(mq_speaker, new_entries)
            total_added += added
        else:
            total_added += len(new_entries)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"Matched speakers: {total_matched}")
    print(f"{'Would add' if args.dry_run else 'Added'}: {total_added} talks")


if __name__ == "__main__":
    main()
