#!/usr/bin/env python3
"""Static site generator for MoscowQA community website.

Reads markdown content from content/ directory, applies Jinja2 templates,
and outputs static HTML to dist/ directory.
"""
import os
import re
import shutil
import yaml
import markdown
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from jinja2 import Environment, FileSystemLoader
from PIL import Image

# Completed vs. upcoming status is now determined on the frontend in
# static/js/events-status.js, based on the visitor's current date. The build
# step intentionally does not set `event.completed`; templates render both
# states and let JS toggle `.is-upcoming` / `.is-completed` classes.

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "dist"

BASE_URL = os.environ.get("BASE_URL", "")
SITE_URL = os.environ.get("SITE_URL", "https://moscowqa.ru")


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean setting from the environment."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Timepad widget -------------------------------------------------------
# Registration/announcement widgets are embedded from Timepad's loader. See
# TIMEPAD_WIDGET.md for the whole picture; everything here is overridable
# through the environment so the same build works on staging and production.
TIMEPAD_LOADER = os.environ.get(
    "TIMEPAD_LOADER", "https://timepad.ru/js/tpwf/loader/min/loader.js"
)
# ID of the Timepad-side customization (styles/templates/behaviour). Empty
# means "use Timepad's default customization".
TIMEPAD_CUSTOMIZATION_ID = os.environ.get("TIMEPAD_CUSTOMIZATION_ID", "")
# Numeric Timepad organization id — only needed for the event list widget.
TIMEPAD_ORG_ID = os.environ.get("TIMEPAD_ORG_ID", "")
TIMEPAD_LOCALE = os.environ.get("TIMEPAD_LOCALE", "ru")
# Master switch and the mode used by events that do not pick one themselves.
# Default is "popup": the form opens over the page from the registration card,
# so visitors don't have to scroll past the programme to reach it.
TIMEPAD_WIDGET_ENABLED = env_flag("TIMEPAD_WIDGET", default=True)
TIMEPAD_DEFAULT_MODE = os.environ.get("TIMEPAD_WIDGET_MODE", "popup")
# The event list ("афиша") widget is off until an org id is configured.
TIMEPAD_LIST_WIDGET_ENABLED = env_flag("TIMEPAD_LIST_WIDGET", default=False)
# Selector of the elements that open the widget in popup mode.
TIMEPAD_TRIGGER_SELECTOR = os.environ.get(
    "TIMEPAD_TRIGGER_SELECTOR", ".js-timepad-trigger"
)

# Timepad event URLs look like https://moscowqa.timepad.ru/event/4046132/ —
# the trailing number is the event id the widget needs.
TIMEPAD_EVENT_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?timepad\.ru/event/(\d+)", re.IGNORECASE
)

# Accepted values of the per-event `timepad_widget` front matter field.
TIMEPAD_MODE_ALIASES = {
    "inline": "inline",
    "iframe": "inline",
    "form": "inline",
    "popup": "popup",
    "button": "popup",
    "off": "off",
    "none": "off",
    "no": "off",
    "false": "off",
}


def parse_timepad_event_id(event: dict) -> str:
    """Return the Timepad event id for an event, or "" when there is none.

    An explicit `timepad_event_id` in the front matter wins; otherwise the id
    is taken from `registration_link` when it points at Timepad. Events hosted
    elsewhere (a partner's landing page) simply get no widget.
    """
    explicit = event.get("timepad_event_id")
    if explicit not in (None, ""):
        return str(explicit).strip()

    link = (event.get("registration_link") or "").strip()
    match = TIMEPAD_EVENT_URL_RE.match(link)
    return match.group(1) if match else ""


def resolve_timepad_mode(event: dict, default_mode: str) -> str:
    """Resolve how the registration widget is shown for a single event.

    Returns "inline" (a form in the page), "popup" (opened by a button) or
    "off". Events without a Timepad id are always "off".
    """
    if not event.get("timepad_event_id"):
        return "off"

    raw = event.get("timepad_widget")
    if raw is None or raw == "":
        return default_mode
    if raw is True:
        return default_mode
    if raw is False:
        return "off"
    return TIMEPAD_MODE_ALIASES.get(str(raw).strip().lower(), default_mode)


# --- Calendar -------------------------------------------------------------
# Every event page ships an .ics file next to it and a Google Calendar link,
# so "иду" does not depend on the visitor remembering the date.
#
# Times are written in UTC: Moscow has been a fixed UTC+3 with no DST since
# 2014, so the conversion is unambiguous and the file needs no VTIMEZONE.
MOSCOW_OFFSET = timedelta(hours=3)
# Events only have to announce a `date`. A `time` ("19:00", optionally with
# `end_time`) turns the calendar entry into a real interval; without it the
# entry is an all-day one, which is the honest rendering of "we announced the
# day, not the hour".
DEFAULT_EVENT_DURATION = timedelta(hours=3)

TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")


def parse_event_date(value) -> date | None:
    """Read a front matter `date` — a quoted ISO string or a YAML date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_event_time(value) -> time | None:
    """Read a front matter `time`/`end_time` ("19:00"), or None when absent."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    match = TIME_RE.match(str(value).strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def event_calendar_span(event: dict):
    """Return (start, end, all_day) for an event, or None without a date.

    For an all-day entry the bounds are dates and `end` is the exclusive next
    day — the form both iCalendar and Google Calendar expect. Otherwise they
    are timezone-aware datetimes in UTC.
    """
    day = parse_event_date(event.get("date"))
    if day is None:
        return None

    start_time = parse_event_time(event.get("time"))
    if start_time is None:
        return day, day + timedelta(days=1), True

    start = datetime.combine(day, start_time, tzinfo=timezone.utc) - MOSCOW_OFFSET
    end_time = parse_event_time(event.get("end_time"))
    if end_time is None:
        return start, start + DEFAULT_EVENT_DURATION, False

    end = datetime.combine(day, end_time, tzinfo=timezone.utc) - MOSCOW_OFFSET
    if end <= start:
        # An event that runs past midnight, e.g. 19:00 — 00:30.
        end += timedelta(days=1)
    return start, end, False


def escape_ics_text(value: str) -> str:
    """Escape a value for an iCalendar TEXT field (RFC 5545 §3.3.11)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold_ics_line(line: str) -> str:
    """Fold one content line to the 75-octet limit (RFC 5545 §3.1).

    Folding counts bytes, not characters, and Cyrillic titles are two bytes
    apiece — so the split walks characters and never cuts one in half.
    """
    limit = 75
    folded, current, size = [], [], 0
    for char in line:
        char_size = len(char.encode("utf-8"))
        if size + char_size > limit:
            folded.append("".join(current))
            # Continuation lines start with a space, which eats one octet.
            current, size, limit = [char], char_size, 74
        else:
            current.append(char)
            size += char_size
    folded.append("".join(current))
    return "\r\n ".join(folded)


def build_ics(event: dict, url: str, now: datetime = None) -> str:
    """Render a single-event iCalendar file, or "" for an event with no date."""
    span = event_calendar_span(event)
    if span is None:
        return ""
    start, end, all_day = span

    if all_day:
        start_line = f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}"
        end_line = f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}"
    else:
        start_line = f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}"
        end_line = f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}"

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    description = " ".join(
        part for part in [event.get("short_description") or "", url] if part
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Moscow QA//moscowqa.ru//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event.get('slug', 'event')}@moscowqa.ru",
        f"DTSTAMP:{stamp}",
        start_line,
        end_line,
        f"SUMMARY:{escape_ics_text(event.get('title', 'Moscow QA'))}",
        f"DESCRIPTION:{escape_ics_text(description)}",
    ]
    if event.get("address"):
        lines.append(f"LOCATION:{escape_ics_text(event['address'])}")
    if url:
        lines.append(f"URL:{url}")
    lines += ["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"]

    return "".join(fold_ics_line(line) + "\r\n" for line in lines)


def google_calendar_url(event: dict, url: str) -> str:
    """Build a "add to Google Calendar" link, or "" for an event with no date."""
    span = event_calendar_span(event)
    if span is None:
        return ""
    start, end, all_day = span
    fmt = "%Y%m%d" if all_day else "%Y%m%dT%H%M%SZ"

    params = {
        "action": "TEMPLATE",
        "text": event.get("title", "Moscow QA"),
        "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
        "details": " ".join(
            part for part in [event.get("short_description") or "", url] if part
        ),
    }
    if event.get("address"):
        params["location"] = event["address"]
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


md = markdown.Markdown(extensions=["meta", "tables", "fenced_code", "toc"])


def slugify(text: str) -> str:
    """Transliterate Russian text into a URL-friendly slug."""
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    result = []
    for char in text.lower():
        if char in translit_map:
            result.append(translit_map[char])
        elif char.isalnum():
            result.append(char)
        elif char in ' -':
            result.append('-')
    slug = ''.join(result)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]


def slugify_talk(title: str, manual_slug: str = None) -> str:
    """Generate URL-friendly slug from Russian talk title."""
    if manual_slug:
        return manual_slug
    return slugify(title)


# --- Topic tags -----------------------------------------------------------
# Talks carry free-form `tags` in the front matter ("автоматизация",
# "нагрузочное", "AI"). Every tag gets a page at /tags/{слаг}/ listing the
# talks under it — a hundred talks are otherwise only reachable through the
# meetup they happened at.


def normalize_tag(value) -> str:
    """Trim a tag as written in the front matter and collapse its spaces."""
    return re.sub(r"\s+", " ", str(value).strip())


def talk_tag_links(talk: dict) -> list[dict]:
    """Return [{name, slug}] for a talk, skipping blanks and duplicates."""
    links, seen = [], set()
    for raw in talk.get("tags") or []:
        name = normalize_tag(raw)
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        links.append({"name": name, "slug": slug})
    return links


def collect_tags(events: list[dict]) -> list[dict]:
    """Group talks by tag, most used first, then alphabetically.

    Events arrive newest first, so each tag's talks keep that order. Tags that
    differ only in case or spacing share a slug and therefore a page; the
    spelling that reaches the page title is the one used by the newest talk.
    """
    by_slug: dict[str, dict] = {}
    for event in events:
        for talk in event.get("talks", []):
            for link in talk.get("tag_links") or []:
                entry = by_slug.setdefault(
                    link["slug"],
                    {"name": link["name"], "slug": link["slug"], "talks": []},
                )
                entry["talks"].append({**talk, "event": event})

    tags = list(by_slug.values())
    tags.sort(key=lambda tag: (-len(tag["talks"]), tag["name"].lower()))
    return tags


def normalize_search_text(text: str) -> str:
    """Fold text to the form the frontend search compares against.

    Lowercase, "ё" folded to "е" and whitespace collapsed, so a visitor gets
    the same matches no matter how they type. static/js/speakers-search.js
    applies exactly the same rules to the query.
    """
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def build_talks_by_speaker(events: list[dict]) -> dict[str, list[dict]]:
    """Map a speaker's display name to their MoscowQA talks.

    The link is the exact name match documented in CLAUDE.md: values in
    `talks[].speakers` must equal the `name` of a file in content/speakers/.
    Events arrive sorted newest first, so each list keeps that order.
    """
    talks_by_speaker: dict[str, list[dict]] = {}
    for event in events:
        for talk in event.get("talks", []):
            for speaker_name in talk.get("speakers", []):
                talks_by_speaker.setdefault(speaker_name, []).append({
                    **talk,
                    "event": event,
                })
    return talks_by_speaker


def speaker_search_text(speaker: dict, talks: list[dict]) -> str:
    """Build the haystack the speakers page is filtered by in the browser.

    Covers the name, the company and the titles of both MoscowQA and external
    talks, so a visitor can look a speaker up by topic as well as by name. The
    slug goes in too: it is a latin transliteration of the name, which makes
    "klenov" find "Александр Кленов".
    """
    parts = [
        speaker.get("name", ""),
        speaker.get("company", ""),
        (speaker.get("slug") or "").replace("-", " "),
    ]
    for talk in talks:
        parts.append(talk.get("title", ""))
    for talk in speaker.get("external_talks") or []:
        parts.append(talk.get("title", ""))
        # Conference name, e.g. "Heisenbug 2025 Autumn".
        parts.append(talk.get("event", ""))

    # Speakers with dozens of external talks repeat the same conference name
    # over and over; dropping the duplicates keeps the attribute readable.
    seen = set()
    unique = []
    for part in parts:
        normalized = normalize_search_text(part or "")
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return " ".join(unique)


# --- Speaker photos -------------------------------------------------------
# Photos live in static/images/speakers/ as two WebP variants written by
# scripts/localize_speaker_photos.py: {slug}.webp (~1080px) and
# {slug}-540.webp. Cards and avatars are far smaller than 1080px, so the
# templates get a srcset and the browser picks the cheaper file.
PHOTO_CARD_WIDTH = 540


def speaker_photo_variants(photo: str) -> dict:
    """Return {"src", "small", "srcset"} for a speaker photo.

    `srcset` is empty for a photo hosted elsewhere or one without the smaller
    variant on disk — those are rendered as a plain <img> exactly as before.
    """
    photo = (photo or "").strip()
    if not photo:
        return {"src": "", "small": "", "srcset": "", "absolute": ""}

    # og:image and schema.org need an absolute URL; a local photo is a path.
    absolute = f"{SITE_URL}{photo}" if photo.startswith("/") else photo
    variants = {"src": photo, "small": photo, "srcset": "", "absolute": absolute}
    if not photo.startswith("/static/"):
        return variants

    full_path = ROOT / photo.lstrip("/")
    small_path = full_path.with_name(f"{full_path.stem}-{PHOTO_CARD_WIDTH}.webp")
    if not (full_path.exists() and small_path.exists()):
        return variants

    small_url = f"{photo.rsplit('/', 1)[0]}/{small_path.name}"
    with Image.open(full_path) as image:
        full_width = image.width

    variants["small"] = small_url
    variants["srcset"] = (
        f"{small_url} {PHOTO_CARD_WIDTH}w, {photo} {full_width}w"
    )
    return variants


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

            # Add slugs for talks
            for idx, talk in enumerate(event.get("talks", [])):
                talk["index"] = idx
                talk["slug"] = slugify_talk(
                    talk["title"],
                    talk.get("slug")
                )
                talk["tag_links"] = talk_tag_links(talk)

            # Timepad registration widget: the id comes from the event's
            # Timepad link unless the front matter names one explicitly.
            event["timepad_event_id"] = parse_timepad_event_id(event)
            event["timepad_widget_mode"] = resolve_timepad_mode(
                event, TIMEPAD_DEFAULT_MODE
            )

            # "Add to calendar": the .ics file is written next to the event
            # page in build(); the Google link is built here because it needs
            # the absolute URL of that page.
            event["google_calendar_url"] = google_calendar_url(
                event, f"{SITE_URL}/events/{event['slug']}/"
            )

            # Note: past-vs-upcoming detection has moved to the browser
            # (static/js/events-status.js). Templates emit `data-event-date`
            # on cards and JS applies `.is-completed` / `.is-upcoming`.
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
            speaker["photo_variants"] = speaker_photo_variants(speaker.get("photo"))
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


def generate_sitemap(events, speakers, pages, tags=()):
    """Generate sitemap.xml for search engines."""
    today = date.today().isoformat()
    urls = []

    # Index page
    urls.append({"loc": f"{SITE_URL}/", "changefreq": "weekly", "priority": "1.0"})
    # Events list
    urls.append({"loc": f"{SITE_URL}/events/", "changefreq": "weekly", "priority": "0.9"})
    # Speakers list
    urls.append({"loc": f"{SITE_URL}/speakers/", "changefreq": "weekly", "priority": "0.8"})
    # Presentations (external talks aggregator)
    urls.append({"loc": f"{SITE_URL}/presentations/", "changefreq": "weekly", "priority": "0.75"})

    # Individual events
    for event in events:
        urls.append({
            "loc": f"{SITE_URL}/events/{event['slug']}/",
            "lastmod": event.get("date", today),
            "changefreq": "monthly",
            "priority": "0.7",
        })

    # Individual talks
    for event in events:
        for talk in event.get("talks", []):
            urls.append({
                "loc": f"{SITE_URL}/events/{event['slug']}/talks/{talk['slug']}/",
                "lastmod": event.get("date", today),
                "changefreq": "monthly",
                "priority": "0.65",
            })

    # Individual speakers
    for speaker in speakers:
        urls.append({
            "loc": f"{SITE_URL}/speakers/{speaker['slug']}/",
            "changefreq": "monthly",
            "priority": "0.6",
        })

    # Topic tags
    if tags:
        urls.append({
            "loc": f"{SITE_URL}/tags/",
            "changefreq": "weekly",
            "priority": "0.6",
        })
        for tag in tags:
            urls.append({
                "loc": f"{SITE_URL}/tags/{tag['slug']}/",
                "changefreq": "monthly",
                "priority": "0.55",
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
        "description": "QA-сообщество Москвы — митапы по тестированию",
        "telegram": "https://t.me/moscowqa",
        "youtube": "https://www.youtube.com/@moscowqa",
        "timepad": "https://moscowqa.timepad.ru",
        "base_url": BASE_URL,
        # Consumed by templates/partials/timepad.html — see TIMEPAD_WIDGET.md.
        "timepad_widget": {
            "enabled": TIMEPAD_WIDGET_ENABLED,
            "loader": TIMEPAD_LOADER,
            "customization_id": TIMEPAD_CUSTOMIZATION_ID,
            "org_id": TIMEPAD_ORG_ID,
            "locale": TIMEPAD_LOCALE,
            "trigger_selector": TIMEPAD_TRIGGER_SELECTOR,
            "default_mode": TIMEPAD_DEFAULT_MODE,
            "list_enabled": TIMEPAD_LIST_WIDGET_ENABLED and bool(TIMEPAD_ORG_ID),
        },
    }

    # Map speaker display names to their file slugs and data for URL/photo generation
    speaker_slugs = {s["name"]: s["slug"] for s in speakers}
    speaker_by_name = {s["name"]: s for s in speakers}

    # Talks per speaker: used both by the individual speaker pages and by the
    # search index of the speakers list.
    talks_by_speaker = build_talks_by_speaker(events)
    for speaker in speakers:
        speaker["search_text"] = speaker_search_text(
            speaker, talks_by_speaker.get(speaker["name"], [])
        )

    # Topic tags: talks grouped by the `tags` of their front matter.
    tags = collect_tags(events)

    common = {"site": site, "events": events, "speakers": speakers, "base": BASE_URL,
              "speaker_slugs": speaker_slugs, "speaker_by_name": speaker_by_name,
              "site_url": SITE_URL, "tags": tags}

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

        # iCalendar file for the "в календарь" button. newline="" keeps the
        # CRLF line endings RFC 5545 asks for on every platform.
        ics = build_ics(event, canonical)
        if ics:
            (event_dir / "event.ics").write_text(
                ics, encoding="utf-8", newline=""
            )

    # Build individual talk pages
    tpl = env.get_template("talk.html")
    for event in events:
        for talk in event.get("talks", []):
            # Prepare talk data with full context
            talk_data = {
                **talk,
                "event": event,
                "event_slug": event["slug"]
            }

            # Find speakers with full data
            talk_speakers = []
            for speaker_name in talk.get("speakers", []):
                speaker_data = speaker_by_name.get(speaker_name, {})
                talk_speakers.append({
                    "name": speaker_name,
                    "slug": speaker_slugs.get(speaker_name, ""),
                    # Avatars are 40–80px, so the card-sized variant is plenty.
                    "photo": (speaker_data.get("photo_variants") or {}).get("small")
                             or speaker_data.get("photo"),
                    "company": speaker_data.get("company", talk.get("company")),
                })
            talk_data["speaker_details"] = talk_speakers

            # Get other talks from same event
            other_talks = [
                t for t in event.get("talks", [])
                if t.get("slug") != talk["slug"]
            ]

            canonical = f"{SITE_URL}/events/{event['slug']}/talks/{talk['slug']}/"
            html = tpl.render(
                **common,
                talk=talk_data,
                other_talks=other_talks,
                canonical_url=canonical
            )

            # Create directory structure
            talk_dir = OUTPUT_DIR / "events" / event["slug"] / "talks" / talk["slug"]
            talk_dir.mkdir(parents=True, exist_ok=True)
            (talk_dir / "index.html").write_text(html, encoding="utf-8")

    # Build speakers list page
    tpl = env.get_template("speakers.html")
    html = tpl.render(**common, canonical_url=f"{SITE_URL}/speakers/")
    (OUTPUT_DIR / "speakers").mkdir(exist_ok=True)
    (OUTPUT_DIR / "speakers" / "index.html").write_text(html, encoding="utf-8")

    # Build individual speaker pages
    tpl = env.get_template("speaker.html")
    for speaker in speakers:
        speaker_talks = talks_by_speaker.get(speaker["name"], [])
        canonical = f"{SITE_URL}/speakers/{speaker['slug']}/"
        html = tpl.render(**common, speaker=speaker, speaker_talks=speaker_talks,
                          canonical_url=canonical)
        speaker_dir = OUTPUT_DIR / "speakers" / speaker["slug"]
        speaker_dir.mkdir(parents=True, exist_ok=True)
        (speaker_dir / "index.html").write_text(html, encoding="utf-8")

    # Build presentations (all external talks) page
    all_talks = []
    for speaker in speakers:
        for talk in speaker.get("external_talks") or []:
            all_talks.append({
                **talk,
                "speaker_name": speaker["name"],
                "speaker_slug": speaker["slug"],
                "speaker_company": speaker.get("company", ""),
            })
    all_talks.sort(key=lambda t: t.get("date") or "", reverse=True)
    speakers_with_talks = sum(
        1 for s in speakers if s.get("external_talks")
    )
    tpl = env.get_template("presentations.html")
    html = tpl.render(
        **common,
        all_talks=all_talks,
        total_count=len(all_talks),
        speakers_with_talks=speakers_with_talks,
        canonical_url=f"{SITE_URL}/presentations/",
    )
    (OUTPUT_DIR / "presentations").mkdir(exist_ok=True)
    (OUTPUT_DIR / "presentations" / "index.html").write_text(html, encoding="utf-8")

    # Build tag pages: an index of every topic plus one page per tag.
    if tags:
        tpl = env.get_template("tags.html")
        html = tpl.render(**common, canonical_url=f"{SITE_URL}/tags/")
        (OUTPUT_DIR / "tags").mkdir(exist_ok=True)
        (OUTPUT_DIR / "tags" / "index.html").write_text(html, encoding="utf-8")

        tpl = env.get_template("tag.html")
        for tag in tags:
            canonical = f"{SITE_URL}/tags/{tag['slug']}/"
            html = tpl.render(**common, tag=tag, canonical_url=canonical)
            tag_dir = OUTPUT_DIR / "tags" / tag["slug"]
            tag_dir.mkdir(parents=True, exist_ok=True)
            (tag_dir / "index.html").write_text(html, encoding="utf-8")

    # Page slugs that use a dedicated template instead of the generic page.html
    custom_page_templates = {"organizers": "organizers.html"}

    # Build extra pages (about, cfp, etc.)
    tpl = env.get_template("page.html")
    for slug, page in pages.items():
        if slug in custom_page_templates:
            continue
        canonical = f"{SITE_URL}/{slug}/"
        html = tpl.render(**common, page=page, canonical_url=canonical)
        page_dir = OUTPUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    # Build pages with dedicated templates (e.g. organizers)
    for slug, template_name in custom_page_templates.items():
        page = pages.get(slug)
        if not page:
            continue
        tpl = env.get_template(template_name)
        canonical = f"{SITE_URL}/{slug}/"
        html = tpl.render(**common, page=page, canonical_url=canonical)
        page_dir = OUTPUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    # 404 page: GitHub Pages serves it for any unknown path. It is not part of
    # the sitemap on purpose — it must never be indexed.
    tpl = env.get_template("404.html")
    (OUTPUT_DIR / "404.html").write_text(
        tpl.render(**common, canonical_url=""), encoding="utf-8"
    )

    # Generate sitemap.xml
    sitemap = generate_sitemap(events, speakers, pages, tags)
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    # Generate robots.txt
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    talk_count = sum(len(e.get("talks", [])) for e in events)
    widget_count = sum(
        1 for e in events if e.get("timepad_widget_mode", "off") != "off"
    )
    tagged_talks = sum(
        1 for e in events for t in e.get("talks", []) if t.get("tag_links")
    )
    print(f"Built {len(events)} events, {talk_count} talks, {len(speakers)} speakers, {len(pages)} pages")
    print(f"Tags: {len(tags)} topics, {tagged_talks}/{talk_count} talks tagged")
    if TIMEPAD_WIDGET_ENABLED:
        print(f"Timepad widget: {widget_count}/{len(events)} events, "
              f"list widget {'on' if site['timepad_widget']['list_enabled'] else 'off'}")
    else:
        print("Timepad widget: disabled (TIMEPAD_WIDGET=0)")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    build()
