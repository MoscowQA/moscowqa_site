#!/usr/bin/env python3
"""Проверка контента и собранного сайта — то, что CLAUDE.md просит ловить глазами.

Что проверяется:

* события — обязательные поля, ISO-дата, формат времени, известный `type`,
  номер или обложка, существование файлов обложек и их webp-вариантов,
  вид ссылок;
* доклады — есть название и спикеры, слаги не совпадают внутри события,
  **каждое имя в `talks[].speakers` дословно совпадает с `name` спикера**
  (иначе доклад молча не свяжется с профилем);
* спикеры — уникальные имена, фото лежит у нас и оба варианта на месте;
* собранный `dist/` — внутренние ссылки ведут на существующие страницы,
  а `fonts.css` ссылается на наши woff2, а не на чужой CDN.

Ошибки (`ОШИБКА`) роняют проверку, замечания (`ВНИМАНИЕ`) — нет.

Usage:
    python3 scripts/validate_content.py
    python3 scripts/validate_content.py --no-links   # без проверки dist/
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

EVENTS_DIR = ROOT / "content" / "events"
SPEAKERS_DIR = ROOT / "content" / "speakers"
DIST_DIR = ROOT / "dist"

EVENT_TYPES = {"Offline", "Online", "Offline + Online"}
LINK_FIELDS = ("registration_link", "video_link", "photos_link")

errors: list[str] = []
warnings: list[str] = []


def error(where: str, message: str) -> None:
    errors.append(f"ОШИБКА  {where}: {message}")


def warn(where: str, message: str) -> None:
    warnings.append(f"ВНИМАНИЕ {where}: {message}")


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        error(path.name, "нет YAML front matter между --- ---")
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        error(path.name, f"не читается YAML: {exc}")
        return {}
    if not isinstance(data, dict):
        error(path.name, "front matter не словарь")
        return {}
    return data


def check_speakers() -> dict[str, dict]:
    """Проверить профили спикеров и вернуть их по имени."""
    by_name: dict[str, dict] = {}
    for path in sorted(SPEAKERS_DIR.glob("*.md")):
        data = front_matter(path)
        if not data:
            continue
        where = f"content/speakers/{path.name}"

        name = (data.get("name") or "").strip()
        if not name:
            error(where, "нет обязательного поля name")
            continue
        if name in by_name:
            error(where, f"имя «{name}» уже занято другим файлом")
        by_name[name] = data

        photo = (data.get("photo") or "").strip()
        if not photo:
            warn(where, "нет фото")
        elif photo.startswith(("http://", "https://")):
            warn(where, f"фото лежит снаружи ({photo}) — прогоните make photos")
        else:
            full = ROOT / photo.lstrip("/")
            if not full.exists():
                error(where, f"файла фото нет: {photo}")
            else:
                small = full.with_name(f"{full.stem}-540.webp")
                if not small.exists():
                    warn(where, f"нет варианта для карточек: {small.name}")

        for talk in data.get("external_talks") or []:
            if not isinstance(talk, dict) or not (talk.get("title") or "").strip():
                error(where, "во внешнем докладе нет title")
            elif not (talk.get("event") or "").strip():
                warn(where, f"у внешнего доклада «{talk['title']}» нет event")
    return by_name


def check_events(speakers: dict[str, dict]) -> None:
    numbers: dict[int, str] = {}
    for path in sorted(EVENTS_DIR.glob("*.md")):
        data = front_matter(path)
        if not data:
            continue
        where = f"content/events/{path.name}"

        if not (data.get("title") or "").strip():
            error(where, "нет обязательного поля title")
        if build.parse_event_date(data.get("date")) is None:
            error(where, f"дата не в формате YYYY-MM-DD: {data.get('date')!r}")

        event_type = data.get("type")
        if event_type not in EVENT_TYPES:
            error(where, f"type={event_type!r}, ожидается один из {sorted(EVENT_TYPES)}")

        for field in ("time", "end_time"):
            if data.get(field) not in (None, "") and build.parse_event_time(data[field]) is None:
                error(where, f'{field}={data[field]!r} — нужен формат "ЧЧ:ММ" в кавычках')

        number = data.get("number")
        if number is None:
            if not data.get("cover"):
                error(where, "без number обязательна обложка cover")
        elif not isinstance(number, int):
            error(where, f"number={number!r} — должно быть числом")
        elif number in numbers:
            error(where, f"номер {number} уже у {numbers[number]}")
        else:
            numbers[number] = path.name

        for field in ("cover", "cover_desktop"):
            value = (data.get(field) or "").strip()
            if not value:
                continue
            if not (ROOT / value.lstrip("/")).exists():
                error(where, f"{field}: файла нет — {value}")
            elif not build.event_cover_variants(value)["sources"]:
                # Не ошибка: сайт соберётся и с одним JPEG, просто отдаст
                # его целиком всем подряд. Лечится `make covers`.
                warn(where, f"{field}: нет webp-вариантов, прогоните make covers")

        for field in LINK_FIELDS:
            value = (data.get(field) or "").strip()
            if value and not value.startswith(("http://", "https://")):
                error(where, f"{field} должно быть полной ссылкой: {value!r}")

        check_talks(where, data, speakers)


def check_talks(where: str, event: dict, speakers: dict[str, dict]) -> None:
    slugs: dict[str, str] = {}
    for talk in event.get("talks") or []:
        if not isinstance(talk, dict):
            error(where, f"доклад должен быть словарём, а не {type(talk).__name__}")
            continue

        title = (talk.get("title") or "").strip()
        if not title:
            error(where, "у доклада нет title")
            continue

        slug = build.slugify_talk(title, talk.get("slug"))
        if not slug:
            error(where, f"из названия «{title}» не получается слаг — задайте slug вручную")
        elif slug in slugs:
            error(where, f"доклады «{slugs[slug]}» и «{title}» дают один URL /{slug}/")
        else:
            slugs[slug] = title

        names = talk.get("speakers") or []
        if not names:
            error(where, f"у доклада «{title}» нет спикеров")
        for name in names:
            if not isinstance(name, str) or not name.strip():
                error(where, f"пустое имя спикера у доклада «{title}»")
            elif name not in speakers:
                error(
                    where,
                    f"«{name}» (доклад «{title}») не совпадает ни с одним name "
                    f"в content/speakers/ — доклад не свяжется с профилем",
                )

        for tag in talk.get("tags") or []:
            if not isinstance(tag, str) or not tag.strip():
                error(where, f"пустой тег у доклада «{title}»")
            elif not build.slugify(build.normalize_tag(tag)):
                error(where, f"из тега {tag!r} не получается слаг (доклад «{title}»)")


class LinkCollector(HTMLParser):
    """Собирает внутренние ссылки страницы: href, src и srcset."""

    URL_ATTRS = {"href", "src"}

    def __init__(self):
        super().__init__()
        self.links: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if not value:
                continue
            if name in self.URL_ATTRS:
                self.links.add(value)
            elif name == "srcset":
                for candidate in value.split(","):
                    url = candidate.strip().split(" ")[0]
                    if url:
                        self.links.add(url)


def resolves(dist: Path, url: str) -> bool:
    path = dist / url.lstrip("/")
    return path.is_file() or (path / "index.html").is_file()


def check_links(dist: Path) -> None:
    if not dist.exists():
        warn("dist/", "нет сборки — проверка ссылок пропущена (сначала make build)")
        return

    for page in sorted(dist.rglob("*.html")):
        collector = LinkCollector()
        collector.feed(page.read_text(encoding="utf-8"))
        where = str(page.relative_to(dist))
        for link in sorted(collector.links):
            # Наружу, якоря, почта и протокол-относительные — не наша забота.
            if not link.startswith("/") or link.startswith("//"):
                continue
            target = re.split(r"[?#]", link, maxsplit=1)[0]
            if target and not resolves(dist, target):
                error(f"dist/{where}", f"битая внутренняя ссылка: {link}")


def check_fonts(dist: Path) -> None:
    """Каждый url() из fonts.css лежит в сборке.

    fonts.css собирает scripts/fetch_fonts.py, и если у Google поменяется
    набор подмножеств, CSS поедет вперёд файлов. Ссылка на пропавший woff2
    видна только в консоли браузера — страница молча съезжает на фолбэк.
    """
    css = dist / "static" / "css" / "fonts.css"
    if not css.is_file():
        error("dist/static/css/fonts.css", "не собрался (нужен make fonts)")
        return

    urls = re.findall(r"url\(['\"]?([^'\")]+)['\"]?\)", css.read_text(encoding="utf-8"))
    if not urls:
        error("dist/static/css/fonts.css", "нет ни одного @font-face с url()")
        return

    for url in sorted(set(urls)):
        if url.startswith(("http://", "https://", "//")):
            error("dist/static/css/fonts.css",
                  f"шрифт грузится со стороны, а должен лежать у нас: {url}")
        elif not (css.parent / url).resolve().is_file():
            error("dist/static/css/fonts.css", f"нет файла шрифта: {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-links", action="store_true",
                        help="Не проверять ссылки в собранном dist/")
    parser.add_argument("--dist", type=Path, default=DIST_DIR,
                        help="Где лежит сборка (по умолчанию dist/)")
    args = parser.parse_args()

    speakers = check_speakers()
    check_events(speakers)
    if not args.no_links:
        check_links(args.dist)
        check_fonts(args.dist)

    for line in warnings:
        print(line)
    for line in errors:
        print(line, file=sys.stderr)

    print(
        f"\nПроверено: {len(list(EVENTS_DIR.glob('*.md')))} событий, "
        f"{len(speakers)} спикеров. "
        f"Ошибок: {len(errors)}, замечаний: {len(warnings)}."
    )
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
