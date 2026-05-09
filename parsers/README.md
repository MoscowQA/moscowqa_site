# Parsers

Scripts to collect external speaker talks from conference sites and update speaker `.md` files.

## Setup

```bash
cd parsers
pip install -r requirements.txt
```

## Heisenbug

Parses all editions from `heisenbug.ru/archive/`.

```bash
# Dry run — see matches without writing anything
python parse_heisenbug.py --dry-run

# Actually write to speaker files
python parse_heisenbug.py

# Also fetch individual talk pages (more accurate title/date/slides, ~3× slower)
python parse_heisenbug.py --detail
```

## SQA Days

Parses the talks listing from `sqadays.com/ru/talks` (paginated).

```bash
# Dry run
python parse_sqadays.py --dry-run

# All pages
python parse_sqadays.py

# Specific page range (faster for testing)
python parse_sqadays.py --pages 1-10

# Fetch individual talk pages for speaker names + slides
python parse_sqadays.py --detail
```

## How it works

1. Loads speaker names from `content/speakers/*.md`
2. Scrapes conference talk listings
3. Matches speaker names (exact + partial)
4. Appends new entries to `external_talks:` in the speaker files
5. Skips talks already recorded (by URL)

## Tips

- Run with `--dry-run` first to see what would be added
- Speaker name matching is approximate: "Алексей Иванов" matches "Алексей Иванов (МoscowQA)" etc.
- After running, review the changes with `git diff content/speakers/` before committing
