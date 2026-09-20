#!/usr/bin/env python3
"""Обложки событий для ссылок в соцсетях (og:image).

Обложку события можно нарисовать руками и положить в `content/events/*.md`
полем `cover` — так сделано для активностей на чужих конференциях. Для
обычных митапов рисовать нечего: всё, что нужно на карточке, уже есть в
front matter, поэтому сборка собирает её сама.

На карточке 1200×630 — номер митапа и формат, дата, название, площадка с
компанией-хостом и спикеры. Из этого Telegram, VK и поисковики делают
превью ссылки: вместо строчки текста — карточка с программой митапа.

Модуль подключается из `build.py` (см. `generate_event_cards`), а запущенный
напрямую — рисует те же карточки в отдельную папку, чтобы посмотреть, что
получится, не пересобирая сайт:

    python3 og_images.py --out /tmp/og            # все события
    python3 og_images.py --out /tmp/og 28-black   # только это

Шрифт — вариативный Inter из `assets/fonts/` (та же гарнитура, что на
сайте). Эта папка, в отличие от `static/`, на сайт не копируется: шрифт
нужен только на сборке.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_PATH = ROOT / "assets" / "fonts" / "Inter.ttf"
LOGO_PATH = ROOT / "static" / "images" / "logo.png"

# Путь обложек внутри сайта. Совпадает с тем, что build.py пишет в
# dist/ и подставляет в og:image.
OG_DIR = "static/og/events"

WIDTH = 1200
HEIGHT = 630
PAD = 64
# Больше имён в превью Telegram уже не прочитать — остальные уходят в «и ещё N».
MAX_SPEAKER_LINES = 4

# Цвета — те же, что в static/css/styles.css.
BG = (7, 7, 11)
PINK = (219, 39, 119)
PURPLE = (124, 58, 237)
WHITE = (255, 255, 255)
GRAY = (156, 163, 175)
DIM = (107, 114, 128)
DIVIDER = (32, 32, 41)

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


# --- Текст -----------------------------------------------------------------


@lru_cache(maxsize=None)
def _font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Inter нужного кегля и насыщенности.

    Ось `opsz` ведём за кеглем: Inter сам подтягивает межбуквенное
    расстояние и пропорции под размер, поэтому крупный заголовок не
    выглядит разреженным, а мелкая подпись — слипшейся.
    """
    if not FONT_PATH.exists():
        # Иначе сборка падает с невнятным «cannot open resource».
        raise FileNotFoundError(
            f"Не найден шрифт для og-обложек: {FONT_PATH}. "
            "Как его вернуть — в assets/fonts/README.md"
        )
    font = ImageFont.truetype(str(FONT_PATH), size)
    try:
        font.set_variation_by_axes([min(32, max(14, size)), weight])
    except Exception:  # noqa: BLE001 — сборка стоит дороже начертания
        # Pillow без поддержки вариативных осей: текст будет обычным
        # Regular, но карточка всё равно соберётся.
        pass
    return font


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def truncate(draw, text: str, font, max_width: float) -> str:
    """Строка, укороченная до ширины по последнему целому слову."""
    if text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    words = text.split()
    out = ""
    for word in words:
        candidate = f"{out} {word}".strip()
        if text_width(draw, candidate + ellipsis, font) > max_width:
            break
        out = candidate
    if not out:
        # Одно слово шире строки — режем по символам.
        out = text
        while out and text_width(draw, out + ellipsis, font) > max_width:
            out = out[:-1]
    return out + ellipsis


def wrap(draw, text: str, font, max_width: float, max_lines: int) -> list[str]:
    """Текст, разложенный по строкам; лишнее уходит в многоточие."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)

    if not lines:
        return []

    # Не поместившийся хвост сворачиваем в многоточие на последней строке.
    consumed = len(" ".join(lines).split())
    if consumed < len(text.split()):
        lines[-1] = truncate(draw, lines[-1] + " …", font, max_width)
    return lines


def format_date(value) -> str:
    """`2026-09-05` → `5 сентября 2026`. Непонятную дату отдаём как есть."""
    if isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            return str(value or "").strip()
    return f"{parsed.day} {MONTHS_GENITIVE[parsed.month - 1]} {parsed.year}"


def event_speakers(event: dict, speaker_by_name: dict | None = None) -> list[tuple[str, str]]:
    """Спикеры события парами «имя, компания», без повторов.

    Компанию берём из профиля спикера, а не из доклада: в `talks[].company`
    иногда стоит должность («Head of QA»), а на карточке нужна компания.
    """
    speaker_by_name = speaker_by_name or {}
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for talk in event.get("talks") or []:
        for name in talk.get("speakers") or []:
            name = str(name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            profile = speaker_by_name.get(name) or {}
            company = (profile.get("company") or talk.get("company") or "").strip()
            result.append((name, company))
    return result


# --- Фон -------------------------------------------------------------------


def _radial(size: tuple[int, int], center: tuple[float, float], radius: float) -> Image.Image:
    """Маска круглого свечения, затухающего к краям.

    Считаем на маленькой сетке и растягиваем: на 1200×630 разница не видна,
    а попиксельный расчёт был бы на два порядка дороже.
    """
    small_w, small_h = 96, 50
    mask = Image.new("L", (small_w, small_h), 0)
    pixels = mask.load()
    cx = center[0] * small_w / size[0]
    cy = center[1] * small_h / size[1]
    rx = radius * small_w / size[0]
    ry = radius * small_h / size[1]
    for y in range(small_h):
        for x in range(small_w):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            d = (dx * dx + dy * dy) ** 0.5
            value = max(0.0, 1.0 - d)
            pixels[x, y] = int(255 * value * value)
    return mask.resize(size, Image.BICUBIC)


def _background() -> Image.Image:
    """Чёрный фон с двумя фирменными свечениями и градиентом внизу."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)

    for color, center, radius, strength in (
        (PINK, (WIDTH * 0.93, HEIGHT * 0.08), WIDTH * 0.62, 0.42),
        (PURPLE, (WIDTH * 0.04, HEIGHT * 1.02), WIDTH * 0.55, 0.30),
    ):
        glow = Image.new("RGB", (WIDTH, HEIGHT), color)
        mask = _radial((WIDTH, HEIGHT), center, radius)
        mask = mask.point(lambda v, s=strength: int(v * s))
        img.paste(glow, (0, 0), mask)

    # Полоса по нижнему краю: розовый → фиолетовый.
    strip_h = 8
    strip = Image.new("RGB", (WIDTH, 1))
    strip_px = strip.load()
    for x in range(WIDTH):
        t = x / (WIDTH - 1)
        strip_px[x, 0] = tuple(
            int(PINK[i] + (PURPLE[i] - PINK[i]) * t) for i in range(3)
        )
    img.paste(strip.resize((WIDTH, strip_h), Image.BICUBIC), (0, HEIGHT - strip_h))
    return img


def _pill(draw, xy: tuple[int, int], text: str, font, *, fill, text_color,
          outline=None) -> tuple[int, int]:
    """Скруглённая плашка с текстом. Возвращает её правый край и низ."""
    pad_x, pad_y = 20, 11
    w = text_width(draw, text, font)
    ascent, descent = font.getmetrics()
    h = ascent + descent
    x, y = xy
    box = (x, y, x + w + pad_x * 2, y + h + pad_y * 2)
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill,
                           outline=outline, width=2 if outline else 0)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=text_color)
    return int(box[2]), int(box[3])


# --- Карточка --------------------------------------------------------------


def render_event_card(event: dict, speaker_by_name: dict | None = None,
                      logo_path: Path | None = None) -> Image.Image:
    """Обложка одного события.

    Блоки укладываются сверху вниз, и каждый следующий знает, сколько
    места осталось: у длинного названия просто меньше строк под спикеров,
    а не наезд на подвал.
    """
    img = _background()
    draw = ImageDraw.Draw(img)
    content_w = WIDTH - PAD * 2

    # Шапка: логотип со словесным знаком слева, дата справа.
    logo_size = 64
    header_y = 52
    logo_file = logo_path if logo_path is not None else LOGO_PATH
    x = PAD
    if logo_file and Path(logo_file).exists():
        logo = Image.open(logo_file).convert("RGBA")
        logo.thumbnail((logo_size, logo_size), Image.LANCZOS)
        img.paste(logo, (x, header_y + (logo_size - logo.height) // 2), logo)
        x += logo.width + 18

    wordmark_font = _font(34, 700)
    ascent, descent = wordmark_font.getmetrics()
    draw.text((x, header_y + (logo_size - ascent - descent) // 2), "MoscowQA",
              font=wordmark_font, fill=WHITE)

    date_text = format_date(event.get("date"))
    if date_text:
        date_font = _font(27, 600)
        d_ascent, d_descent = date_font.getmetrics()
        draw.text(
            (WIDTH - PAD - text_width(draw, date_text, date_font),
             header_y + (logo_size - d_ascent - d_descent) // 2),
            date_text, font=date_font, fill=PINK,
        )

    y = header_y + logo_size + 30
    draw.line((PAD, y, WIDTH - PAD, y), fill=DIVIDER, width=2)
    y += 32

    # Плашки: номер митапа и формат.
    badge_font = _font(23, 700)
    badge_bottom = y
    badge_x = PAD
    if event.get("number"):
        badge_x, badge_bottom = _pill(
            draw, (badge_x, y), f"МИТАП #{event['number']}", badge_font,
            fill=PINK, text_color=WHITE,
        )
        badge_x += 12
    event_type = str(event.get("type") or "").strip()
    if event_type:
        _, badge_bottom = _pill(
            draw, (badge_x, y), event_type.upper(), _font(23, 600),
            fill=None, text_color=GRAY, outline=DIVIDER,
        )
    if badge_bottom > y:
        y = badge_bottom + 26

    # Название.
    title_font = _font(56, 800)
    title_leading = 68
    for line in wrap(draw, str(event.get("title") or ""), title_font, content_w, 3):
        draw.text((PAD, y), line, font=title_font, fill=WHITE)
        y += title_leading
    y += 6

    # Площадка: адрес и компания-хост.
    place = " · ".join(
        part for part in (
            str(event.get("address") or "").strip(),
            str(event.get("company") or "").strip(),
        ) if part
    )
    if place:
        place_font = _font(26, 500)
        draw.text((PAD, y), truncate(draw, place, place_font, content_w),
                  font=place_font, fill=GRAY)
        y += 42

    # Спикеры. Блок прижат к подвалу, но не выше того, где закончился
    # заголовок: у короткого названия карточка не зияет пустотой посередине,
    # у длинного — спикеры просто начинаются сразу под ним.
    footer_y = HEIGHT - 52 - 22
    speakers = event_speakers(event, speaker_by_name)
    flow_top = y + 10
    available = int(footer_y - 22 - flow_top)
    if speakers and available > 0:
        # Строку сжимаем ровно настолько, чтобы состав влез в оставшееся
        # место, но не мельче читаемого в превью Telegram. Что не влезло
        # даже так — сворачивается в «и ещё N».
        if len(speakers) <= 3:
            line_h = 46
        else:
            slots = min(len(speakers), MAX_SPEAKER_LINES)
            line_h = max(34, min(40, available // slots))
        name_size = 27 if line_h >= 44 else (24 if line_h >= 38 else 22)
        name_font = _font(name_size, 600)
        company_font = _font(name_size - 2, 400)

        fits = min(MAX_SPEAKER_LINES, available // line_h)
        if fits >= len(speakers):
            shown, rest = speakers, 0
        elif fits >= 2:
            # Последняя строка уходит под «и ещё N».
            shown, rest = speakers[:fits - 1], len(speakers) - (fits - 1)
        else:
            # Длинное название съело всю карточку: состав опускаем, чтобы
            # не налезть на подвал — заголовка и площадки достаточно.
            shown, rest = [], 0

        block_h = (len(shown) + (1 if rest else 0)) * line_h
        y = max(flow_top, footer_y - 22 - block_h)

        for name, company in shown:
            bar_top = y + (line_h - 22) // 2
            draw.rounded_rectangle((PAD, bar_top, PAD + 4, bar_top + 22),
                                   radius=2, fill=PINK)
            tx = PAD + 20
            ascent, descent = name_font.getmetrics()
            baseline = y + (line_h - ascent - descent) // 2
            draw.text((tx, baseline), name, font=name_font, fill=WHITE)
            if company:
                tx += text_width(draw, name, name_font) + 12
                draw.text((tx, baseline + 2),
                          truncate(draw, f"· {company}", company_font,
                                   WIDTH - PAD - tx),
                          font=company_font, fill=GRAY)
            y += line_h
        if rest:
            draw.text((PAD + 20, y + (line_h - name_size) // 2 - 4),
                      f"и ещё {rest} {_speakers_word(rest)}",
                      font=_font(name_size - 3, 600), fill=DIM)

    draw.text((PAD, footer_y), "moscowqa.ru", font=_font(24, 600), fill=DIM)
    return img


def _speakers_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "спикер"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "спикера"
    return "спикеров"


def card_alt(event: dict) -> str:
    """Подпись к обложке: то же, что на ней написано, только словами."""
    parts = [str(event.get("title") or "").strip() or "Митап Moscow QA"]
    date_text = format_date(event.get("date"))
    if date_text:
        parts.append(date_text)
    place = str(event.get("company") or event.get("address") or "").strip()
    if place:
        parts.append(place)
    return ", ".join(parts)


def generate_event_cards(events, output_dir: Path, speaker_by_name=None,
                         logo_path: Path | None = None) -> int:
    """Нарисовать обложки событий в `{output_dir}/static/og/events/`.

    Событию со своим `cover` обложка не нужна — нарисованная руками лучше
    сгенерированной. Остальным проставляются `og_image` и `og_image_alt`:
    путь и подпись, которые `templates/event.html` подставит в og:image.
    """
    target = Path(output_dir) / OG_DIR
    target.mkdir(parents=True, exist_ok=True)

    count = 0
    for event in events:
        if event.get("cover"):
            continue
        slug = event["slug"]
        card = render_event_card(event, speaker_by_name, logo_path)
        card.save(target / f"{slug}.png", optimize=True)
        event["og_image"] = f"/{OG_DIR}/{slug}.png"
        event["og_image_alt"] = card_alt(event)
        count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slugs", nargs="*", help="слаги событий; по умолчанию все")
    parser.add_argument("--out", default="og-preview", help="куда сложить картинки")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    import build  # noqa: PLC0415 — импорт здесь, чтобы модуль не тянул сборку

    events = build.load_events()
    speaker_by_name = {s["name"]: s for s in build.load_speakers()}
    if args.slugs:
        wanted = set(args.slugs)
        events = [e for e in events if e["slug"] in wanted]
        missing = wanted - {e["slug"] for e in events}
        if missing:
            print(f"Нет таких событий: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for event in events:
        path = out / f"{event['slug']}.png"
        render_event_card(event, speaker_by_name).save(path, optimize=True)
        print(f"{path} ({path.stat().st_size // 1024} КБ)")
    print(f"Готово: {len(events)} обложек в {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
