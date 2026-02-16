#!/usr/bin/env python3
"""Static site generator for MoscowQA community website.

Reads markdown content from content/ directory, applies Jinja2 templates,
and outputs static HTML to dist/ directory.
"""
import os
import shutil
import yaml
import markdown
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "dist"

md = markdown.Markdown(extensions=["meta", "tables", "fenced_code", "toc"])


def parse_md_file(filepath: Path) -> dict:
    """Parse a markdown file with YAML front matter."""
    text = filepath.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) >= 3 and parts[0].strip() == "":
        front_matter = yaml.safe_load(parts[1])
        body_md = parts[2].strip()
    else:
        front_matter = {}
        body_md = text

    md.reset()
    body_html = md.convert(body_md)
    return {**front_matter, "body": body_html}


def load_events() -> list[dict]:
    """Load all event markdown files, sorted by date descending."""
    events_dir = CONTENT_DIR / "events"
    events = []
    if events_dir.exists():
        for f in events_dir.glob("*.md"):
            event = parse_md_file(f)
            event["slug"] = f.stem
            events.append(event)
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return events


def load_speakers() -> list[dict]:
    """Load all speaker markdown files, sorted by name."""
    speakers_dir = CONTENT_DIR / "speakers"
    speakers = []
    if speakers_dir.exists():
        for f in speakers_dir.glob("*.md"):
            speaker = parse_md_file(f)
            speaker["slug"] = f.stem
            speakers.append(speaker)
    speakers.sort(key=lambda s: s.get("name", ""))
    return speakers


def load_pages() -> dict:
    """Load site-level pages (about, cfp, etc.)."""
    pages = {}
    for f in CONTENT_DIR.glob("*.md"):
        page = parse_md_file(f)
        page["slug"] = f.stem
        pages[f.stem] = page
    return pages


def build():
    """Build the static site."""
    # Clean output
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Copy static files
    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static")

    # Set up Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    # Load data
    events = load_events()
    speakers = load_speakers()
    pages = load_pages()

    site = {
        "title": "Moscow QA",
        "description": "Сообщество тестировщиков Москвы",
        "telegram": "https://t.me/moscowqa",
        "youtube": "https://www.youtube.com/@moscowqa",
        "timepad": "https://moscowqa.timepad.ru",
    }

    common = {"site": site, "events": events, "speakers": speakers}

    # Build index page
    tpl = env.get_template("index.html")
    html = tpl.render(**common, latest_events=events[:6])
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")

    # Build events list page
    tpl = env.get_template("events.html")
    html = tpl.render(**common)
    (OUTPUT_DIR / "events").mkdir(exist_ok=True)
    (OUTPUT_DIR / "events" / "index.html").write_text(html, encoding="utf-8")

    # Build individual event pages
    tpl = env.get_template("event.html")
    for event in events:
        html = tpl.render(**common, event=event)
        event_dir = OUTPUT_DIR / "events" / event["slug"]
        event_dir.mkdir(parents=True, exist_ok=True)
        (event_dir / "index.html").write_text(html, encoding="utf-8")

    # Build speakers list page
    tpl = env.get_template("speakers.html")
    html = tpl.render(**common)
    (OUTPUT_DIR / "speakers").mkdir(exist_ok=True)
    (OUTPUT_DIR / "speakers" / "index.html").write_text(html, encoding="utf-8")

    # Build individual speaker pages
    tpl = env.get_template("speaker.html")
    for speaker in speakers:
        # Find talks by this speaker
        speaker_talks = []
        for event in events:
            for talk in event.get("talks", []):
                if speaker["name"] in talk.get("speakers", []):
                    speaker_talks.append({**talk, "event": event})
        html = tpl.render(**common, speaker=speaker, speaker_talks=speaker_talks)
        speaker_dir = OUTPUT_DIR / "speakers" / speaker["slug"]
        speaker_dir.mkdir(parents=True, exist_ok=True)
        (speaker_dir / "index.html").write_text(html, encoding="utf-8")

    # Build extra pages (about, cfp, etc.)
    tpl = env.get_template("page.html")
    for slug, page in pages.items():
        html = tpl.render(**common, page=page)
        page_dir = OUTPUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    print(f"Built {len(events)} events, {len(speakers)} speakers, {len(pages)} pages")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    build()
