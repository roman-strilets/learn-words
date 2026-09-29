# Implementation Plan: Метки слов

**Branch**: `006-word-labels` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-word-labels/spec.md`

## Summary

Словарь получает тематические метки: у слова их может быть сколько угодно, у метки —
сколько угодно слов.

**Хранение.** Две новые таблицы — `labels` (с ключом `name_key` для регистронезависимой
уникальности, R2) и связка `word_labels` с каскадами на оба конца (R1). Таблица
`words` не меняется, миграция только создаёт таблицы.

**Метки на слове.** `POST /words` и `PATCH /words/{id}` принимают `labels` — список
названий; сервер в той же транзакции берёт существующие метки и создаёт недостающие
(R3). Так отменённая или отклонённая (409) правка не оставляет новых меток. В «Словаре»
метки видны в строке, а меняются в `WordForm` — общем для «Добавить слово» и
«Изменить» — через компонент `LabelPicker` (R9).

**Отбор.** `GET /words?label=<id>|none` складывается с поиском, статусом и «Учить
первыми» (R5).

**Управление.** `GET /labels` (список по алфавиту со счётчиком слов) приходит с
основой: его читают подсказки формы (US1) и выпадающий список фильтра (US2).
`POST/PATCH/DELETE /labels` и вкладки «Общие» / «Метки» на странице «Настройки» (R10) —
в US3. Удаление спрашивает подтверждение с числом слов.

Занятия, расписание, упражнения, импорт и `review_log` не меняются.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic; React 19,
TanStack Query, react-router. Новых зависимостей нет

**Storage**: SQLite. Одна миграция: `create_table` для `labels` и `word_labels`, без
`batch_alter_table`. `PRAGMA foreign_keys=ON` уже включён в `app/db.py`

**Testing**: pytest (`backend/tests/test_api.py`, `backend/tests/test_import.py`);
фронт — `yarn typecheck`, `yarn build` и ручные сценарии [quickstart.md](./quickstart.md)

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), браузер

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: фильтр по метке на словаре 7 000+ слов — не медленнее нынешнего
поиска (SC-002): `EXISTS` по индексу `ix_word_labels_label_id`. Метки страницы из 50
слов — один `selectin`-запрос

**Constraints**: сервер stateless (Принцип I); миграция без пересоздания `words`
(Принцип IV); регистронезависимость считается в Python, т.к. `lower()` SQLite не знает
кириллицы (R2); контракт меняется синхронно в `schemas.py`, роутерах, тестах,
`types.ts` и README

**Scale/Scope**: бэкенд — `models.py`, новая миграция, `schemas.py`, новый
`labels_service.py`, `routers/words.py`, новый `routers/labels.py`, `main.py`; фронт —
`api/types.ts`, `api/client.ts`, новый `components/LabelPicker.tsx`,
`components/WordForm.tsx`, `pages/WordsPage.tsx`, `pages/SettingsPage.tsx`, новый
`components/LabelsSection.tsx`; тесты; README

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Уникальность, разрешение названий, фильтр и счётчики — на сервере; фронт показывает и собирает ввод. Серверного состояния нет. Правка меток — ручное действие со словарём: `review_log`, `ease`, `lapses` не трогает (FR-005), это закреплено тестом. Упражнения и `exercises.py` не затрагиваются. | ✅ |
| II. Чистое ядро расписания | `srs.py` и `study_service.py` не меняются. Логика меток — в отдельном `labels_service.py`, роутеры тонкие. Предел длины — именованная константа `LABEL_NAME_MAX` с комментарием; параметром алгоритма она не является, поэтому не `config.py` (R7). | ✅ |
| III. Поведение закрепляется тестами | Новый контракт и каждое правило из data-model покрыты тестами (таблица в [quickstart.md](./quickstart.md)), включая инвариант импорта. `types.ts` меняется вместе с `schemas.py`. | ✅ |
| IV. Схема и данные неприкосновенны | Миграция с докстрингом «что и почему», только `create_table`: внешние ключи `progress`/`review_log` не уезжают. `downgrade` рабочий, теряет только разметку. Импорт не трогает метки (тест). Удаление метки необратимо стирает разметку — спрашивает подтверждение с числом слов (FR-013); прогресс оно не стирает. | ✅ |
| V. Простота | Библиотек нет: `LabelPicker` и вкладки — на `useState` и query-параметре. Нет иерархии, цветов, массовой разметки и занятий по метке — занятия по метке записываются в README «Что не сделано». `Label.words` не заводится. README обновляется в том же коммите: «Словарь», новый подраздел «Метки», «API», «Что не сделано». | ✅ |

**После Phase 1**: дизайн добавил две таблицы, один сервис и четыре маршрута, без
серверного состояния и зависимостей. Нарушений нет, Complexity Tracking не нужен.

## Project Structure

### Documentation (this feature)

```text
specs/006-word-labels/
├── plan.md              # этот файл
├── research.md          # Phase 0: R1–R12
├── data-model.md        # Phase 1: labels, word_labels, валидация, разрешение названий
├── quickstart.md        # Phase 1: тесты и ручные сценарии
├── contracts/
│   └── api.md           # Phase 1: /labels, labels в /words, фильтр label
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── <rev>_word_labels.py     # + labels, word_labels (create_table)
├── app/
│   ├── models.py                # Label, word_labels, Word.labels
│   ├── schemas.py               # LABEL_NAME_MAX, LabelRef, LabelOut, LabelInput,
│   │                            #   WordOut.labels, WordCreate/WordUpdate.labels
│   ├── labels_service.py        # label_key(), label_sort_key(), list_labels(),
│   │                            #   resolve_labels(), find_by_key()
│   ├── main.py                  # подключение роутера меток
│   └── routers/
│       ├── labels.py            # GET /labels (основа), POST/PATCH/DELETE (US3)
│       └── words.py             # labels в create/update, фильтр label
└── tests/
    ├── test_api.py              # метки на слове, фильтр, управление, инварианты
    └── test_import.py           # импорт не трогает метки

frontend/
└── src/
    ├── api/
    │   ├── types.ts             # LabelRef, Label, Word.labels, WordInput.labels
    │   └── client.ts            # listLabels, createLabel, renameLabel, deleteLabel, listWords({label})
    ├── components/
    │   ├── LabelPicker.tsx      # чипы + ввод с подсказками и «Создать метку»
    │   ├── LabelsSection.tsx    # вкладка «Метки»: список, создание, переименование, удаление
    │   └── WordForm.tsx         # поле меток
    └── pages/
        ├── AddWordPage.tsx      # инвалидация ['labels'] после добавления
        ├── WordsPage.tsx        # метки в строке, фильтр по метке, сброс удалённой
        └── SettingsPage.tsx     # вкладки «Общие» / «Метки» (?tab=labels)

README.md                        # Словарь, Метки, API, Что не сделано
```

**Structure Decision**: существующая структура «бэкенд + фронтенд». Метки получают
свой сервис, а не место в `study_service.py`: тот связывает SRS, упражнения и базу, а
метки к занятиям не относятся. Разрешение названий нужно и роутеру слов, и роутеру
меток (ключ), поэтому живёт в сервисе, а не в одном из роутеров. `LabelsSection` —
отдельный файл, потому что `SettingsPage.tsx` уже содержит две секции и вкладку
добавлять проще, чем раздувать файл.

## Complexity Tracking

Нарушений Constitution Check нет.
