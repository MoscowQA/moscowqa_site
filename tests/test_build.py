"""Тесты хрупких мест генератора: слаги, Timepad, календарь, теги, фото.

Это чистые функции build.py — то, что ломается тихо: доклад уезжает на другой
URL, виджет регистрации не появляется, .ics не открывается в календаре.
Запуск: `make test` или `python3 -m pytest`.
"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build  # noqa: E402


# --- Слаги ----------------------------------------------------------------

class TestSlugify:
    def test_transliterates_russian(self):
        assert build.slugify("Архитектура тестов") == "arhitektura-testov"

    def test_yo_and_soft_sign(self):
        # ё передаётся как "yo", мягкий знак выбрасывается.
        assert build.slugify("Чёрный митап") == "chyornyy-mitap"
        assert build.slugify("Стиль") == "stil"

    def test_collapses_separators(self):
        assert build.slugify("Тесты  —  и   код") == "testy-i-kod"

    def test_strips_edge_dashes_and_punctuation(self):
        assert build.slugify("«Помогите, flaky!»") == "pomogite-flaky"

    def test_keeps_latin_and_digits(self):
        assert build.slugify("Allure Report 3") == "allure-report-3"

    def test_limits_length(self):
        assert len(build.slugify("тест " * 50)) <= 80

    def test_manual_slug_wins(self):
        assert build.slugify_talk("Любое название", "ruchnoy-slug") == "ruchnoy-slug"

    def test_falls_back_to_title(self):
        assert build.slugify_talk("Lead time") == "lead-time"


# --- Timepad --------------------------------------------------------------

class TestTimepadEventId:
    def test_from_registration_link(self):
        event = {"registration_link": "https://moscowqa.timepad.ru/event/4204473/"}
        assert build.parse_timepad_event_id(event) == "4204473"

    def test_explicit_id_wins(self):
        event = {
            "timepad_event_id": "111",
            "registration_link": "https://moscowqa.timepad.ru/event/222/",
        }
        assert build.parse_timepad_event_id(event) == "111"

    def test_numeric_explicit_id_becomes_string(self):
        assert build.parse_timepad_event_id({"timepad_event_id": 4046132}) == "4046132"

    def test_partner_landing_page_has_no_id(self):
        event = {"registration_link": "https://mir-platform.ru/qameetup"}
        assert build.parse_timepad_event_id(event) == ""

    def test_no_link_at_all(self):
        assert build.parse_timepad_event_id({"registration_link": ""}) == ""

    def test_url_without_trailing_slash(self):
        event = {"registration_link": "http://timepad.ru/event/3973443"}
        assert build.parse_timepad_event_id(event) == "3973443"

    def test_lookalike_domain_is_not_timepad(self):
        event = {"registration_link": "https://nottimepad.ru/event/123/"}
        assert build.parse_timepad_event_id(event) == ""


class TestTimepadMode:
    def test_without_id_always_off(self):
        assert build.resolve_timepad_mode({"timepad_widget": "inline"}, "popup") == "off"

    def test_default_when_not_specified(self):
        assert build.resolve_timepad_mode({"timepad_event_id": "1"}, "popup") == "popup"

    def test_empty_value_falls_back_to_default(self):
        event = {"timepad_event_id": "1", "timepad_widget": ""}
        assert build.resolve_timepad_mode(event, "inline") == "inline"

    @pytest.mark.parametrize("raw,expected", [
        ("inline", "inline"), ("iframe", "inline"), ("form", "inline"),
        ("popup", "popup"), ("button", "popup"),
        ("off", "off"), ("none", "off"), ("no", "off"), ("false", "off"),
        ("POPUP", "popup"), ("  Inline  ", "inline"),
    ])
    def test_aliases(self, raw, expected):
        event = {"timepad_event_id": "1", "timepad_widget": raw}
        assert build.resolve_timepad_mode(event, "popup") == expected

    def test_yaml_booleans(self):
        # `timepad_widget: false` в YAML приходит настоящим False, не строкой.
        assert build.resolve_timepad_mode(
            {"timepad_event_id": "1", "timepad_widget": False}, "popup") == "off"
        assert build.resolve_timepad_mode(
            {"timepad_event_id": "1", "timepad_widget": True}, "inline") == "inline"

    def test_unknown_value_falls_back_to_default(self):
        event = {"timepad_event_id": "1", "timepad_widget": "модально"}
        assert build.resolve_timepad_mode(event, "popup") == "popup"


# --- Поиск по спикерам ----------------------------------------------------

class TestSearchText:
    def test_normalizes_case_yo_and_spaces(self):
        assert build.normalize_search_text("  Чёрный   Митап ") == "черный митап"

    def test_covers_name_company_and_slug(self):
        speaker = {"name": "Алексей Иванов", "company": "2ГИС", "slug": "aleksey-ivanov"}
        text = build.speaker_search_text(speaker, [])
        assert "алексей иванов" in text
        assert "2гис" in text
        # Слаг — латиница, по ней тоже ищут.
        assert "aleksey ivanov" in text

    def test_covers_talk_titles(self):
        speaker = {"name": "Алексей Иванов", "slug": "aleksey-ivanov"}
        text = build.speaker_search_text(
            speaker, [{"title": "Архитектура читаемых тестов на Playwright"}])
        assert "playwright" in text

    def test_covers_external_talks_and_events(self):
        speaker = {
            "name": "Константин Волков",
            "slug": "konstantin-volkov",
            "external_talks": [{"title": "Zero to Hero", "event": "Heisenbug"}],
        }
        text = build.speaker_search_text(speaker, [])
        assert "zero to hero" in text
        assert "heisenbug" in text

    def test_deduplicates_repeated_conferences(self):
        speaker = {
            "name": "Спикер",
            "slug": "speaker",
            "external_talks": [
                {"title": "Доклад один", "event": "Heisenbug"},
                {"title": "Доклад два", "event": "Heisenbug"},
            ],
        }
        assert build.speaker_search_text(speaker, []).count("heisenbug") == 1

    def test_skips_empty_fields(self):
        speaker = {"name": "Спикер", "company": "", "slug": "speaker"}
        assert "  " not in build.speaker_search_text(speaker, [])


# --- Календарь ------------------------------------------------------------

class TestEventDates:
    def test_iso_string(self):
        assert build.parse_event_date("2026-10-01") == date(2026, 10, 1)

    def test_yaml_date_object(self):
        assert build.parse_event_date(date(2026, 10, 1)) == date(2026, 10, 1)

    def test_garbage_is_none(self):
        assert build.parse_event_date("первое октября") is None
        assert build.parse_event_date(None) is None

    @pytest.mark.parametrize("raw", ["19:00", "9:05", "19.00", "  19:00  "])
    def test_time_formats(self, raw):
        assert build.parse_event_time(raw) is not None

    def test_absent_time(self):
        assert build.parse_event_time("") is None
        assert build.parse_event_time(None) is None

    def test_impossible_time(self):
        assert build.parse_event_time("25:00") is None
        assert build.parse_event_time("19:75") is None


class TestCalendarSpan:
    def test_without_time_is_all_day_with_exclusive_end(self):
        start, end, all_day = build.event_calendar_span({"date": "2026-10-01"})
        assert all_day is True
        assert (start, end) == (date(2026, 10, 1), date(2026, 10, 2))

    def test_with_time_converts_moscow_to_utc(self):
        start, end, all_day = build.event_calendar_span(
            {"date": "2026-10-01", "time": "18:00"})
        assert all_day is False
        assert start == datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        # Без end_time берётся три часа.
        assert end == datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)

    def test_explicit_end_time(self):
        start, end, _ = build.event_calendar_span(
            {"date": "2026-10-01", "time": "18:00", "end_time": "22:00"})
        assert (end - start).seconds == 4 * 3600

    def test_end_past_midnight_moves_to_next_day(self):
        start, end, _ = build.event_calendar_span(
            {"date": "2026-10-01", "time": "19:00", "end_time": "00:30"})
        assert end > start
        assert (end - start).seconds == 5 * 3600 + 1800

    def test_event_without_date(self):
        assert build.event_calendar_span({"title": "Без даты"}) is None


class TestIcs:
    def make(self, **extra):
        event = {"slug": "28-black", "title": "Moscow QA #28", "date": "2026-10-01"}
        event.update(extra)
        return build.build_ics(
            event, "https://moscowqa.ru/events/28-black/",
            now=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc))

    def unfold(self, ics):
        return ics.replace("\r\n ", "")

    def test_structure_and_crlf(self):
        ics = self.make()
        assert ics.startswith("BEGIN:VCALENDAR\r\n")
        assert ics.endswith("END:VCALENDAR\r\n")
        assert "\n" not in ics.replace("\r\n", "")

    def test_all_day_event(self):
        ics = self.unfold(self.make())
        assert "DTSTART;VALUE=DATE:20261001" in ics
        assert "DTEND;VALUE=DATE:20261002" in ics

    def test_timed_event_in_utc(self):
        ics = self.unfold(self.make(time="18:00"))
        assert "DTSTART:20261001T150000Z" in ics
        assert "DTEND:20261001T180000Z" in ics

    def test_stable_uid_and_stamp(self):
        ics = self.unfold(self.make())
        assert "UID:28-black@moscowqa.ru" in ics
        assert "DTSTAMP:20260918T120000Z" in ics

    def test_escapes_commas_and_semicolons(self):
        ics = self.unfold(self.make(address="Москва, Вятская; 27"))
        assert "LOCATION:Москва\\, Вятская\\; 27" in ics

    def test_newlines_in_description_are_escaped(self):
        ics = self.unfold(self.make(short_description="Первая\nвторая"))
        assert "Первая\\nвторая" in ics

    def test_lines_fit_75_octets(self):
        ics = self.make(
            title="Очень длинное название митапа, которое точно не влезает в одну строку",
            short_description="Описание " * 30,
        )
        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

    def test_folding_is_reversible(self):
        long_title = "Длинное название " * 5
        ics = self.make(title=long_title)
        assert f"SUMMARY:{long_title}" in self.unfold(ics)

    def test_event_without_date_has_no_file(self):
        assert build.build_ics({"slug": "x", "title": "X"}, "https://example.com") == ""


class TestGoogleCalendarUrl:
    def test_all_day_dates(self):
        url = build.google_calendar_url(
            {"title": "Moscow QA #28", "date": "2026-10-01"}, "https://moscowqa.ru/")
        assert "dates=20261001%2F20261002" in url

    def test_timed_dates_in_utc(self):
        url = build.google_calendar_url(
            {"title": "Moscow QA #28", "date": "2026-10-01", "time": "18:00"},
            "https://moscowqa.ru/")
        assert "dates=20261001T150000Z%2F20261001T180000Z" in url

    def test_location_included_when_known(self):
        url = build.google_calendar_url(
            {"title": "T", "date": "2026-10-01", "address": "Москва"}, "")
        assert "location=" in url

    def test_no_date_no_link(self):
        assert build.google_calendar_url({"title": "T"}, "") == ""


# --- Теги -----------------------------------------------------------------

class TestTags:
    def test_normalize_collapses_spaces(self):
        assert build.normalize_tag("  AI  и   LLM ") == "AI и LLM"

    def test_links_carry_name_and_slug(self):
        links = build.talk_tag_links({"tags": ["AI и LLM", "автоматизация"]})
        assert links == [
            {"name": "AI и LLM", "slug": "ai-i-llm"},
            {"name": "автоматизация", "slug": "avtomatizatsiya"},
        ]

    def test_skips_blanks_and_duplicates(self):
        links = build.talk_tag_links({"tags": ["карьера", "  ", "Карьера", ""]})
        assert [link["slug"] for link in links] == ["karera"]

    def test_talk_without_tags(self):
        assert build.talk_tag_links({}) == []

    def test_collect_groups_talks_and_sorts_by_count(self):
        events = [
            {"slug": "e1", "talks": [
                {"title": "A", "tag_links": build.talk_tag_links({"tags": ["автоматизация"]})},
                {"title": "B", "tag_links": build.talk_tag_links({"tags": ["автоматизация", "карьера"]})},
            ]},
            {"slug": "e2", "talks": [
                {"title": "C", "tag_links": build.talk_tag_links({"tags": ["автоматизация"]})},
            ]},
        ]
        tags = build.collect_tags(events)
        assert [(tag["slug"], len(tag["talks"])) for tag in tags] == [
            ("avtomatizatsiya", 3), ("karera", 1),
        ]

    def test_collect_keeps_event_reference(self):
        events = [{"slug": "e1", "talks": [
            {"title": "A", "tag_links": build.talk_tag_links({"tags": ["карьера"]})}]}]
        assert build.collect_tags(events)[0]["talks"][0]["event"]["slug"] == "e1"

    def test_no_tags_no_pages(self):
        assert build.collect_tags([{"slug": "e1", "talks": [{"title": "A"}]}]) == []


# --- Фото спикеров --------------------------------------------------------

class TestSpeakerPhotoVariants:
    @pytest.fixture
    def photos(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build, "ROOT", tmp_path)
        directory = tmp_path / "static" / "images" / "speakers"
        directory.mkdir(parents=True)
        return directory

    def write(self, directory, name, size):
        Image.new("RGB", size, "white").save(directory / name, "WEBP")

    def test_both_variants_give_srcset(self, photos):
        self.write(photos, "ivan.webp", (1080, 1080))
        self.write(photos, "ivan-540.webp", (540, 540))
        variants = build.speaker_photo_variants("/static/images/speakers/ivan.webp")
        assert variants["small"] == "/static/images/speakers/ivan-540.webp"
        assert variants["srcset"] == (
            "/static/images/speakers/ivan-540.webp 540w, "
            "/static/images/speakers/ivan.webp 1080w"
        )

    def test_width_descriptor_matches_real_photo(self, photos):
        self.write(photos, "ivan.webp", (800, 800))
        self.write(photos, "ivan-540.webp", (540, 540))
        variants = build.speaker_photo_variants("/static/images/speakers/ivan.webp")
        assert variants["srcset"].endswith("ivan.webp 800w")

    def test_without_small_variant_no_srcset(self, photos):
        self.write(photos, "ivan.webp", (1080, 1080))
        variants = build.speaker_photo_variants("/static/images/speakers/ivan.webp")
        assert variants["srcset"] == ""
        assert variants["small"] == "/static/images/speakers/ivan.webp"

    def test_remote_photo_is_left_alone(self, photos):
        remote = "https://example.com/photo.png"
        variants = build.speaker_photo_variants(remote)
        assert variants == {
            "src": remote, "small": remote, "srcset": "", "absolute": remote,
        }

    def test_absolute_url_for_og_image(self, photos):
        self.write(photos, "ivan.webp", (1080, 1080))
        variants = build.speaker_photo_variants("/static/images/speakers/ivan.webp")
        assert variants["absolute"] == (
            f"{build.SITE_URL}/static/images/speakers/ivan.webp")

    def test_speaker_without_photo(self, photos):
        assert build.speaker_photo_variants("")["src"] == ""
        assert build.speaker_photo_variants(None)["srcset"] == ""


# --- Разметка события -----------------------------------------------------

class TestPostalAddress:
    def test_splits_off_a_known_city(self):
        address = build.postal_address("Москва, Вятская улица, 27с42")
        assert address["addressLocality"] == "Москва"
        assert address["streetAddress"] == "Вятская улица, 27с42"
        assert address["addressCountry"] == "RU"

    def test_city_without_a_comma_after_it(self):
        # Адреса пишутся по-разному, делить по первой запятой нельзя.
        address = build.postal_address("Москва ул. Садовническая 9А")
        assert address["addressLocality"] == "Москва"
        assert address["streetAddress"] == "ул. Садовническая 9А"

    def test_second_known_city(self):
        address = build.postal_address("Санкт-Петербург, Пискарёвский проспект, 2к2")
        assert address["addressLocality"] == "Санкт-Петербург"

    def test_unknown_city_stays_whole(self):
        # Лучше весь адрес одной строкой, чем угаданный не тот город.
        address = build.postal_address("Казань, улица Баумана, 1")
        assert "addressLocality" not in address
        assert address["streetAddress"] == "Казань, улица Баумана, 1"

    def test_city_alone(self):
        assert build.postal_address("Москва")["streetAddress"] == "Москва"


class TestEventSchemaDates:
    def test_day_without_time_ends_the_same_day(self):
        """endDate в schema.org включительный, в отличие от iCalendar.

        Календарный расчёт отдаёт следующий день, и если отдать его как есть,
        поисковик решит, что митап идёт двое суток.
        """
        dates = build.event_schema_dates({"date": "2026-10-01"})
        assert dates == {"startDate": "2026-10-01", "endDate": "2026-10-01"}

    def test_time_is_written_in_moscow_time(self):
        dates = build.event_schema_dates({"date": "2026-10-01", "time": "18:00"})
        assert dates["startDate"] == "2026-10-01T18:00:00+03:00"
        # Без end_time берётся та же длительность, что и для календаря.
        assert dates["endDate"] == "2026-10-01T21:00:00+03:00"

    def test_explicit_end_time(self):
        dates = build.event_schema_dates(
            {"date": "2026-10-01", "time": "19:00", "end_time": "22:30"})
        assert dates["endDate"] == "2026-10-01T22:30:00+03:00"

    def test_event_without_date(self):
        assert build.event_schema_dates({"title": "Без даты"}) == {}


class TestEventOffers:
    URL = "https://moscowqa.ru/events/28-black/"

    def test_free_entry_is_still_an_offer(self):
        # Без offers карточка события в выдаче не собирается.
        offers = build.event_offers({}, self.URL)
        assert offers["price"] == "0"
        assert offers["priceCurrency"] == "RUB"
        assert offers["availability"] == "https://schema.org/InStock"

    def test_registration_link_wins(self):
        offers = build.event_offers(
            {"registration_link": "https://example.com/reg"}, self.URL)
        assert offers["url"] == "https://example.com/reg"

    def test_falls_back_to_timepad(self):
        offers = build.event_offers({"timepad_event_id": "4204473"}, self.URL)
        assert offers["url"] == "https://moscowqa.timepad.ru/event/4204473/"

    def test_falls_back_to_the_event_page(self):
        assert build.event_offers({"registration_link": ""}, self.URL)["url"] == self.URL


class TestEventPerformers:
    def test_order_of_the_programme_without_duplicates(self):
        event = {"talks": [
            {"speakers": ["Аня"]},
            {"speakers": ["Боря", "Аня"]},
        ]}
        assert [p["name"] for p in build.event_performers(event)] == ["Аня", "Боря"]

    def test_links_to_the_speaker_page_and_company(self):
        profiles = {"Аня": {"name": "Аня", "slug": "anya", "company": "Ozon Tech"}}
        person = build.event_performers({"talks": [{"speakers": ["Аня"]}]}, profiles)[0]
        assert person["url"] == f"{build.SITE_URL}/speakers/anya/"
        assert person["worksFor"] == {"@type": "Organization", "name": "Ozon Tech"}

    def test_speaker_without_a_profile_still_gets_named(self):
        person = build.event_performers({"talks": [{"speakers": ["Аня"]}]}, {})[0]
        assert person == {"@type": "Person", "name": "Аня"}

    def test_event_without_talks(self):
        assert build.event_performers({}) == []


class TestEventSchema:
    URL = "https://moscowqa.ru/events/28-black/"

    def make(self, **extra):
        event = {
            "slug": "28-black",
            "title": "Moscow QA #28",
            "date": "2026-10-01",
            "type": "Offline",
            "company": "Ozon Tech",
            "address": "Москва, Пресненская набережная, 10",
            "short_description": "Митап про тестирование",
            "talks": [{"speakers": ["Аня"]}],
        }
        event.update(extra)
        return event

    def schema(self, **extra):
        return build.event_schema(self.make(**extra), self.URL)

    def test_has_everything_google_asks_for(self):
        schema = self.schema(og_image="/static/og/events/28-black.png")
        for field in ("name", "startDate", "endDate", "location", "image",
                      "offers", "performer", "organizer", "eventStatus",
                      "eventAttendanceMode"):
            assert field in schema, field

    def test_is_serialisable_json(self):
        # Шаблон отдаёт это через `| tojson`; несериализуемое поле уронит сборку.
        assert json.loads(json.dumps(self.schema()))["@type"] == "Event"

    @pytest.mark.parametrize("event_type,mode", [
        ("Online", "OnlineEventAttendanceMode"),
        ("Offline", "OfflineEventAttendanceMode"),
        ("Offline + Online", "MixedEventAttendanceMode"),
        (None, "MixedEventAttendanceMode"),
    ])
    def test_attendance_mode(self, event_type, mode):
        assert self.schema(type=event_type)["eventAttendanceMode"].endswith(mode)

    def test_own_cover_wins_over_the_generated_one(self):
        schema = self.schema(cover="/static/images/events/28-black.jpg",
                             og_image="/static/og/events/28-black.png")
        assert schema["image"] == [f"{build.SITE_URL}/static/images/events/28-black.jpg"]

    def test_image_is_an_absolute_url(self):
        schema = self.schema(og_image="/static/og/events/28-black.png")
        assert schema["image"][0].startswith("https://")

    def test_event_without_a_picture_has_no_image_field(self):
        # Пустой image хуже отсутствующего: поисковик считает его ошибкой.
        assert "image" not in self.schema()

    def test_empty_description_is_omitted(self):
        assert "description" not in self.schema(short_description="")

    def test_free_entry_is_stated(self):
        assert self.schema()["isAccessibleForFree"] is True

    def test_event_without_address_has_no_location(self):
        assert "location" not in self.schema(address="")


class TestEventCoverVariants:
    COVER = "/static/images/events/28-black.jpg"

    @pytest.fixture
    def covers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build, "ROOT", tmp_path)
        directory = tmp_path / "static" / "images" / "events"
        directory.mkdir(parents=True)
        return directory

    def write(self, directory, name, size):
        Image.new("RGB", size, "white").save(directory / name)

    def test_webp_variants_become_sources(self, covers):
        self.write(covers, "28-black.jpg", (1377, 768))
        self.write(covers, "28-black.webp", (1200, 669))
        self.write(covers, "28-black-540.webp", (540, 301))
        self.write(covers, "28-black-768.webp", (768, 428))

        variants = build.event_cover_variants(self.COVER)
        assert [(s["url"].rsplit("/", 1)[1], s["width"]) for s in variants["sources"]] == [
            ("28-black-540.webp", 540),
            ("28-black-768.webp", 768),
            ("28-black.webp", 1200),
        ]

    def test_src_stays_the_original(self, covers):
        """og:image указывает на `cover`, а webp туда кладут не все соцсети."""
        self.write(covers, "28-black.jpg", (1377, 768))
        self.write(covers, "28-black.webp", (1200, 669))
        assert build.event_cover_variants(self.COVER)["src"] == self.COVER

    def test_size_of_the_original_is_reported(self, covers):
        # Размеры нужны шаблону, чтобы картинка не дёргала вёрстку.
        self.write(covers, "28-black.jpg", (1377, 768))
        variants = build.event_cover_variants(self.COVER)
        assert (variants["width"], variants["height"]) == (1377, 768)

    def test_widest_descriptor_matches_the_real_file(self, covers):
        self.write(covers, "28-black.jpg", (1377, 768))
        self.write(covers, "28-black.webp", (1024, 571))
        assert build.event_cover_variants(self.COVER)["sources"][-1]["width"] == 1024

    def test_without_webp_no_sources(self, covers):
        # Раньше обложки были одним JPEG — такая разметка должна остаться рабочей.
        self.write(covers, "28-black.jpg", (1377, 768))
        variants = build.event_cover_variants(self.COVER)
        assert variants["sources"] == []
        assert variants["src"] == self.COVER

    def test_missing_file(self, covers):
        variants = build.event_cover_variants(self.COVER)
        assert variants == {"src": self.COVER, "sources": [], "width": 0, "height": 0}

    def test_remote_and_empty_cover(self, covers):
        remote = "https://example.com/cover.jpg"
        assert build.event_cover_variants(remote)["sources"] == []
        assert build.event_cover_variants("")["src"] == ""
        assert build.event_cover_variants(None)["sources"] == []
