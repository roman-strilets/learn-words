# Implementation Plan: Изучение раундами по типам упражнений

**Branch**: `003-learn-exercise-rounds` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-learn-exercise-rounds/spec.md`

## Summary

Режим «Изучение» перестаёт быть очередью, в которой слово поднимается по шагам
знакомства поодиночке, и повторяет устройство повторения: фаза знакомства по всем
словам, затем четыре раунда `choice_ru_en → choice_en_ru → letters → dictation`.
Ошибка возвращает слово в конец текущего раунда с пересобранной карточкой; следующий
раунд начинается, только когда все слова текущего отвечены верно.

Технически раунды изучения нельзя отдать вместе с занятием: их состав известен лишь
после знакомства — «Уже знаю» выводит слово и добирает замену. Поэтому появляется
`POST /api/study/rounds` с готовым списком слов, который собирает план целиком.
`GET /api/study/session?mode=learn` начинает выдавать `session_id` (ключ корреляции
в журнале, не серверное состояние), ответы в режиме `learn` перестают двигать
расписание, а `POST /api/study/review/finish` становится общим для двух режимов
`POST /api/study/finish` с полем `mode`: повторение подводит итог по худшей попытке,
изучение выпускает слово в повторения независимо от ошибок (уточнение 2026-08-30).

Больше всего кода при этом удаляется, а не добавляется: пошаговый выбор упражнения
(`srs.exercise_for`, `study_service._next_exercise`) и learn-ветка в `answer_exercise`
исчезают, а раннер раундов с фронта становится общим для обоих режимов.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript 5 / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, rapidfuzz;
React 19, TanStack Query, react-router, Tailwind 4, Vite

**Storage**: SQLite (`backend/data/app.db`), WAL, `PRAGMA foreign_keys=ON`.
Изменений схемы не требуется: `review_log.session_id` заведён миграцией фичи 001

**Testing**: pytest (`backend/tests`, временная SQLite из `conftest.py`); на фронте
тест-раннера нет — ворота `yarn typecheck` и `yarn build`

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), десктопный браузер

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: занятие из 5 слов (5 карточек знакомства + 20 упражнений)
проходится за ≤ 7 минут (SC-009); сборка плана раундов — один запрос,
20 упражнений, ≤ 20 выборок дистракторов

**Constraints**: сервер stateless между запросами (Принцип I); `srs.py` без БД и без
обращения к системному времени (Принцип II); расписание пользователя не восстанавливается
(Принцип IV)

**Scale/Scope**: словарь ~7 300 слов, один пользователь; затрагиваются 4 файла бэкенда
(`srs.py`, `study_service.py`, `schemas.py`, `routers/study.py`), миграций нет,
~6 файлов фронтенда, 3 файла тестов, README

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| **I. Сервер — единственный источник правды** | Правильность ответа по-прежнему считает только `exercises.check_answer`; клиент решает, какую карточку показать следующей, но не верен ли ответ и не какое расписание выставить. Итог занятия выводит сервер из `review_log` по ключу занятия — клиент не присылает ни оценку, ни новое расписание. `POST /study/rounds` серверного состояния не создаёт: он собирает карточки по переданным словам и ничего не запоминает. `mode` приходит от клиента и в `/answer` (так уже сейчас), и в `/finish` — см. пометку ниже. | ✅ |
| **II. Чистое ядро расписания** | В `srs.py` приватная `_graduate` становится публичной `graduate()`, `REVIEW_ROUNDS` переименовывается в `EXERCISE_ROUNDS` (порядок один на два режима), кортеж `LEARNING_STEPS` заменяется числом `RELEARN_STEPS`. Все функции остаются чистыми, импортов SQLAlchemy и вызовов `utcnow()` не прибавляется. Связывание журнала, SRS и БД — в `study_service.py`; роутер остаётся тонким. Размер занятия по-прежнему из `settings.new_words_per_session`, новых «магических чисел» нет. | ✅ |
| **III. Поведение закрепляется тестами** | Меняются генерация упражнений, расписание и контракт API — тесты в `test_srs.py`, `test_api.py` правятся в том же коммите; для `POST /study/rounds` и `POST /study/finish?mode=learn` добавляются новые. `frontend/src/api/types.ts` меняется синхронно со `schemas.py`. | ✅ |
| **IV. Схема и данные неприкосновенны** | Миграция не нужна: колонка `review_log.session_id` уже есть, новых полей не появляется. Записи журнала прежних занятий остаются валидными. Необратимых действий не добавляется, подтверждения не требуются. | ✅ |
| **V. Простота и объяснённые решения** | Один новый эндпоинт (`/study/rounds`), один переименованный (`/study/finish`), ноль новых зависимостей и таблиц. Чистое удаление: `exercise_for`, `_next_exercise`, `SelectResponse.next_exercise`, learn-ветка `answer_exercise`, дубликат раннера раундов на фронте. Отвергнутые альтернативы записаны в [research.md](./research.md). README обновляется в том же коммите. | ✅ |

**Пометка к принципу I**: `mode` в `POST /study/finish` — параметр запроса, а не факт,
который сервер обязан проверять; прецедент уже есть в `AnswerRequest.mode`. Вывести
режим из данных нельзя: слова в статусе `learning` встречаются и в занятии-повторении
(туда они попадают после забывания), поэтому статус слова режим не различает. Хранить
режим в журнале означало бы новую колонку и миграцию ради значения, которое клиент и
так знает, — по принципу V этого не делаем. Приложение однопользовательское и локальное,
подделывать себе режим некому.

**Итог**: отступлений нет, раздел Complexity Tracking пуст.

**Перепроверка после Phase 1**: дизайн не добавил ни таблиц, ни колонок, ни зависимостей;
миграции по-прежнему нет (Принцип IV). `POST /study/rounds` подтверждён как чистое
чтение без серверного состояния, а вывод итога занятия остался целиком на сервере
(Принцип I). Все решения и отвергнутые альтернативы записаны в
[research.md](./research.md) (Принцип V). Вердикт не меняется.

## Project Structure

### Documentation (this feature)

```text
specs/003-learn-exercise-rounds/
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
    srs.py                 REVIEW_ROUNDS → EXERCISE_ROUNDS (порядок один на два режима);
                           _graduate → публичная graduate();
                           LEARNING_STEPS (кортеж типов) → RELEARN_STEPS (число);
                           − exercise_for()
    exercises.py           без изменений: build_exercise(attempt=…) уже пересобирает
                           карточку для повтора
    study_service.py       build_session: session_id выдаётся и в режиме learn;
                           + build_rounds(word_ids) — план раундов по готовому списку;
                           answer_exercise: learn-ветка удаляется, оба режима только
                           проверяют и пишут в журнал; − _next_exercise();
                           select_word: «Изучить» просто заводит прогресс, без apply_answer;
                           finish_review_session → finish_session(…, mode)
    schemas.py             ReviewRound → ExerciseRound;
                           ReviewFinishRequest/Result → SessionFinishRequest/Result (+ mode);
                           SelectResponse: − next_exercise;
                           AnswerRequest: session_id обязателен в обоих режимах
    routers/study.py       + POST /study/rounds;
                           POST /study/review/finish → POST /study/finish
  tests/
    test_srs.py            EXERCISE_ROUNDS, graduate(), RELEARN_STEPS; − тесты exercise_for
    test_api.py            план раундов изучения, ответы learn не двигают расписание,
                           finish в режиме learn выпускает слово несмотря на ошибки
    test_exercises.py      без изменений

frontend/
  src/
    api/types.ts           ExerciseRound, SessionFinishResult, SelectResponse без
                           next_exercise, AnswerPayload.session_id обязателен
    api/client.ts          + buildRounds(wordIds); finishReview → finishSession(id, mode)
    components/
      RoundsRunner.tsx     новый: раннер раундов, вынесенный из ReviewSession —
                           общий для «Изучения» и «Повторения»
      ReviewSession.tsx    удаляется: повторение рендерит RoundsRunner напрямую
      StudySession.tsx     раннер изучения: фаза знакомства → запрос раундов → RoundsRunner
      exercises/ExerciseView.tsx, Feedback.tsx, IntroCard.tsx   без изменений
    pages/StudyPage.tsx    review → RoundsRunner, learn → StudySession

README.md                  разделы «Два вида занятия», «Знакомство», «API»
```

**Structure Decision**: используется существующее разделение `backend/` + `frontend/`
из корня репозитория. Новых каталогов и пакетов не заводится: общий раннер раундов
встаёт рядом с существующими компонентами в `frontend/src/components/`, серверная
логика — в уже существующих `srs.py` / `study_service.py` / `routers/study.py`.

## Complexity Tracking

> Отступлений от конституции нет — таблица не заполняется.
