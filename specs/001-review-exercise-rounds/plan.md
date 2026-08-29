# Implementation Plan: Повторение раундами по типам упражнений

**Branch**: `001-review-exercise-rounds` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-review-exercise-rounds/spec.md`

## Summary

Режим «Повторение» перестаёт быть очередью из одного случайного упражнения на слово и
становится занятием из четырёх раундов: `choice_ru_en → choice_en_ru → letters → dictation`.
В каждом раунде все слова занятия проходятся одним типом упражнения; ошибка возвращает
слово в конец текущего раунда с пересобранной карточкой; следующий раунд начинается,
только когда все слова раунда отвечены верно.

Технически: сервер отдаёт весь план занятия одним ответом `GET /api/study/session?mode=review`
(идентификатор занятия + четыре раунда с готовыми упражнениями), проверяет каждый ответ
и пишет его в `review_log` с этим идентификатором, но **не трогает расписание** до конца
занятия. Расписание пересчитывается один раз — на `POST /api/study/review/finish`, где
сервер сам, по журналу занятия, определяет, какие слова прошли все четыре раунда и были
ли по ним ошибки. Очередь и порядок карточек по-прежнему живут на фронте, сервер
остаётся stateless: `session_id` — не состояние, а ключ корреляции в журнале.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript 5 / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, rapidfuzz;
React 19, TanStack Query, react-router, Tailwind 4, Vite

**Storage**: SQLite (`backend/data/app.db`), WAL, `PRAGMA foreign_keys=ON`

**Testing**: pytest (`backend/tests`, временная SQLite из `conftest.py`); на фронте
тест-раннера нет — ворота `yarn typecheck` и `yarn build`

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), десктопный браузер

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: занятие из 5 слов (20 карточек) проходится за ≤ 5 минут (SC-008);
сборка плана занятия — один запрос, 20 упражнений, ≤ 20 выборок дистракторов

**Constraints**: сервер stateless между запросами (Принцип I); `srs.py` без БД и без
обращения к системному времени (Принцип II); расписание пользователя не восстанавливается,
любое изменение схемы — только миграцией Alembic (Принцип IV)

**Scale/Scope**: словарь ~7 300 слов, один пользователь; затрагиваются 3 файла бэкенда
(`srs.py`, `study_service.py`, `schemas.py` + роутер), 1 миграция, ~4 файла фронтенда

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| **I. Сервер — единственный источник правды** | Правильность ответа считает только `exercises.check_answer`. Клиент решает, *какую карточку показать следующей*, но не *верен ли ответ* и не *какое расписание выставить*: итоговое качество на `finish` выводится сервером из `review_log`, а не приходит с клиента. Каждая попытка, включая повторы после ошибки, пишется в журнал. `session_id` не создаёт серверного состояния — это колонка журнала, никакой таблицы сессий и кеша очереди не появляется. | ✅ |
| **II. Чистое ядро расписания** | В `srs.py` добавляются чистая константа `REVIEW_ROUNDS` и чистая функция `session_quality(outcomes)`; импортов SQLAlchemy и обращений к `utcnow()` не прибавляется. Связывание журнала, SRS и БД — в `study_service.py`, роутер остаётся тонким. Размер занятия по-прежнему берётся из `settings.review_words_per_session`; новых «магических чисел» нет. | ✅ |
| **III. Поведение закрепляется тестами** | Меняются генерация упражнений, расписание и контракт API — значит, тесты в `backend/tests/test_srs.py`, `test_exercises.py`, `test_api.py` меняются в том же коммите. `frontend/src/api/types.ts` правится синхронно со `schemas.py`. | ✅ |
| **IV. Схема и данные неприкосновенны** | Одна миграция Alembic: nullable-колонка `review_log.session_id` + индекс. Таблица не пересоздаётся (`add_column`/`drop_column` напрямую, без `batch_alter_table`), внешние ключи не двигаются. Существующие строки журнала остаются с `session_id = NULL` и продолжают считаться в статистике. Необратимых действий не добавляется. | ✅ |
| **V. Простота и объяснённые решения** | Один новый эндпоинт (`finish`), одна колонка, план занятия отдаётся одним ответом. Отвергнутые альтернативы записаны в [research.md](./research.md). README обновляется в том же коммите (разделы «Повторения», «API»). | ✅ |

**Итог**: отступлений нет, раздел Complexity Tracking пуст.

## Project Structure

### Documentation (this feature)

```text
specs/001-review-exercise-rounds/
├── plan.md              # этот файл
├── research.md          # Phase 0: решения и отвергнутые альтернативы
├── data-model.md        # Phase 1: сущности, состояния, правила
├── quickstart.md        # Phase 1: как проверить фичу руками и тестами
├── contracts/
│   └── study-api.md     # Phase 1: контракт HTTP-эндпоинтов занятия
├── checklists/
│   └── requirements.md  # чек-лист качества спецификации
└── tasks.md             # Phase 2 (/speckit-tasks — этой командой не создаётся)
```

### Source Code (repository root)

```text
backend/
  app/
    srs.py                 + REVIEW_ROUNDS (порядок раундов), + session_quality();
                           − REVIEW_EXERCISES, _REVIEW_WEIGHTS, pick_review_exercise
    exercises.py           без изменений логики; build_exercise(attempt=…) уже даёт
                           пересборку карточки для повтора
    study_service.py       build_session → план из четырёх раундов + session_id;
                           answer_exercise → режим review не трогает прогресс;
                           + finish_review_session()
    schemas.py             + ReviewRound, ReviewFinishRequest/Result;
                           SessionOut: − exercises, + session_id, + rounds;
                           AnswerRequest: + mode, + session_id
    models.py              ReviewLog: + session_id (nullable, индекс)
    routers/study.py       + POST /study/review/finish
  alembic/versions/
    <new>_review_log_session_id.py   миграция: колонка + индекс
  tests/
    test_srs.py            порядок раундов, session_quality
    test_exercises.py      повторная карточка собирается заново
    test_api.py            план занятия, ответы без записи расписания, finish

frontend/
  src/
    api/types.ts           ReviewRound, SessionPayload, AnswerPayload, ReviewFinishResult
    api/client.ts          + finishReview(sessionId)
    components/
      ReviewSession.tsx    новый раннер: раунды, повторы, счётчики, вызов finish
      StudySession.tsx     остаётся раннером режима «Изучение»: стартовая очередь
                           становится пустой (поле SessionOut.exercises удалено),
                           поведение не меняется; из него выносится
      exercises/ExerciseView.tsx   общий переключатель карточек (вынос из StudySession)
    pages/StudyPage.tsx    выбирает раннер по режиму занятия

README.md                  разделы «Повторения (SM-2)» и «API»
```

**Structure Decision**: используется существующее разделение `backend/` + `frontend/`
из корня репозитория. Новых каталогов и пакетов не заводится: раннер занятия-повторения
встаёт рядом с существующим в `frontend/src/components/`, серверная логика — в уже
существующих `srs.py` / `study_service.py` / `routers/study.py`.

## Complexity Tracking

> Отступлений от конституции нет — таблица не заполняется.
