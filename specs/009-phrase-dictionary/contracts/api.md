# API Contract: фразы

Маршруты слов не меняются. Маршруты фраз повторяют их форму под своими префиксами и
отвечают теми же схемами (`backend/app/schemas.py`, `frontend/src/api/types.ts`).
В ответах для фраз `word` — текст фразы, `word_id` — id фразы, `word_count` у метки
— число фраз. Ошибки — человекочитаемый `detail`: 404 «Фраза не найдена», 409
конфликт, 422 неверное значение.

## Словарь фраз — `/api/phrases`

```
GET    /api/phrases?search=&status=&priority=&label=&limit=&offset=   → WordPage
POST   /api/phrases                    WordCreate → 201 WordOut (409 дубль)
GET    /api/phrases/{id}               → WordWithProgress (404)
PATCH  /api/phrases/{id}               WordUpdate → WordWithProgress (409, 404)
PUT    /api/phrases/{id}/status        {status} → WordWithProgress (422 неизвестный)
PUT    /api/phrases/{id}/priority      {priority} → WordWithProgress (409 не новой фразе)
DELETE /api/phrases/{id}               → 204 (404)
```

- `word` (текст фразы) — 1–200 символов после обрезки, иначе 422.
- Дубль — совпал ключ фразы (регистр и пробелы не важны) и хотя бы одно значение
  перевода; 409 «Фраза «…» с переводом «…» уже есть в словаре».
- Фильтры те же, что у `/api/words`: `search` по фразе и переводу, `status`
  (`new | learning | review | known | suspended`), `priority=true`,
  `label=<id>|none` — по меткам фраз. `from_id` не поддерживается (нужен только
  разметке).
- `labels` в `POST`/`PATCH` — названия меток **фраз**; недостающие создаются в
  `phrase_labels`. Метки слов с тем же названием не затрагиваются.
- Статус и отметка не пишут `phrase_review_log`.

## Метки фраз — `/api/phrase-labels`

```
GET    /api/phrase-labels              → LabelOut[] по алфавиту, word_count = число фраз
POST   /api/phrase-labels              {name, description?} → 201 LabelOut (409, 422)
PATCH  /api/phrase-labels/{id}         {name?, description?} → LabelOut (409, 404, 422)
DELETE /api/phrase-labels/{id}         → 204, снимает метку со всех фраз (404)
```

Правила названий и описаний — как у `/api/labels`. Маршрута `classify` нет.
Название, занятое меткой **слов**, для меток фраз свободно.

## Занятия с фразами — `/api/phrase-study`

```
GET    /api/phrase-study/session?mode=learn|review   → SessionOut
POST   /api/phrase-study/rounds        {word_ids} → ExerciseRound[]
GET    /api/phrase-study/new?limit=    → WordOut[]
POST   /api/phrase-study/select        {word_id, action, exclude_ids} → SelectResponse (404)
POST   /api/phrase-study/answer        AnswerRequest → AnswerResponse (404, 409, 422)
POST   /api/phrase-study/finish        {session_id, mode} → SessionFinishResult[]
POST   /api/phrase-study/reset/{id}    → 204
```

- Поведение — как у `/api/study/*` (раунды, перемешивание, повтор после ошибки,
  итог по режиму, идемпотентный `finish`), но всё берётся из таблиц фраз:
  `new_words` и `rounds` содержат только фразы, варианты ответа — только фразы,
  `finish` читает только `phrase_review_log`.
- `session` в `learn` берёт до `NEW_PHRASES_PER_SESSION` новых фраз (отмеченные
  первыми, затем по возрастанию `id`) в пределах `DAILY_NEW_PHRASES_LIMIT`; в
  `review` — до `REVIEW_PHRASES_PER_SESSION` фраз с подошедшим сроком.
- Вариантов ответа в карточке выбора может быть меньше 4, если фраз мало; правильный
  вариант есть всегда, двух с одинаковым переводом нет.
- Проверка письма, диктанта и сборки игнорирует апостроф дополнительно к правилам
  слов: `It's up to you.` = `its up to you`.
- `session_id` слов, переданный в `/api/phrase-study/finish`, — пустой список (и
  наоборот): журналы разные.

## Статистика фраз — `/api/phrase-stats`

```
GET    /api/phrase-stats/overview      → StatsOverview (total_words = всего фраз)
GET    /api/phrase-stats/daily?days=   → DailyStat[] (new_words = фраз взято в изучение)
```

Считается только по таблицам фраз; `/api/stats/*` по-прежнему считает только слова.

## Фронтенд

- `deckApi(deck: 'words' | 'phrases')` в `frontend/src/api/client.ts` — те же
  методы с префиксом колоды; `api` остаётся для слов.
- Маршруты: `/phrases`, `/phrases/new`, `/study?deck=phrases&mode=learn|review`,
  `/settings?tab=phrase-labels`. Без `deck` занятие — со словами.
