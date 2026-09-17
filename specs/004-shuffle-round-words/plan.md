# Implementation Plan: Случайный порядок слов в каждом раунде

**Branch**: `004-shuffle-round-words` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-shuffle-round-words/spec.md`

## Summary

Сейчас `study_service._rounds_for` собирает все четыре раунда по одному списку слов,
поэтому порядок слов во всех раундах одинаковый. Доработка перемешивает каждый раунд
отдельно.

**Сервер.** Новая чистая функция `order_round` в `app/exercises.py` выбирает случайный
порядок раунда. Порядок гарантированно отличается от предыдущего раунда, а если слов
три и больше, раунд не начинается со слова, которым закончился предыдущий. Гарантии
«всегда», а не «почти всегда», дают четыре кандидата-перестановки (R2).

**Фронт.** `RoundsRunner` на границе раунда применяет ту же поправку
(`frontend/src/lib/roundOrder.ts`) к тому, что действительно показал. Это нужно,
если раунд закончился повтором после ошибки или слово выбыло посреди занятия (R3).

Схема API, база, расписание и порядок знакомства не меняются.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript 5 / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Pydantic v2; React 19, TanStack Query.
Новых зависимостей нет: перемешивание через `random.Random`, переданный параметром

**Storage**: SQLite, без изменений схемы и без миграций

**Testing**: pytest (`backend/tests/test_exercises.py`, `backend/tests/test_api.py`);
фронт — `yarn typecheck`, `yarn build` и ручные сценарии [quickstart.md](./quickstart.md)

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), десктопный браузер

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: без изменений. Перестановка 5 элементов и до четырёх
кандидатов на раунд пренебрежимо малы по сравнению с выборкой дистракторов

**Constraints**: сервер stateless (Принцип I); `rng` передаётся параметром (Принцип II);
схема ответа API не меняется

**Scale/Scope**: бэкенд — `app/exercises.py` (новая функция), `app/study_service.py`
(`_rounds_for`); фронт — новый `lib/roundOrder.ts`, `components/RoundsRunner.tsx`;
тесты — `test_exercises.py`, `test_api.py`; README

## Constitution Check

*GATE: пройден до Phase 0, перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Ответы по-прежнему проверяет `exercises.py`, каждая попытка идёт в `review_log`. На сервере не появляется состояния: план собирается и отдаётся за один запрос. Фронт меняет только порядок показа в своей очереди, состав раунда не трогает. | ✅ |
| II. Чистое ядро расписания | `srs.py` не затрагивается. `order_round` — чистая функция без БД и времени, `rng` приходит параметром. «Магических чисел» нет: минимумы 2 и 3 слова следуют из FR-003 и FR-004 и называются в коде константами с комментарием. | ✅ |
| III. Поведение закрепляется тестами | Генерация плана меняется, поэтому нужны табличные тесты `order_round` и API-тесты плана (см. [quickstart.md](./quickstart.md)). Фронтовая поправка проходит через `typecheck` и `build`, алгоритм у неё тот же, что у покрытого тестами серверного. `types.ts` и `schemas.py` не меняются, рассинхрона нет. | ✅ |
| IV. Схема и данные неприкосновенны | Моделей и миграций не трогаем, расписание не меняется. | ✅ |
| V. Простота | Библиотек не добавляем, настройки «перемешивать» нет. README обновляется в том же коммите: раздел «Занятие идёт раундами» и описание `rounds` в «API». Решение «сервер + поправка на фронте» объясняется комментарием в `RoundsRunner`. | ✅ |

**После Phase 1**: артефакты дизайна не добавили ни состояния, ни зависимостей,
ни изменений схемы. Нарушений нет, Complexity Tracking не нужен.

## Project Structure

### Documentation (this feature)

```text
specs/004-shuffle-round-words/
├── plan.md              # этот файл
├── research.md          # Phase 0: R1–R5
├── data-model.md        # Phase 1: инварианты плана и состояние раннера
├── quickstart.md        # Phase 1: проверки и ручные сценарии
├── contracts/
│   └── study-api.md     # Phase 1: гарантии порядка в плане раундов
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── exercises.py         # + order_round(items, previous, last, rng, key)
│   └── study_service.py     # _rounds_for: порядок каждого раунда через order_round
└── tests/
    ├── test_exercises.py    # таблицы order_round, равномерность первого раунда
    └── test_api.py          # гарантии порядка в плане review и /study/rounds

frontend/
└── src/
    ├── lib/
    │   └── roundOrder.ts    # + arrangeRound(items, previous, lastWordId)
    └── components/
        └── RoundsRunner.tsx # roundOrder, lastWordId, поправка на границе раунда

README.md                    # раунды: порядок слов случайный; API: гарантии порядка
```

**Structure Decision**: существующая структура «бэкенд + фронтенд». Функция
порядка лежит в `exercises.py`: там уже живут прочие случайные решения о содержимом
карточек (`build_letter_bank`, выбор дистракторов), и они тестируются
в `test_exercises.py`. На фронте чистая функция вынесена в `lib/`, рядом с `format.ts`,
чтобы `RoundsRunner` остался про состояние занятия.

## Complexity Tracking

Нарушений Constitution Check нет.
