"""Shared helpers: load speakers, match names, update .md files."""
import re
import time
import yaml
from pathlib import Path

SPEAKERS_DIR = Path(__file__).parent.parent / "content" / "speakers"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def load_speakers() -> list[dict]:
    """Return list of dicts with speaker data + raw file text."""
    speakers = []
    for path in sorted(SPEAKERS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) >= 3 and parts[0].strip() == "":
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            meta = {}
            body = text
        speakers.append(
            {
                "slug": path.stem,
                "path": path,
                "name": meta.get("name", ""),
                "meta": meta,
                "body": body,
                "existing_urls": {
                    t.get("url", "") for t in (meta.get("external_talks") or [])
                },
            }
        )
    return speakers


def normalize_name(name: str) -> str:
    """Lowercase + collapse whitespace for loose matching."""
    return re.sub(r"\s+", " ", name.strip().lower())


def build_name_index(speakers: list[dict]) -> dict[str, dict]:
    """Map normalized speaker name → speaker dict."""
    return {normalize_name(s["name"]): s for s in speakers if s["name"]}


def find_speaker(name_index: dict, candidate: str):
    """Try to match a candidate name against the speaker index."""
    key = normalize_name(candidate)
    if key in name_index:
        return name_index[key]
    # partial match: candidate words all appear in a known name
    words = key.split()
    for known, speaker in name_index.items():
        if all(w in known for w in words):
            return speaker
    return None


def save_speaker(speaker: dict, new_talks: list[dict]) -> int:
    """Append new_talks to external_talks in the speaker's .md file.

    Returns number of talks actually added.
    """
    added = []
    for talk in new_talks:
        if talk.get("url", "") not in speaker["existing_urls"]:
            added.append(talk)
            speaker["existing_urls"].add(talk.get("url", ""))

    if not added:
        return 0

    meta = speaker["meta"]
    existing = list(meta.get("external_talks") or [])
    meta["external_talks"] = existing + added

    # Dump back to file preserving structure
    path: Path = speaker["path"]
    front = yaml.dump(
        meta,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    path.write_text(f"---\n{front}---\n\n{speaker['body']}\n", encoding="utf-8")
    return len(added)


def polite_sleep(seconds: float = 1.0):
    time.sleep(seconds)
