# Implementation Plan: Занятие по группе слов

**Branch**: `main` (коммиты прямо в `main`) | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-label-group-study/spec.md`

## Summary

Новое занятие «Учить группу»: пользователь выбирает метку слов, и занятие берёт
порцию её слов (по умолчанию 5) в любом статусе и сразу ведёт пять раундов
упражнений, как «Повторить слова», без знакомства. Порции идут по кругу: каждая
берёт непройденные слова текущего круга, на стыке добирается из следующего круга, а
новый круг идёт в другом порядке. Интервальных повторений, дневных лимитов и влияния
на основной прогресс нет.

Технически: круг хранится в новой таблице `group_cycle_words` (строка на метку,
круг и слово, с позицией и отметкой прохождения), ответы — в новой таблице
`group_review_log`, которую не читают ни статистика, ни обычные занятия. Логика круга
— чистая функция в `app/group_cycles.py` с табличными тестами; связывание с базой — в
`app/group_study_service.py`; маршруты — `/api/group-study/*`. На фронте
`RoundsRunner` получает маршруты ответа и итога пропсом и обслуживает новую страницу
`/study/group` без копирования правил раундов.

## Technical Context

**Language/Version**: Python ≥ 3.12 (бэкенд), TypeScript strict (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2; React 19,
TanStack Query, react-router, Tailwind 4. Новых зависимостей нет.

**Storage**: SQLite (WAL, `foreign_keys=ON`); две новые таблицы одной миграцией
поверх `31a578309216`

**Testing**: pytest на временной SQLite (`conftest.py`); фронтенд — `yarn typecheck`,
`yarn build`

**Target Platform**: локальное веб-приложение (браузер + uvicorn на localhost)

**Project Type**: web application (backend + frontend, yarn workspaces)

**Performance Goals**: сборка порции и выбор групп — как нынешние занятия
(один-два запроса на метку из сотен слов; словарь 7 000+ записей)

**Constraints**: основной прогресс, журнал `review_log` и статистика неизменны
(SC-002); сервер stateless между запросами, кроме долговременных данных круга

**Scale/Scope**: один пользователь; десятки меток, до сотен слов в метке

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Ответ проверяет `exercises.check_answer`; круг и прохождение решает сервер по своему журналу (`finish` не принимает от клиента, какое слово в каком круге); очередь занятия на фронте, перезагрузка пересобирает порцию из сохранённого круга; запись круга при сборке — долговременные данные, не серверная сессия (research R7) | ✅ с отступлением: попытки пишутся в `group_review_log`, а не в `review_log` — см. Complexity Tracking |
| II. Чистое ядро расписания | `srs.py` не меняется; логика круга — чистая функция `group_cycles.py` (без базы, `rng` параметром), время — `app.clock.utcnow()`; связывание — `group_study_service.py`, роутер тонкий; `GROUP_WORDS_PER_SESSION` в `config.py` | ✅ |
| III. Поведение закреплено тестами | Табличные тесты круга, API-тесты маршрутов и изоляции (снимок прогресса, журнала, статистики и обычных занятий до/после), миграция; `types.ts` синхронно со `schemas.py` | ✅ |
| IV. Схема и данные неприкосновенны | Одна миграция только создаёт таблицы, существующие не трогает; `downgrade` удаляет только новые; каскады FK: метка → круги, слово → строки круга и журнала; «Начать круг заново» прогресс не стирает, поэтому подтверждения не требует | ✅ |
| V. Простота | Без новых зависимостей и абстракций «на будущее»: колоду не обобщаем на фразы (FR-020), статистику групп не строим; README получает раздел «Занятие по группе», маршруты в «API», параметр в «Настройки» и правку «Что не сделано» в том же коммите | ✅ |

**Повторная проверка после Phase 1**: модель данных и контракт новых отступлений не
добавили. Изоляция от основного прогресса держится на том, что сервис группы не
импортирует `Progress`/`ReviewLog` для записи; это закрепляет API-тест изоляции.

## Project Structure

### Documentation (this feature)

```text
specs/010-label-group-study/
├── plan.md              # этот файл
├── research.md          # решения R1–R11
├── data-model.md        # group_cycle_words, group_review_log, переходы круга
├── quickstart.md        # проверка тестами и руками
├── contracts/api.md     # маршруты /api/group-study
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
  alembic/versions/<rev>_group_study.py   NEW: group_cycle_words, group_review_log
  app/
    models.py            + GroupCycleWord, GroupReviewLog
    config.py            + group_words_per_session
    group_cycles.py      NEW: чистая логика круга (порция, добор, новый круг, рестарт)
    group_study_service.py  NEW: группы, сборка, ответ, finish, рестарт над базой
    schemas.py           + GroupOut, GroupSessionRequest/Out, GroupAnswerRequest/Response,
                           GroupFinishRequest/Result
    routers/group_study.py  NEW: /api/group-study/*
    main.py              подключает роутер
  tests/
    test_group_cycles.py     NEW: табличные тесты чистой логики
    test_group_study_api.py  NEW: маршруты, идемпотентность, изоляция
    test_migrations.py       + новые таблицы поверх базы со словами
frontend/src/
  api/types.ts           + Group* типы
  api/client.ts          + groupApi
  components/RoundsRunner.tsx   проп api: { answer, finish } вместо deck + mode
  components/StudySession.tsx, pages/StudyPage.tsx   передают api из deckApi(deck)
  pages/GroupStudyPage.tsx      NEW: выбор группы, занятие, итог, «Следующая порция»
  pages/HomePage.tsx     кнопка «Учить группу» в блоке «Слова»
  App.tsx                маршрут /study/group
README.md                «Занятие по группе», API, Настройки, «Что не сделано»
```

**Structure Decision**: существующая монорепа backend + frontend без новых пакетов.
Общие правила раундов (`_rounds_for`, `build_exercise`, `check_answer`,
`RoundsRunner`) переиспользуются; новые файлы — только логика круга, её сервис,
роутер, страница и тесты.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Принцип I требует, чтобы каждая попытка попадала в `review_log`; попытки занятия по группе пишутся в `group_review_log` | Пользователь потребовал, чтобы занятие по группе не влияло на основной прогресс и статистику (FR-006–FR-010, SC-002); в `review_log` обязательные колонки перехода расписания, которого у группы нет, а у новых слов нет и статуса | `review_log` + колонка-признак: фильтр в каждом запросе статистики и `finish` (забытый — тихо смешивает числа) и выдуманные `status_*`/`ease_after`. Дух принципа (каждая попытка в журнале, итог выводит сервер из журнала) сохранён. Это второе такое отступление после `phrase_review_log`, поэтому перед реализацией — поправка конституции отдельным коммитом: «каждая попытка пишется в журнал своего вида занятия» (MINOR, v1.1.0) |
