#!/usr/bin/env python3
"""Move speaker photos onto our own static/ and prepare them for srcset.

Most speaker photos used to live on a third-party bucket: if it went away or
changed access, every speaker page would break at once. This script downloads
a speaker's photo (or picks up one already committed), writes two WebP
variants next to each other and rewrites the `photo` field of the speaker's
markdown file:

    static/images/speakers/{slug}.webp       ~1080px, the full-size variant
    static/images/speakers/{slug}-540.webp   540px, what cards actually need

build.py notices the smaller file and emits a srcset, so a 280px card no
longer downloads a 1080px photo.

Usage:
    python3 scripts/localize_speaker_photos.py            # all speakers
    python3 scripts/localize_speaker_photos.py ivan-ivanov  # one speaker
    python3 scripts/localize_speaker_photos.py --dry-run
    python3 scripts/localize_speaker_photos.py --keep-originals
"""

import argparse
import io
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SPEAKERS_DIR = ROOT / "content" / "speakers"
PHOTOS_DIR = ROOT / "static" / "images" / "speakers"
PHOTO_URL_PREFIX = "/static/images/speakers"

FULL_SIZE = 1080
CARD_SIZE = 540
QUALITY = 82
TIMEOUT = 60

PHOTO_LINE_RE = re.compile(r'^photo:\s*.*$', re.MULTILINE)


def read_source(value: str) -> bytes:
    """Fetch the photo a speaker file points at — remote URL or local path."""
    if value.startswith(("http://", "https://")):
        request = urllib.request.Request(
            value, headers={"User-Agent": "moscowqa-site/1.0"}
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()

    local = ROOT / value.lstrip("/")
    return local.read_bytes()


def write_variants(data: bytes, slug: str) -> tuple[Path, Path]:
    """Write the 1080px and 540px WebP variants, returning their paths."""
    image = Image.open(io.BytesIO(data))
    if image.mode in ("RGBA", "LA", "P"):
        # Photos are shown in round/square frames on an opaque background;
        # flattening onto white keeps transparent PNGs from going black.
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image)
    image = image.convert("RGB")

    full = image.copy()
    if max(full.size) > FULL_SIZE:
        full.thumbnail((FULL_SIZE, FULL_SIZE), Image.LANCZOS)
    card = image.copy()
    if max(card.size) > CARD_SIZE:
        card.thumbnail((CARD_SIZE, CARD_SIZE), Image.LANCZOS)

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    full_path = PHOTOS_DIR / f"{slug}.webp"
    card_path = PHOTOS_DIR / f"{slug}-{CARD_SIZE}.webp"
    full.save(full_path, "WEBP", quality=QUALITY, method=6)
    card.save(card_path, "WEBP", quality=QUALITY, method=6)
    return full_path, card_path


def update_photo_field(path: Path, new_value: str) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = f'photo: "{new_value}"'
    updated, count = PHOTO_LINE_RE.subn(replacement, text, count=1)
    if count != 1:
        sys.exit(f"{path.name}: не нашлась строка photo:")
    path.write_text(updated, encoding="utf-8")


def current_photo(path: Path) -> str:
    """Read the raw `photo` value without a full YAML parse.

    A plain read keeps the rest of the file untouched: these files are edited
    by hand and a YAML round-trip would reformat every one of them.
    """
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("photo:"):
            return line.split(":", 1)[1].strip().strip('"\'')
        if line.strip() == "---" and line != "---":
            break
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*", help="Слаги спикеров (по умолчанию — все)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать, что будет сделано, ничего не записывая")
    parser.add_argument("--keep-originals", action="store_true",
                        help="Не удалять исходные файлы, которые заменил webp")
    args = parser.parse_args()

    files = sorted(SPEAKERS_DIR.glob("*.md"))
    if args.slugs:
        wanted = set(args.slugs)
        files = [f for f in files if f.stem in wanted]
        missing = wanted - {f.stem for f in files}
        if missing:
            sys.exit("Нет таких спикеров: " + ", ".join(sorted(missing)))

    converted = skipped = failed = 0
    for path in files:
        slug = path.stem
        photo = current_photo(path)
        target = f"{PHOTO_URL_PREFIX}/{slug}.webp"

        if not photo:
            skipped += 1
            continue
        if photo == target:
            skipped += 1
            continue

        if args.dry_run:
            print(f"{slug}: {photo} -> {target}")
            converted += 1
            continue

        try:
            data = read_source(photo)
        except Exception as error:  # noqa: BLE001 — сеть или отсутствующий файл
            print(f"{slug}: не удалось прочитать {photo}: {error}", file=sys.stderr)
            failed += 1
            continue

        full_path, card_path = write_variants(data, slug)
        update_photo_field(path, target)

        # The source file this replaces, when it was already in the repo.
        if not photo.startswith(("http://", "https://")) and not args.keep_originals:
            old = ROOT / photo.lstrip("/")
            if old.exists() and old.resolve() != full_path.resolve():
                old.unlink()

        print(
            f"{slug}: {full_path.stat().st_size // 1024}KB + "
            f"{card_path.stat().st_size // 1024}KB"
        )
        converted += 1

    print(f"\nобработано: {converted}, пропущено: {skipped}, ошибок: {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
