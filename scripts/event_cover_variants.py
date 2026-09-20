#!/usr/bin/env python3
"""Собрать webp-варианты обложек событий рядом с исходными картинками.

Фото спикеров давно лежат в webp со srcset, а обложки событий так и остались
одним большим JPEG на все случаи: и в шапке события, где картинка занимает
352px, и на карточке в списке, и на мобильном. Этот скрипт дописывает рядом
с каждой обложкой её webp-версии:

    static/images/events/{имя}.webp       исходный размер (не больше 1200px)
    static/images/events/{имя}-768.webp   для десктопа с retina
    static/images/events/{имя}-540.webp   для мобильного

`build.py` сам замечает эти файлы и собирает из них `<picture>`
(см. `event_cover_variants` и `templates/partials/cover.html`).

Исходный JPEG остаётся на месте и остаётся тем, что указано в `cover`:
он уходит в og:image, а туда webp кладут не все соцсети. Браузеры его не
скачивают — им достаётся webp из `<source>`.

Запуск:
    python3 scripts/event_cover_variants.py             # все обложки
    python3 scripts/event_cover_variants.py 28-black    # обложки одного события
    python3 scripts/event_cover_variants.py --dry-run
"""

import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EVENTS_DIR = ROOT / "content" / "events"

# Обложку нигде не показывают крупнее ~740px (мобильный во всю ширину), так
# что исходник выше 1200px — это запас на retina и не более того.
MAX_WIDTH = 1200
# Ширины под реальные места показа: 352px в шапке и 384px на карточке
# (×2 на retina) и полная ширина на мобильном.
VARIANT_WIDTHS = (540, 768)
# Та же планка, что у фотографий спикеров (scripts/localize_speaker_photos.py).
QUALITY = 82

COVER_FIELDS = ("cover", "cover_desktop")


def cover_paths(event_file: Path) -> list[str]:
    """Значения cover/cover_desktop из front matter события."""
    text = event_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    _, _, rest = text.partition("---")
    front_matter, _, _ = rest.partition("\n---")
    data = yaml.safe_load(front_matter) or {}
    return [str(data.get(field) or "").strip() for field in COVER_FIELDS]


def variants_for(source: Path) -> list[tuple[Path, int]]:
    """Какие файлы надо получить из этой картинки: (путь, ширина)."""
    with Image.open(source) as image:
        width = image.width

    full_width = min(width, MAX_WIDTH)
    targets = [(source.with_suffix(".webp"), full_width)]
    for target_width in VARIANT_WIDTHS:
        # Апскейл бессмысленен: вариант шире исходника — тот же исходник.
        if target_width < full_width:
            targets.append(
                (source.with_name(f"{source.stem}-{target_width}.webp"), target_width)
            )
    return targets


def write_variant(source: Path, target: Path, width: int) -> int:
    with Image.open(source) as image:
        image = image.convert("RGB")
        if image.width > width:
            ratio = width / image.width
            image = image.resize(
                (width, max(1, round(image.height * ratio))), Image.LANCZOS
            )
        image.save(target, "WEBP", quality=QUALITY, method=6)
    return target.stat().st_size


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slugs", nargs="*", help="слаги событий (по умолчанию — все)")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что будет сделано, ничего не записывая")
    args = parser.parse_args(argv)

    files = sorted(EVENTS_DIR.glob("*.md"))
    if args.slugs:
        wanted = set(args.slugs)
        files = [f for f in files if f.stem in wanted]
        missing = wanted - {f.stem for f in files}
        if missing:
            print("Нет таких событий: " + ", ".join(sorted(missing)), file=sys.stderr)
            return 1

    written = before_total = after_total = 0
    for event_file in files:
        for cover in cover_paths(event_file):
            if not cover.startswith("/static/"):
                continue
            source = ROOT / cover.lstrip("/")
            if not source.exists():
                print(f"ВНИМАНИЕ {event_file.name}: нет файла {cover}", file=sys.stderr)
                continue
            if source.suffix.lower() == ".webp":
                continue

            before = source.stat().st_size
            before_total += before
            for target, width in variants_for(source):
                if args.dry_run:
                    print(f"{source.name} -> {target.name} ({width}px)")
                    written += 1
                    continue
                size = write_variant(source, target, width)
                after_total += size
                written += 1
                print(f"{target.name}: {width}px, {size / 1024:.0f} КБ "
                      f"(исходник {before / 1024:.0f} КБ)")

    if args.dry_run:
        print(f"Готово (вхолостую): {written} файлов")
    else:
        print(f"Готово: {written} файлов, "
              f"{before_total / 1024:.0f} КБ исходников -> "
              f"{after_total / 1024:.0f} КБ вариантов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
