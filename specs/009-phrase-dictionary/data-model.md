# Data Model: Словарь фраз

Одна миграция Alembic создаёт пять таблиц. Таблицы слов (`words`, `progress`,
`review_log`, `labels`, `word_labels`, `settings`) не меняются. Все внешние ключи
фраз указывают только на таблицы фраз — связей со словами нет.

## phrases — фраза

| Колонка | Тип | Ограничения | Смысл |
|---|---|---|---|
| `id` | Integer | PK | Порядок добавления новых фраз |
| `text` | String(200) | NOT NULL | Английская фраза как введена, обрезана по краям |
| `text_key` | String(200) | NOT NULL, index | `lower` + схлопнутые пробелы — ключ дубля |
| `translation` | Text | NOT NULL | Русский перевод |
| `example` | Text | NULL | Пример |
| `example_translation` | Text | NULL | Перевод примера |
| `created_at` | DateTime (naive UTC) | NOT NULL | `clock.utcnow()` |
| `priority` | Boolean | NOT NULL, default false | «Учить первой»; только без прогресса |

- Уникальный индекс `ux_phrases_text_key_translation (text_key, translation)` — как
  у слов; проверка дубля в роутере сравнивает значения перевода через
  `translation_variants`, индекс — последняя линия обороны.
- Синонимы для общего кода и схем: `word → text`, `word_key → text_key`.
- Связи: `progress` (one-to-one, `cascade="all, delete-orphan"`, `selectin`),
  `labels` (many-to-many через `phrase_label_links`, порядок по `name_key` с «ё» = «е»).

**Валидация** (Pydantic, общая с `WordCreate`/`WordUpdate`, кроме длины): `word`
1–200 символов после обрезки, `translation` непустой, `labels` — названия до 50
символов.

## phrase_progress — прогресс фразы

Копия `progress` по смыслу и колонкам, ключ — `phrase_id`.

| Колонка | Тип | Ограничения |
|---|---|---|
| `phrase_id` | Integer | PK, FK → `phrases.id` ON DELETE CASCADE |
| `status` | String(16) | NOT NULL, `learning` / `review` / `known` / `suspended` |
| `step`, `repetitions`, `lapses` | Integer | NOT NULL |
| `ease`, `interval_days` | Float | NOT NULL |
| `due_at`, `started_at`, `updated_at` | DateTime | NOT NULL |

- Индекс `ix_phrase_progress_status_due_at (status, due_at)` — отбор к повторению.
- Синоним `word_id → phrase_id`.
- Строки нет — фраза «Новая».

**Переходы статуса** — те же, что у слов, через те же чистые функции `srs.py`:

```
(нет строки) --«Изучить»--> learning --finish(learn)--> review
(нет строки) --«Уже знаю»--> known
review --finish(review), ошибка--> learning (lapses+1, срок сегодня)
review --finish(review), без ошибок--> review (интервал растёт)
любой --ручная смена--> force_status(...)       # журнал не пишется
любой --«Новое»/удаление--> (нет строки)         # с подтверждением в UI
```

## phrase_review_log — журнал ответов по фразам

Копия `review_log` по колонкам: `id`, `phrase_id` (FK → `phrases.id` ON DELETE
CASCADE, index), `exercise`, `correct`, `answer`, `used_hint`, `attempt`,
`quality`, `duration_ms`, `status_before`, `status_after`, `ease_after`,
`interval_after`, `created_at` (index), `session_id` (String(36), index).
Синоним `word_id → phrase_id`.

Пишется знакомством (`intro`) и каждым ответом в занятии с фразами. Ручные
действия (правка, статус, отметка, метки) сюда не пишут.

## phrase_labels — метка фраз

Те же колонки, что `labels`: `id`, `name` String(50), `name_key` String(50)
(уникальный индекс `ux_phrase_labels_name_key`), `description` String(200) NULL,
`created_at`. Метка фраз и метка слов с одинаковым названием — разные строки
разных таблиц.

## phrase_label_links — связка «фраза — метка»

| Колонка | Ограничения |
|---|---|
| `phrase_id` | PK, FK → `phrases.id` ON DELETE CASCADE |
| `label_id` | PK, FK → `phrase_labels.id` ON DELETE CASCADE |

Индекс `ix_phrase_label_links_label_id` — для фильтра и счётчика фраз у метки.

## Deck — описание колоды (не таблица)

Замороженный dataclass в `app/decks.py`, по которому общий код находит свои таблицы:

| Поле | `WORDS` | `PHRASES` |
|---|---|---|
| `item` | `Word` | `Phrase` |
| `progress` | `Progress` | `PhraseProgress` |
| `log` | `ReviewLog` | `PhraseReviewLog` |
| `label` | `Label` | `PhraseLabel` |
| `links` | `word_labels` | `phrase_label_links` |
| `new_per_session` | `settings.new_words_per_session` | `settings.new_phrases_per_session` |
| `review_per_session` | `settings.review_words_per_session` | `settings.review_phrases_per_session` |
| `daily_new_limit` | `settings.daily_new_limit` | `settings.daily_new_phrases_limit` |
| `uses_order_setting` | да (`new_words_order`) | нет — всегда по возрастанию `id` |
| `drop_apostrophes` | нет | да |
| `not_found` | «Слово не найдено» | «Фраза не найдена» |
