# API Contract: Импорт слов из CSV

Один новый маршрут, остальные не меняются. Для фраз маршрута нет (FR-020).

## POST /api/words/import

Импортирует CSV-файл в словарь слов одной транзакцией.

### Запрос

```
POST /api/words/import
Content-Type: text/csv

<байты файла как есть>
```

Тело — содержимое файла без обёртки: ни JSON, ни multipart (research R1).
Кодировка UTF-8, BOM допускается. Разделитель «,» или «;» определяется по
заголовку (research R3). Первая строка — заголовок. Названия колонок перечислены
в research R4.

Пример тела:

```csv
слово;перевод;пример;перевод примера;метка
saucepan;кастрюля;Put the saucepan on the stove.;Поставь кастрюлю на плиту.;Кухня
whisk;венчик;;;"Кухня; Посуда"
"roll out";"внедрить";;;
```

Несколько меток в одной ячейке разделяются «;». Если «;» — разделитель колонок,
ячейку берут в кавычки, как у `whisk`. Без кавычек `Кухня; Посуда` распадётся на две
колонки, и вторая метка потеряется. Подсказка в интерфейсе это показывает.

### 200 OK — `ImportReport`

Пример ответа для другого файла, из пяти строк:

```json
{
  "rows": 5,
  "created": 3,
  "merged": 1,
  "unchanged": 0,
  "skipped": 1,
  "skipped_rows": [{ "line": 4, "reason": "нет перевода" }],
  "labels_created": ["Кухня", "Посуда"],
  "ignored_columns": ["источник"]
}
```

Поля описаны в [data-model.md](../data-model.md#importreport-ответ-api).
`skipped_rows` содержит не больше `import_skipped_report_max` (200) элементов,
`skipped` — полное число. Файл с заголовком и без строк данных даёт 200 и нули.

### Ошибки

`detail` — строка на русском. Словарь при любой ошибке не меняется.

| Код | Когда | Пример `detail` |
|---|---|---|
| 413 | тело больше `import_max_bytes` | «Файл больше 5 МБ» |
| 422 | пустое тело / нет заголовка | «Файл пустой» |
| 422 | байты не декодируются как UTF-8 | «Файл не в UTF-8 — сохраните его как «CSV UTF-8»» |
| 422 | нет колонки слова или перевода | «Нет обязательных колонок: перевод. Ожидаются: слово, перевод, пример, перевод примера, метка» |
| 422 | одно поле названо дважды | «Колонка «перевод» встречается дважды» |

### Побочные эффекты

- Создаёт записи `words` и метки `labels`, добавляет связи `word_labels`,
  дописывает `translation` и заполняет пустые `example`/`example_translation`
  существующих записей.
- Не трогает `progress`, `priority`, `review_log`, `phrase_review_log`,
  `group_review_log`, `phrases`, `phrase_labels`.
- Повторный запрос с тем же телом возвращает `created = merged = 0`,
  `labels_created = []`.

## Фронтенд (`frontend/src/api/types.ts`, `client.ts`)

```ts
export interface ImportSkippedRow {
  line: number
  reason: string
}

export interface ImportReport {
  rows: number
  created: number
  merged: number
  unchanged: number
  skipped: number
  skipped_rows: ImportSkippedRow[]
  labels_created: string[]
  ignored_columns: string[]
}
```

`api.importWords(file: File): Promise<ImportReport>` отправляет `file` телом
запроса с заголовком `Content-Type: text/csv`, переопределяя JSON-заголовок
`request()`. Ошибки приходят как `ApiError` с `detail`.

Перед отправкой панель импорта сравнивает `file.size` с тем же пределом в 5 МБ
и при превышении сообщает о нём без запроса (research R9). Решает сервер:
браузерная проверка лишь избавляет от бессмысленной отправки.

## README

В раздел «API» добавляется строка:

```
POST   /api/words/import              тело — CSV-файл; добавить и дополнить слова
                                       с метками (413, 422)
```
