# Шрифт для og-обложек

`Inter.ttf` — вариативный Inter (оси `opsz` и `wght`), тот же шрифт, которым
набран сайт. Используется только на сборке, в `og_images.py`: Pillow рисует
им текст на обложках событий. В `dist/` не копируется — в отличие от
`static/`, эта папка не попадает на сайт.

- Источник: <https://github.com/google/fonts/tree/main/ofl/inter>
- Лицензия: SIL Open Font License 1.1, полный текст — в `OFL.txt`

Обновить:

```bash
curl -L -o assets/fonts/Inter.ttf \
  'https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf'
curl -L -o assets/fonts/OFL.txt \
  'https://raw.githubusercontent.com/google/fonts/main/ofl/inter/OFL.txt'
```
