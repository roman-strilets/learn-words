# Implementation Plan: Словарь фраз

**Branch**: `009-phrase-dictionary` (работа идёт в `main`) | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-phrase-dictionary/spec.md`

## Summary

Вторая колода — фразы — со своим словарём, метками, занятиями «Учить фразы» /
«Повторить фразы» и статистикой. Хранится в пяти новых таблицах, связей со словами
нет. Логику занятия не копируем: сервисы и роутеры слов параметризуются описанием
колоды (`Deck`), а модели фраз несут синонимы с именами полей слов, так что те же
Pydantic-схемы и тот же фронтенд-раннер обслуживают обе колоды. Маршруты слов не
меняются; фразы живут под `/api/phrases`, `/api/phrase-labels`, `/api/phrase-study`,
`/api/phrase-stats`. Отличия фраз от слов — длина до 200 символов, апостроф не
важен при проверке, порядок новых всегда «по добавлению», метки свои, без
автоматической разметки. Подробности решений — [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.12 (бэкенд), TypeScript strict / React 19 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, rapidfuzz; Vite, TanStack Query, react-router, Tailwind 4. Новых зависимостей нет.

**Storage**: SQLite (`backend/data/app.db`), одна новая миграция Alembic: таблицы `phrases`, `phrase_progress`, `phrase_review_log`, `phrase_labels`, `phrase_label_links` ([data-model.md](data-model.md))

**Testing**: pytest на временной SQLite (`backend/tests/`), `yarn typecheck`, `yarn build`, `ruff check`

**Target Platform**: локальный однопользовательский веб (браузер + uvicorn)

**Project Type**: web application (backend + frontend, монорепа)

**Performance Goals**: как у слов — ответы API мгновенны на словаре фраз в сотни–тысячи записей

**Constraints**: таблицы и поведение слов не меняются (SC-003); сервер stateless; проверка ответа только на сервере; расписание пересчитывается один раз в `finish`

**Scale/Scope**: ~5 таблиц, 4 группы маршрутов, 2 новые страницы фронта (`/phrases`, `/phrases/new`), вкладка настроек, параметризация занятия, главной и статистики

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Ответы по фразам проверяет `exercises.check_answer` с колодой; каждая попытка пишется в журнал колоды (`phrase_review_log`); очередь на фронте, сервер stateless; ручные действия журнал не трогают | ✅ с отступлением: журнал фраз — отдельная таблица, см. Complexity Tracking |
| II. Чистое ядро расписания | `srs.py` не меняется и не узнаёт о колодах; `now`/`rng` передаются как раньше; три новых параметра в `config.py` (`NEW_PHRASES_PER_SESSION`, `REVIEW_PHRASES_PER_SESSION`, `DAILY_NEW_PHRASES_LIMIT`); роутеры фраз тонкие — фабрики над теми же сервисами | ✅ |
| III. Поведение закреплено тестами | Новые тесты: CRUD и дубли фраз, метки фраз, изоляция колод (занятия, варианты ответа, `finish`, статистика), апостроф в `normalize_answer`, дистракторы при 1–3 фразах, миграция поверх базы со словами; существующие тесты слов проходят без правок; `types.ts` синхронен со схемами | ✅ |
| IV. Схема и данные неприкосновенны | Одна миграция только создаёт таблицы, таблицы слов не трогает; `downgrade` удаляет только таблицы фраз; удаление фразы и «Новое» спрашивают подтверждение; импорт CSV фразы не трогает; прогресс фраз отдельно от фраз | ✅ |
| V. Простота | Без новых зависимостей; `Deck` — абстракция под реально существующую вторую колоду, а не «на будущее»; авторазметка, импорт и порядок фраз — в «Что не сделано» README; README получает раздел «Фразы» и маршруты в «API» в том же коммите | ✅ |

**Повторная проверка после Phase 1**: модель данных и контракт отступлений не
добавили. Схемы общие, поэтому правило «schemas.py ↔ types.ts в одном коммите»
выполняется естественно: новых схем нет, кроме длины фразы в `PhraseCreate`/
`PhraseUpdate` (наследники `WordCreate`/`WordUpdate`).

## Project Structure

### Documentation (this feature)

```text
specs/009-phrase-dictionary/
├── plan.md              # этот файл
├── research.md          # решения R1–R9
├── data-model.md        # таблицы фраз и описание колоды
├── quickstart.md        # проверка руками и тестами
├── contracts/api.md     # маршруты фраз
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
  alembic/versions/<rev>_phrases.py   новые таблицы фраз
  app/
    decks.py             NEW: Deck, WORDS, PHRASES
    models.py            + Phrase, PhraseProgress, PhraseReviewLog, PhraseLabel,
                           phrase_label_links (синонимы word/word_key/word_id)
    config.py            + new_phrases_per_session, review_phrases_per_session,
                           daily_new_phrases_limit
    schemas.py           + PhraseCreate/PhraseUpdate (длина 200)
    exercises.py         normalize_answer(drop_apostrophes), дистракторы и check по колоде
    study_service.py     все функции принимают deck (по умолчанию WORDS)
    labels_service.py    resolve_labels и счётчики по колоде
    word_filters.py      filtered_words(deck=…)
    routers/
      words.py, labels.py, study.py, stats.py   → фабрики make_*_router(deck)
      deps.py            get_item(deck)
    main.py              подключает роутеры фраз
  tests/
    test_phrases_api.py  NEW: словарь, метки, занятия, статистика, изоляция
    test_exercises.py    + апостроф, дистракторы колоды фраз
    test_migrations.py   NEW или в test_api: миграция поверх базы со словами
frontend/src/
  api/client.ts          deckApi(deck); api = deckApi('words') + настройки
  api/types.ts           type Deck = 'words' | 'phrases'
  components/            WordForm, LabelPicker, LabelsSection, StudySession,
                         RoundsRunner, StudyModeLinks — проп deck
  components/DictionaryList.tsx   NEW: список/строка словаря, вынесенные из WordsPage
  pages/PhrasesPage.tsx, AddPhrasePage.tsx   NEW
  pages/HomePage.tsx, StudyPage.tsx, StatsPage.tsx, SettingsPage.tsx   колоды
  App.tsx                пункт «Фразы», маршруты /phrases, /phrases/new
README.md                раздел «Фразы», API, настройки, «Что не сделано»
```

**Structure Decision**: существующая монорепа backend + frontend, без новых пакетов.
Код занятия, словаря и меток общий для колод; новые файлы — только описание колоды,
миграция, тесты фраз и две страницы.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Принцип I требует, чтобы каждая попытка попадала в `review_log`; попытки по фразам пишутся в `phrase_review_log` | Пользователь просил хранить фразы отдельно и не пересекать со словами; у журнала фраз внешний ключ на `phrases`, а `finish` и статистика слов не могут случайно задеть фразы (SC-002, SC-003) | Общий `review_log` с nullable `phrase_id`: пересборка живой таблицы с месяцами прогресса через `batch_alter_table` и фильтр по колоде в каждом запросе статистики и `finish` — забытый фильтр смешивает колоды. Дух принципа (полный журнал каждой попытки, статистика только из журнала) сохраняется; поправку конституции («журнал колоды») стоит внести отдельным коммитом |
