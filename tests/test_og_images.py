"""Тесты обложек для ссылок в соцсетях.

Обложку никто не проверяет глазами на каждом событии — её видно только в
превью ссылки, уже после деплоя. Поэтому здесь проверяется то, что ломается
тихо: съехавшая раскладка, потерянные спикеры, чужая компания у имени и
событие со своим `cover`, которому генерация не нужна.
Запуск: `make test` или `python3 -m pytest`.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import og_images  # noqa: E402


def make_event(**overrides) -> dict:
    event = {
        "slug": "30-example",
        "title": "Moscow QA #30 x Пример",
        "number": 30,
        "date": "2026-11-12",
        "company": "Пример",
        "address": "Москва, Примерная улица, 1",
        "type": "Offline + Online",
        "talks": [
            {"title": "Доклад", "speakers": ["Иван Иванов"], "company": "Роль"},
        ],
    }
    event.update(overrides)
    return event


def talks_for(*names) -> list[dict]:
    return [{"title": f"Доклад {i}", "speakers": [n]} for i, n in enumerate(names, 1)]


# --- Дата ------------------------------------------------------------------

class TestFormatDate:
    def test_iso_string(self):
        assert og_images.format_date("2026-09-05") == "5 сентября 2026"

    def test_date_object(self):
        assert og_images.format_date(date(2024, 3, 14)) == "14 марта 2024"

    def test_all_months_are_genitive(self):
        # Родительный падеж: «5 мая», а не «5 май».
        assert og_images.format_date("2026-05-01") == "1 мая 2026"
        assert og_images.format_date("2026-12-31") == "31 декабря 2026"

    def test_garbage_passes_through(self):
        # Сборка из-за кривой даты падать не должна — что дали, то и покажем.
        assert og_images.format_date("когда-нибудь") == "когда-нибудь"
        assert og_images.format_date(None) == ""


# --- Спикеры ---------------------------------------------------------------

class TestEventSpeakers:
    def test_collects_in_order_without_duplicates(self):
        event = make_event(talks=[
            {"title": "1", "speakers": ["Аня"]},
            {"title": "2", "speakers": ["Боря", "Аня"]},
        ])
        assert og_images.event_speakers(event) == [("Аня", ""), ("Боря", "")]

    def test_company_comes_from_speaker_profile(self):
        # В talks[].company нередко стоит должность — на карточке нужна компания.
        event = make_event(talks=[
            {"title": "1", "speakers": ["Иван Иванов"], "company": "Head of QA"},
        ])
        profiles = {"Иван Иванов": {"name": "Иван Иванов", "company": "Ozon Tech"}}
        assert og_images.event_speakers(event, profiles) == [("Иван Иванов", "Ozon Tech")]

    def test_falls_back_to_talk_company(self):
        event = make_event(talks=[
            {"title": "1", "speakers": ["Иван Иванов"], "company": "Ozon Tech"},
        ])
        assert og_images.event_speakers(event, {}) == [("Иван Иванов", "Ozon Tech")]

    def test_event_without_talks(self):
        assert og_images.event_speakers(make_event(talks=[])) == []
        assert og_images.event_speakers({}) == []


# --- Раскладка -------------------------------------------------------------

class TestRenderEventCard:
    def test_canvas_size_is_the_og_standard(self):
        card = og_images.render_event_card(make_event())
        assert card.size == (og_images.WIDTH, og_images.HEIGHT)

    @pytest.mark.parametrize("names", [
        [],
        ["Аня"],
        ["Аня", "Боря", "Вера"],
        ["Аня", "Боря", "Вера", "Гена"],
        ["Аня", "Боря", "Вера", "Гена", "Дима", "Егор", "Жанна"],
    ])
    def test_nothing_is_drawn_over_the_footer(self, names):
        """Состав любой длины не наезжает на подвал.

        Между последней строкой спикеров и «moscowqa.ru» должна остаться
        пустая полоса — иначе текст сливается с подвалом.
        """
        card = og_images.render_event_card(make_event(talks=talks_for(*names)))
        assert self.brightest(card, self.GAP_TOP, 14) < 90

    def test_the_footer_itself_is_drawn(self):
        """Страховка от «теста, который всегда зелёный».

        Проверка выше ловит наезд на подвал по яркости пикселей. Если бы
        текст перестал рисоваться вовсе, она молчала бы — поэтому здесь
        отдельно проверяется, что подпись внизу видна.
        """
        card = og_images.render_event_card(make_event())
        assert self.brightest(card, og_images.HEIGHT - 52 - 22, 30) > 90

    GAP_TOP = og_images.HEIGHT - 52 - 22 - 18

    @staticmethod
    def brightest(card, top: int, height: int) -> int:
        """Самый светлый пиксель в горизонтальной полосе карточки."""
        strip = card.crop((og_images.PAD, top, og_images.WIDTH - og_images.PAD,
                           top + height))
        return strip.convert("L").getextrema()[1]

    def test_long_title_still_fits(self):
        card = og_images.render_event_card(make_event(
            title="Очень длинное название митапа, которое никак не помещается "
                  "в одну строку и даже в две помещается с трудом, честное слово",
            talks=talks_for("Аня", "Боря", "Вера", "Гена"),
        ))
        assert card.size == (og_images.WIDTH, og_images.HEIGHT)

    def test_event_without_number_renders(self):
        # Ненумерованные активности (шорт-треки) идут без плашки «МИТАП #N».
        event = make_event(title="Шорт-трек на конференции")
        event.pop("number")
        assert og_images.render_event_card(event).size[0] == og_images.WIDTH

    def test_missing_fields_do_not_break_the_card(self):
        card = og_images.render_event_card({"slug": "x", "title": "Без всего"})
        assert card.size == (og_images.WIDTH, og_images.HEIGHT)


class TestCardAlt:
    def test_names_the_event_date_and_host(self):
        alt = og_images.card_alt(make_event())
        assert alt == "Moscow QA #30 x Пример, 12 ноября 2026, Пример"

    def test_survives_an_empty_event(self):
        assert og_images.card_alt({}) == "Митап Moscow QA"


# --- Связка со сборкой -----------------------------------------------------

class TestGenerateEventCards:
    def test_writes_a_card_and_sets_og_image(self, tmp_path):
        events = [make_event()]
        assert og_images.generate_event_cards(events, tmp_path) == 1

        written = tmp_path / og_images.OG_DIR / "30-example.png"
        assert written.exists()
        assert events[0]["og_image"] == "/static/og/events/30-example.png"
        assert events[0]["og_image_alt"]

    def test_event_with_its_own_cover_is_skipped(self, tmp_path):
        # Нарисованная руками обложка лучше сгенерированной — не трогаем её.
        events = [make_event(cover="/static/images/events/30.jpg")]
        assert og_images.generate_event_cards(events, tmp_path) == 0
        assert "og_image" not in events[0]
        assert not list((tmp_path / og_images.OG_DIR).glob("*.png"))

    def test_path_matches_what_the_site_serves(self, tmp_path):
        """`og_image` — это путь внутри dist/, иначе og:image ведёт в 404."""
        events = [make_event()]
        og_images.generate_event_cards(events, tmp_path)
        assert (tmp_path / events[0]["og_image"].lstrip("/")).exists()
