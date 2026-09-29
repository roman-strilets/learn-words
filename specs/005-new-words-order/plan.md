# Implementation Plan: Порядок изучения новых слов и поднятые слова

**Branch**: `005-new-words-order` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-new-words-order/spec.md`

## Summary

Сейчас `new_words_query` в `app/study_service.py` отбирает новые слова по `Word.id`
по возрастанию, и выбрать другой порядок нельзя. Доработка добавляет два рычага.

**Порядок.** Настройка `new_words_order` (`oldest_first` | `newest_first`) хранится в
пустовавшей таблице `settings` без миграции (R1). `fetch_new_words` читает её сам,
поэтому занятие, замена после «Уже знаю» и `GET /study/new` получают один и тот же
порядок без новых параметров. Маршруты `GET`/`PUT /api/settings`, секция на
странице «Настройки».

**Поднятие.** Колонка `words.priority` добавляется миграцией через `add_column` (R3).
Отбор сортирует `priority DESC, id ASC|DESC` (R4). Отметку ставит
`PUT /api/words/{id}/priority` только новому слову, а снимают её две точки, где
заводится прогресс (R5). В «Словаре» — кнопка в строке нового слова и фильтр.

Расписание, упражнения, «Повторение» и порядок карточек внутри занятия не меняются.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript 5 / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic; React 19,
TanStack Query. Новых зависимостей нет

**Storage**: SQLite. Одна миграция: `words.priority BOOLEAN NOT NULL DEFAULT false`
через `op.add_column`. Порядок — строка в существующей таблице `settings`

**Testing**: pytest (`backend/tests/test_api.py`, `backend/tests/test_import.py`);
фронт — `yarn typecheck`, `yarn build` и ручные сценарии [quickstart.md](./quickstart.md)

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), десктопный браузер

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: без изменений. Словарь — тысячи строк; сортировка по двум
колонкам без индекса укладывается в время нынешнего отбора

**Constraints**: сервер stateless (Принцип I) — настройка читается при каждом
отборе, а не кешируется; миграция без пересоздания таблицы (Принцип IV); контракт API
меняется синхронно в `schemas.py`, роутерах, тестах, `types.ts` и README

**Scale/Scope**: бэкенд — `models.py`, новая миграция, `schemas.py`,
`study_service.py`, `routers/words.py`, новый `routers/settings.py`, `main.py`;
фронт — `api/types.ts`, `api/client.ts`, `pages/SettingsPage.tsx`,
`pages/WordsPage.tsx`, `components/icons.tsx`; тесты; README

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Отбор и сортировку делает сервер; фронт только показывает переключатели. Настройка — строка в базе, а не состояние процесса: читается на каждом отборе, перезагрузка пересобирает занятие как раньше. Отметка и смена порядка — ручные действия, `review_log`, `ease` и `lapses` не трогают (FR-014). | ✅ |
| II. Чистое ядро расписания | `srs.py` не затрагивается. Логика отбора остаётся в `study_service.py`, роутеры тонкие. Новых числовых параметров нет; значения порядка — перечисление `NewWordsOrder`, а не строки в коде. | ✅ |
| III. Поведение закрепляется тестами | Меняются отбор слов, контракт API и импорт-инвариант — на каждое изменение есть тест (таблица в [quickstart.md](./quickstart.md)). `types.ts` меняется вместе с `schemas.py`. | ✅ |
| IV. Схема и данные неприкосновенны | Изменение модели — через миграцию с докстрингом «что и почему». `add_column` с `server_default`, без `batch_alter_table`: внешние ключи `progress` и `review_log` не уезжают. `downgrade` рабочий, теряет только отметки. Импорт существующие строки не трогает. Снятие отметки не стирает прогресс, подтверждение не нужно; возврат в «Новое» по-прежнему спрашивает его. | ✅ |
| V. Простота | Вариантов порядка два, случайного нет. Таблица `settings` переиспользуется, отдельной таблицы для отметок нет (R3). README обновляется в том же коммите: «Словарь», новый подраздел про порядок новых слов, «API». | ✅ |

**После Phase 1**: дизайн добавил одну колонку и два маршрута, без серверного
состояния и зависимостей. Нарушений нет, Complexity Tracking не нужен.

## Project Structure

### Documentation (this feature)

```text
specs/005-new-words-order/
├── plan.md              # этот файл
├── research.md          # Phase 0: R1–R7
├── data-model.md        # Phase 1: words.priority, ключ settings, правило отбора
├── quickstart.md        # Phase 1: тесты и ручные сценарии
├── contracts/
│   └── api.md           # Phase 1: /settings, /words/{id}/priority, фильтр, отбор
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── <rev>_word_priority.py   # + words.priority через add_column
├── app/
│   ├── models.py                # Word.priority
│   ├── schemas.py               # NewWordsOrder, AppSettings, WordPriorityUpdate, WordOut.priority
│   ├── study_service.py         # new_words_order(), new_words_query(order), снятие отметки
│   │                            #   в select_word и set_word_status, set_word_priority()
│   ├── main.py                  # подключение роутера настроек
│   └── routers/
│       ├── settings.py          # GET/PUT /settings
│       └── words.py             # PUT /words/{id}/priority, фильтр priority
└── tests/
    ├── test_api.py              # порядок, поднятие, снятие отметки, настройки
    └── test_import.py           # импорт не трогает priority

frontend/
└── src/
    ├── api/
    │   ├── types.ts             # NewWordsOrder, AppSettings, Word.priority
    │   └── client.ts            # getSettings, updateSettings, setWordPriority, listWords({priority})
    ├── components/
    │   └── icons.tsx            # иконка «поднять»
    └── pages/
        ├── SettingsPage.tsx     # секция «Порядок новых слов»
        └── WordsPage.tsx        # кнопка «Учить первым», фильтр «Учить первыми»

README.md                        # Словарь, порядок новых слов, API
```

**Structure Decision**: существующая структура «бэкенд + фронтенд». Чтение
настройки живёт в `study_service.py` рядом с `fetch_new_words`, её единственным
потребителем на сервере; отдельный модуль ради одного ключа не нужен. Роутер
настроек отдельный: `/settings` не относится ни к словам, ни к занятию, и следующая
настройка ляжет туда же.

## Complexity Tracking

Нарушений Constitution Check нет.
