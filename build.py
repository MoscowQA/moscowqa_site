#!/usr/bin/env python3
"""Static site generator for MoscowQA community website.

Reads markdown content from content/ directory, applies Jinja2 templates,
and outputs static HTML to dist/ directory.
"""
import os
import shutil
import yaml
import markdown
from datetime import date
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "dist"

BASE_URL = os.environ.get("BASE_URL")
SITE_URL = os.environ.get("SITE_URL", "https://moscowqa.ru/")

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


def generate_sitemap(events, speakers, pages):
    """Generate sitemap.xml for search engines."""
    today = date.today().isoformat()
    urls = []

    # Index page
    urls.append({"loc": f"{SITE_URL}/", "changefreq": "weekly", "priority": "1.0"})
    # Events list
    urls.append({"loc": f"{SITE_URL}/events/", "changefreq": "weekly", "priority": "0.9"})
    # Speakers list
    urls.append({"loc": f"{SITE_URL}/speakers/", "changefreq": "weekly", "priority": "0.8"})

    # Individual events
    for event in events:
        urls.append({
            "loc": f"{SITE_URL}/events/{event['slug']}/",
            "lastmod": event.get("date", today),
            "changefreq": "monthly",
            "priority": "0.7",
        })

    # Individual speakers
    for speaker in speakers:
        urls.append({
            "loc": f"{SITE_URL}/speakers/{speaker['slug']}/",
            "changefreq": "monthly",
            "priority": "0.6",
        })

    # Extra pages
    for slug in pages:
        urls.append({
            "loc": f"{SITE_URL}/{slug}/",
            "changefreq": "monthly",
            "priority": "0.5",
        })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        if "lastmod" in u:
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines)


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
    env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}

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
        "base_url": BASE_URL,
    }

    # Map speaker display names to their file slugs and data for URL/photo generation
    speaker_slugs = {s["name"]: s["slug"] for s in speakers}
    speaker_by_name = {s["name"]: s for s in speakers}

    common = {"site": site, "events": events, "speakers": speakers, "base": BASE_URL,
              "speaker_slugs": speaker_slugs, "speaker_by_name": speaker_by_name,
              "site_url": SITE_URL}

    # Build index page
    tpl = env.get_template("index.html")
    html = tpl.render(**common, latest_events=events[:6],
                      canonical_url=f"{SITE_URL}/")
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")

    # Build events list page
    tpl = env.get_template("events.html")
    html = tpl.render(**common, canonical_url=f"{SITE_URL}/events/")
    (OUTPUT_DIR / "events").mkdir(exist_ok=True)
    (OUTPUT_DIR / "events" / "index.html").write_text(html, encoding="utf-8")

    # Build individual event pages
    tpl = env.get_template("event.html")
    for event in events:
        canonical = f"{SITE_URL}/events/{event['slug']}/"
        html = tpl.render(**common, event=event, canonical_url=canonical)
        event_dir = OUTPUT_DIR / "events" / event["slug"]
        event_dir.mkdir(parents=True, exist_ok=True)
        (event_dir / "index.html").write_text(html, encoding="utf-8")

    # Build speakers list page
    tpl = env.get_template("speakers.html")
    html = tpl.render(**common, canonical_url=f"{SITE_URL}/speakers/")
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
        canonical = f"{SITE_URL}/speakers/{speaker['slug']}/"
        html = tpl.render(**common, speaker=speaker, speaker_talks=speaker_talks,
                          canonical_url=canonical)
        speaker_dir = OUTPUT_DIR / "speakers" / speaker["slug"]
        speaker_dir.mkdir(parents=True, exist_ok=True)
        (speaker_dir / "index.html").write_text(html, encoding="utf-8")

    # Build extra pages (about, cfp, etc.)
    tpl = env.get_template("page.html")
    for slug, page in pages.items():
        canonical = f"{SITE_URL}/{slug}/"
        html = tpl.render(**common, page=page, canonical_url=canonical)
        page_dir = OUTPUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    # Generate sitemap.xml
    sitemap = generate_sitemap(events, speakers, pages)
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    # Generate robots.txt
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    print(f"Built {len(events)} events, {len(speakers)} speakers, {len(pages)} pages")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    build()
