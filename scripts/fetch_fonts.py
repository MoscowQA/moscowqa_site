#!/usr/bin/env python3
"""Перенести Inter с Google Fonts к нам: скачать woff2 и собрать fonts.css.

Раньше `templates/base.html` тянул шрифт прямо с `fonts.googleapis.com`:
два preconnect, лишний запрос за CSS перед запросом за самим шрифтом и
зависимость от чужого CDN, который в России открывается не у всех. Теперь
шрифт лежит у нас:

    static/fonts/inter/inter-{подмножество}.woff2   сами файлы
    static/css/fonts.css                            @font-face на них

Скрипт берёт с Google ту же CSS, что запрашивал браузер, скачивает все
woff2 из неё и переписывает `src` на наши пути. `unicode-range` остаётся
как был, поэтому браузер по-прежнему качает только те подмножества, которые
реально встретились на странице: русской странице достаются cyrillic и
latin, остальное лежит мёртвым грузом и не скачивается.

Шрифт вариативный (одна ось `wght`), так что все начертания сайта —
400..800 — это один файл на подмножество, а не пять.

Запуск:
    python3 scripts/fetch_fonts.py            # обновить шрифт и CSS
    python3 scripts/fetch_fonts.py --dry-run  # показать, что изменится
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "static" / "fonts" / "inter"
CSS_FILE = ROOT / "static" / "css" / "fonts.css"

# Ровно то, что стояло в base.html до переезда: Inter начертаний 400–800.
# `wght@400..800` отдаёт вариативную версию — один файл на все пять.
SOURCE_URL = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@400..800&display=swap"
)
# Google отдаёт woff2 только «современным» браузерам; с curl/urllib по
# умолчанию в ответ приходит CSS со ссылками на ttf.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HEADER = """/* Inter, который раньше приезжал с fonts.googleapis.com.
 *
 * Файл собран `scripts/fetch_fonts.py` (`make fonts`) — руками не правим,
 * правки перетрёт следующий прогон. Зачем и как — в
 * static/fonts/inter/README.md.
 */
"""

# В CSS от Google каждому @font-face предшествует комментарий с названием
# подмножества: /* cyrillic */. По нему и называем файлы.
SUBSET_COMMENT = re.compile(r"/\*\s*([a-z0-9-]+)\s*\*/")
FONT_URL = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+)\)")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read()


def localize(css: str) -> tuple[str, list[tuple[str, str]]]:
    """Переписать ссылки на gstatic на наши пути.

    Возвращает готовую CSS и список (url, имя файла) — что надо скачать.
    """
    downloads: list[tuple[str, str]] = []
    subset = "unknown"
    seen: dict[str, str] = {}
    out: list[str] = []

    for line in css.splitlines():
        comment = SUBSET_COMMENT.fullmatch(line.strip())
        if comment:
            subset = comment.group(1)

        match = FONT_URL.search(line)
        if match:
            url = match.group(1)
            name = seen.get(url)
            if name is None:
                name = f"inter-{subset}.woff2"
                seen[url] = name
                downloads.append((url, name))
            line = line.replace(match.group(0), f"url('../fonts/inter/{name}')")

        out.append(line)

    return HEADER + "\n".join(out) + "\n", downloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="ничего не писать, только показать план")
    args = parser.parse_args()

    print(f"→ {SOURCE_URL}")
    try:
        css = fetch(SOURCE_URL).decode("utf-8")
    except OSError as exc:
        print(f"ОШИБКА: не скачалась CSS с Google Fonts: {exc}", file=sys.stderr)
        return 1

    local_css, downloads = localize(css)
    if not downloads:
        print("ОШИБКА: в ответе Google нет ссылок на woff2", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"{CSS_FILE.relative_to(ROOT)}: {len(local_css.splitlines())} строк")
        for _, name in downloads:
            print(f"  {(FONTS_DIR / name).relative_to(ROOT)}")
        return 0

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for url, name in downloads:
        try:
            data = fetch(url)
        except OSError as exc:
            print(f"ОШИБКА: не скачался {name}: {exc}", file=sys.stderr)
            return 1
        (FONTS_DIR / name).write_bytes(data)
        total += len(data)
        print(f"  {name:28} {len(data) / 1024:6.1f} КБ")

    CSS_FILE.write_text(local_css, encoding="utf-8")
    print(f"{len(downloads)} файлов, {total / 1024:.1f} КБ → "
          f"{FONTS_DIR.relative_to(ROOT)}/")
    print(f"CSS → {CSS_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
