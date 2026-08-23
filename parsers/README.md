# Parsers

## Первый запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r parsers/requirements.txt
```

---

## Heisenbug

Данные берутся с `heisenbug.ru/archive` — все сезоны автоматически.

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

## SQA Days

Данные берутся с `sqadays.com` по конкретным conference ID.  
Список всех известных ID хранится в `CONFERENCE_IDS` внутри `collect_sqadays.py`.

### Когда вышел новый SQA Days

Сайт не публикует список конференций — новый `eventId` нужно добавить вручную:

1. Найти `eventId` в URL страницы конференции: `sqadays.com/ru/talks/**144051**`
2. Добавить его первым в список `CONFERENCE_IDS` в файле `parsers/collect_sqadays.py`
3. Запустить:

```bash
python parsers/collect_sqadays.py --event <eventId>
python parsers/sync_sqadays.py
python build.py
```

### Полная пересборка с нуля

```bash
python parsers/collect_sqadays.py
python parsers/sync_sqadays.py
python build.py
```

---

## Посмотреть изменения перед применением

К любому sync-скрипту добавьте `--dry-run`:

```bash
python parsers/sync_heisenbug.py --dry-run
python parsers/sync_sqadays.py --dry-run
```

---

## Добавить нового спикера MoscowQA

1. Создайте файл в `content/speakers/`
2. Запустите синхронизацию — доклады подтянутся автоматически:

```bash
python parsers/sync_heisenbug.py
python parsers/sync_sqadays.py
python build.py
```