# Фотографии спикеров

## Формат именования

**Стандарт:** `{speaker-slug}.{ext}`

Где:
- `{speaker-slug}` - slug спикера из имени файла в `content/speakers/` (например, `aleksey-karavanov`)
- `{ext}` - расширение файла (`png`, `jpg`, `jpeg`)

## Примеры

- `aleksey-karavanov.png` → спикер из файла `content/speakers/aleksey-karavanov.md`
- `dmitriy-zubkov.png` → спикер из файла `content/speakers/dmitriy-zubkov.md`
- `aleksandr-yurkov.png` → спикер из файла `content/speakers/aleksandr-yurkov.md`

## Использование в YAML

```yaml
---
name: "Алексей Караванов"
company: "YADRO"
photo: "/static/images/speakers/aleksey-karavanov.png"
---
```

## Правила

1. **Только lowercase** - все буквы в нижнем регистре
2. **Дефисы вместо пробелов** - используйте `-` для разделения слов
3. **Транслитерация** - кириллица транслитерируется (а→a, ё→yo, и т.д.)
4. **Соответствие slug'у** - имя файла должно совпадать с slug'ом спикера

## Соответствие файлов

| Старое имя | Новое имя | Slug спикера |
|------------|-----------|--------------|
| karavanov.png | aleksey-karavanov.png | aleksey-karavanov |
| zubkov.png | dmitriy-zubkov.png | dmitriy-zubkov |
| delendik.png | yuriy-delendik.png | yuriy-delendik |
| Yurkov.png | aleksandr-yurkov.png | aleksandr-yurkov |
| Zubashev.png | ivan-zubashev.png | ivan-zubashev |

## Добавление новой фотографии

1. Узнайте slug спикера (имя файла в `content/speakers/` без расширения)
2. Переименуйте фото в формат `{speaker-slug}.{ext}`
3. Положите файл в `static/images/speakers/`
4. Обновите поле `photo` в YAML спикера:
   ```yaml
   photo: "/static/images/speakers/{speaker-slug}.png"
   ```
5. Пересоберите сайт: `python build.py`
