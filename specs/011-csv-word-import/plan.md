# Implementation Plan: Импорт слов из CSV

**Branch**: `main` (коммиты прямо в `main`) | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-csv-word-import/spec.md`

## Summary

На странице «Словарь» появляется «Импорт из CSV». Пользователь выбирает файл с
колонками слово, перевод, пример, перевод примера, метка. Новые слова заводятся со
статусом «Новое». У существующих слов дописывается новый перевод через «;»,
подставляется пример, если его не было, и добавляются метки. Недостающие метки
создаются. Прогресс и журналы ответов не меняются. Повторный импорт того же
файла ничего не меняет. После импорта показывается отчёт с пропущенными строками
и причинами.

Технически: новый модуль `app/word_import.py` с чистой функцией `parse_import`
(кодировка, разделитель, колонки, проверка строк — без базы) и `apply_import`
(слияние со словарём одной транзакцией). Правила слияния
`row_for_translation`/`merge_translation` переезжают сюда из `app/cli.py`, и
консольный импорт продолжает ими пользоваться. Маршрут `POST /api/words/import`
принимает файл сырым телом `text/csv`, поэтому новая зависимость не нужна. На
фронте — панель `ImportPanel` в слоте `panel` «Словаря», рядом с автоматической
разметкой.

## Technical Context

**Language/Version**: Python ≥ 3.12 (бэкенд), TypeScript strict (фронтенд)

**Primary Dependencies**: FastAPI 0.141, SQLAlchemy 2.0, Pydantic v2, стандартный
`csv`; React 19, TanStack Query, Tailwind 4. Новых зависимостей нет: сырое тело
вместо multipart (research R1).

**Storage**: SQLite. Схема не меняется, миграции нет (data-model.md).

**Testing**: pytest на временной SQLite (`conftest.py`); фронтенд — `yarn typecheck`,
`yarn build`

**Target Platform**: локальное веб-приложение (браузер + uvicorn на localhost)

**Project Type**: web application (backend + frontend, yarn workspaces)

**Performance Goals**: `dictionary.csv` (≈ 7 700 строк, 1 МБ) импортируется меньше
чем за 10 с (SC-002). Индекс слов и меток держится в памяти, без запросов на каждую
строку (research R8).

**Constraints**: файл ≤ 5 МБ (`import_max_bytes`), UTF-8; импорт применяется
целиком или никак; `progress` и журналы ответов не трогаются.

**Scale/Scope**: один пользователь, словарь в тысячи–десятки тысяч слов; один
маршрут, один модуль бэкенда, одна панель фронтенда.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Сервер — источник правды | Разбор, проверка и слияние — на сервере. Клиент только отправляет файл и показывает отчёт. Импорт не пишет в `review_log` и не трогает `ease`/`lapses` — это ручное действие со словарём. Сервер stateless: отчёт не хранится | ✅ |
| II. Чистое ядро расписания | `srs.py` не затронут. `parse_import` — чистая функция без базы. Роутер тонкий: тело → `parse_import` → `apply_import` → ответ. Пределы — в `config.py` (`import_max_bytes`, `import_skipped_report_max`) | ✅ |
| III. Тесты | Табличные тесты разбора (`test_word_import.py`). API-тесты слияния, идемпотентности, отката и кодов ошибок в `test_api.py`. Типы `ImportReport` синхронны в `schemas.py` и `types.ts`. Существующий `test_import.py` закрепляет консольный импорт после переноса функций | ✅ |
| IV. Данные неприкосновенны | Миграции нет. Импорт идемпотентен (FR-012) и атомарен (FR-015). Расписание не стирается, поэтому подтверждение не требуется. Правило об импорте уточняется поправкой 1.2.0 (T000, см. ниже): оба импорта только дописывают в ручные записи | ✅ после T000 |
| V. Простота | Новых зависимостей нет. Сырое тело вместо multipart. Нет предпросмотра, нет шаблона, нет фоновых задач. README меняется в том же коммите (FR-021): раздел про импорт, «API», фраза «Импорт CSV меток не трогает» уточняется до консольного импорта | ✅ |
| Контракт API | `schemas.py`, роутер, `test_api.py`, `types.ts` и раздел «API» README меняются одним коммитом | ✅ |
| Ошибки API | Человекочитаемый `detail`. 422 — непригодный файл, 413 — слишком большой | ✅ |

**Поправка IV.** Сейчас принцип IV требует, чтобы консольный импорт (`app/cli.py`)
«не трогал записи, заведённые вручную». Но `cli.py` и сейчас дописывает новое
значение перевода в ручную запись (`_row_for_translation`). Импорт из интерфейса
делает то же самое по решению пользователя (Clarifications спецификации). Текст
расходится с кодом, а не только с этой фичей, поэтому правится принцип, а не
записывается отступление (Governance: повторяющееся отступление — повод для
поправки). Поправка 1.2.0 (MINOR: правило распространяется на второй способ
импорта) идёт отдельным коммитом (T000). Она говорит, что оба импорта идемпотентны
и в ручные записи только дописывают: новое значение перевода, пустой пример,
метки. Ничего не удаляется, не дробится и не перезаписывается, прогресс и
журналы не трогаются.

**Post-design re-check**: после Phase 1 таблица не меняется. В data-model нет
новых таблиц. Контракт — один маршрут без состояния. Журналы и `progress` явно
перечислены в «Побочных эффектах» контракта как нетронутые.

## Project Structure

### Documentation (this feature)

```text
specs/011-csv-word-import/
├── plan.md              # этот файл
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── api.md           # Phase 1
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── word_import.py        # НОВЫЙ: parse_import, apply_import, row_for_translation,
│   │                         #        merge_translation, ImportFileError
│   ├── cli.py                # общие правила слияния берутся из word_import
│   ├── config.py             # import_max_bytes, import_skipped_report_max
│   ├── schemas.py            # ImportReport, ImportSkippedRow
│   ├── main.py               # подключение роутера импорта
│   └── routers/
│       └── word_import.py    # НОВЫЙ: POST /api/words/import
└── tests/
    ├── test_word_import.py   # НОВЫЙ: табличные тесты parse_import
    ├── test_api.py           # POST /api/words/import
    └── test_import.py        # без изменений поведения — страховка переноса

frontend/src/
├── api/
│   ├── types.ts              # ImportReport, ImportSkippedRow
│   └── client.ts             # importWords(file)
├── components/
│   └── ImportPanel.tsx       # НОВЫЙ: подсказка, выбор файла, отчёт/ошибка
└── pages/
    └── WordsPage.tsx         # кнопка «Импорт из CSV», одна открытая панель за раз

README.md                     # раздел про импорт из интерфейса, «API», уточнение про метки
```

**Structure Decision**: структура web application уже есть (`backend/`,
`frontend/`). Маршрут вынесен в отдельный роутер `routers/word_import.py`, а не в
фабрику `make_words_router`: фабрика общая для слов и фраз, а импорт есть только у
слов. Роутер подключается раньше `words.router`. Конфликта путей нет: у
`/api/words/{word_id}` нет метода POST, но ранний порядок снимает вопрос совсем.

## Complexity Tracking

Отступлений от конституции нет: расхождение с принципом IV закрывается поправкой
1.2.0 (T000), а не исключением.
