# Implementation Plan: Упражнение «Напишите слово по-английски»

**Branch**: `008-ru-en-writing` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-ru-en-writing/spec.md`

## Summary

В занятие добавляется пятый раунд `writing_ru_en`. Он стоит четвёртым, перед диктантом.
На карточке только русский перевод, пользователь пишет английское слово. Подсказок нет,
в данных карточки ответа нет. Сервер проверяет ответ теми же правилами, что в диктанте,
и игнорирует `used_hint` для этого типа.

Почти всё поведение (план, перемешивание, правило «все раунды» на `finish`) уже
выводится из кортежа `EXERCISE_ROUNDS`. Поэтому изменение сводится к новому значению
перечисления, схеме карточки, ветке в `build_exercise`, одной строке про подсказку
и карточке на фронтенде. Миграция не нужна.

## Technical Context

**Language/Version**: Python ≥ 3.12 (бэкенд), TypeScript strict (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Pydantic v2; React 19, TanStack Query, Tailwind 4

**Storage**: SQLite. `review_log.exercise` — `String(24)` без ограничения, схема не меняется

**Testing**: pytest (`backend/tests/`); фронтенд — `yarn typecheck`, `yarn build`

**Target Platform**: локальное веб-приложение (браузер + uvicorn)

**Project Type**: web application (backend + frontend)

**Performance Goals**: не меняются. Карточка строится без запросов к базе: дистракторы не нужны

**Constraints**: ответ не уходит в браузер до проверки; подсказок нет (FR-003)

**Scale/Scope**: один пользователь; +1 раунд на занятие из ~5 слов

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Ответ проверяет `check_answer`. Решение в карточку не кладётся. `used_hint` для типа без подсказок сервер обнуляет сам (R6). Каждая попытка идёт в `review_log` общим путём | ✅ |
| II. Чистое ядро расписания | В `srs.py` меняется только кортеж `EXERCISE_ROUNDS` и константа типов без подсказки. Без базы, без времени. Новых магических чисел нет | ✅ |
| III. Поведение закрепляется тестами | Табличный тест проверки и сборки карточки в `test_exercises.py`. Тесты плана из пяти раундов, `used_hint` и `finish` в `test_api.py`. `types.ts` синхронно со `schemas.py` | ✅ |
| IV. Схема и данные неприкосновенны | Таблицы не меняются, миграции нет (R2). Старый журнал остаётся валидным | ✅ |
| V. Простота | Ни зависимостей, ни настроек. Отдельный компонент вместо флага в `DictationCard` (R8). README обновляется в том же коммите: таблица раундов, «четыре» → «пять», раздел API | ✅ |

Изменение контракта API идёт одним коммитом: `schemas.py`, `test_api.py`, `types.ts`,
README. Роутер не меняется: он работает с объединением `Exercise`.

**Post-design re-check**: research, data-model и contracts нарушений не добавили. ✅

## Project Structure

### Documentation (this feature)

```text
specs/008-ru-en-writing/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models.py          # ExerciseType.WRITING_RU_EN
│   ├── srs.py             # EXERCISE_ROUNDS: пять раундов; EXERCISES_WITHOUT_HINT
│   ├── schemas.py         # WritingRuEnExercise, объединение Exercise
│   ├── exercises.py       # ветка build_exercise без дистракторов
│   └── study_service.py   # answer_exercise: used_hint=False для типов без подсказки;
│                          # докстринги «четыре раунда» → «все раунды»
└── tests/
    ├── test_exercises.py  # сборка карточки, табличная проверка ответа
    └── test_api.py        # пять раундов, used_hint, finish; переименования «four»

frontend/src/
├── api/types.ts                         # 'writing_ru_en', WritingRuEnExercise
├── api/client.ts                        # комментарий «четыре раунда»
└── components/
    ├── RoundsRunner.tsx                 # EXERCISE_LABEL, комментарий
    └── exercises/
        ├── ExerciseView.tsx             # case 'writing_ru_en'
        └── WritingCard.tsx              # новая карточка

README.md                                # таблица раундов, «пять», раздел API
```

**Structure Decision**: Существующая раскладка web application (`backend/`,
`frontend/`). Новый файл один — `WritingCard.tsx`.

## Complexity Tracking

Нарушений конституции нет.
