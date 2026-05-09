# Parsers

## Первый запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r parsers/requirements.txt
```

---

## Добавить доклады с Heisenbug

### Когда вышел новый сезон

```bash
python parsers/collect_heisenbug.py --edition "2026 Spring"
python parsers/sync_heisenbug.py
python build.py
```

### Полная пересборка с нуля

```bash
python parsers/collect_heisenbug.py
python parsers/sync_heisenbug.py
python build.py
```

---

## Добавить доклады с SQA Days

```bash
python parsers/parse_sqadays.py
python build.py
```

---

## Посмотреть изменения перед применением

К любому скрипту добавьте `--dry-run`:

```bash
python parsers/sync_heisenbug.py --dry-run
python parsers/parse_sqadays.py --dry-run
```

---

## Добавить нового спикера MoscowQA

1. Создайте файл в `content/speakers/`
2. Запустите синхронизацию — доклады с Heisenbug подтянутся автоматически:

```bash
python parsers/sync_heisenbug.py
python build.py
```