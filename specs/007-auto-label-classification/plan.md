# Implementation Plan: Автоматическая разметка слов по меткам

**Branch**: `007-auto-label-classification` | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-auto-label-classification/spec.md`

## Summary

Словарь размечается по меткам языковой моделью: каждому слову — самая подходящая метка
из выбранного набора или ничего.

**Модель.** Бэкенд вызывает `typesafe-sdk` (`TypeSafeClient.system_one`) — один запрос
на пачку, вопрос `Choice` на каждое слово: критерии — метки (описание или название) и
явный вариант «ни одна» (R1, R8). Адрес, ключ и модель передаются явно из таблицы
`settings`; значения по умолчанию `http://localhost:11434` / `ollama` / `nimble` — в
`config.py` (R2). Повторов нет, таймаут 120 с, ошибки модели — 502/504 с понятным
`detail` (R6).

**Этапы.** Сервер stateless: `POST /labels/classify` обрабатывает одну пачку — до
`limit` слов, подходящих под фильтры «Словаря», начиная с `from_id` — и отдаёт курсор
следующей (R4). Отбор — та же функция, что у `GET /words` (R3). Чтение и запись
разнесены по разные стороны вызова модели, пачка применяется целиком (R5). Этап ведёт
фронт: панель на «Словаре» с набором меток, лимитом, «Начать с», размером пачки,
прогрессом, «Остановить» и «Продолжить» (R10).

**Метки и настройки.** У метки появляется необязательное описание (миграция
`add_column`, частичный `PATCH /labels/{id}`, R9). Вкладка «Разметка» в «Настройках» —
адрес, ключ, модель, «Проверить подключение» одним крошечным вопросом модели, «Сбросить»
(R7).

Занятия, расписание, упражнения, импорт и `review_log` не меняются.

## Technical Context

**Language/Version**: Python 3.12+ (бэкенд), TypeScript / Node ≥ 22.12 (фронтенд)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic; React 19,
TanStack Query, react-router. Новая — `typesafe-sdk` 0.7.x (`uv add`), транзитивно
`tenacity`; `httpx2` и `pydantic` у бэкенда уже есть

**Storage**: SQLite. Одна миграция: `add_column labels.description` (без пересоздания
таблицы). Настройки классификатора — строки в существующей `settings`

**Testing**: pytest — `test_api.py` (маршруты с фейковым классификатором через
`get_classifier`), новый `test_classifier.py` (чистые функции таблично, адаптер с
`httpx2.MockTransport`); фронт — `yarn typecheck`, `yarn build` и ручные сценарии
[quickstart.md](./quickstart.md) на живой модели

**Target Platform**: локальный однопользовательский веб-стенд (`yarn dev`), браузер;
локальная Ollama — внешний необязательный сервис

**Project Type**: веб-приложение, бэкенд + фронтенд в одном репозитории

**Performance Goals**: пачка из 20 слов укладывается в 120 с на локальной 9B-модели
(4 слова — 12,6 с с загрузкой модели); прогресс обновляется после каждой пачки
(SC-006); подсчёт «попадёт N слов» — один `COUNT` по тем же фильтрам

**Constraints**: сервер stateless — курсор вместо серверной задачи (Принцип I); тесты
без сети (Принцип III); миграция без пересоздания `labels` (Принцип IV); транзакция
не держится открытой во время вызова модели (R5); контракт меняется синхронно в
`schemas.py`, роутерах, тестах, `types.ts` и README

**Scale/Scope**: бэкенд — `pyproject.toml`/`uv.lock`, `config.py`, `models.py`,
миграция, `schemas.py`, новые `word_filters.py` и `classifier.py`,
`labels_service.py`, `routers/words.py`, `routers/labels.py`, `routers/settings.py`;
фронт — `api/types.ts`, `api/client.ts`, новые `components/AutoLabelPanel.tsx` и
`components/ClassifierSection.tsx`, `components/LabelsSection.tsx`,
`pages/WordsPage.tsx`, `pages/SettingsPage.tsx`; тесты; README

## Constitution Check

*GATE: пройден до Phase 0 с двумя обоснованными отступлениями (Complexity Tracking),
перепроверен после Phase 1.*

| Принцип | Проверка | Итог |
|---|---|---|
| I. Сервер — источник правды | Какую метку поставить, решает сервер (модель + сопоставление ответа с набором), фронт только показывает и собирает ввод. Серверного состояния нет: этап — цепочка независимых запросов с курсором `from_id` (R4); прогресс и место остановки — на фронте. Разметка — ручное действие со словарём: `review_log`, `ease`, `lapses`, `progress` не трогает (FR-008, тест). | ✅ |
| II. Чистое ядро расписания | `srs.py`, `study_service.py`, `exercises.py` не меняются. Логика разметки — `classifier.py` (чистые `build_questions`/`parse_choices` + адаптер), отбор — `word_filters.py`; роутеры тонкие. Таймауты и предел пачки — именованные параметры `config.py` с комментарием «почему» (data-model). | ✅ |
| III. Поведение закрепляется тестами | Каждое правило контракта и data-model — тест (таблица в quickstart), чистые функции — `parametrize`. Сеть не нужна: фейк через `get_classifier` и `MockTransport`. `types.ts` меняется вместе с `schemas.py`. Качество модели (SC-002) — ручной сценарий, потому что зависит от внешней модели, а не от кода. | ✅ |
| IV. Схема и данные неприкосновенны | Миграция с докстрингом: только `add_column`, `downgrade` — прямой `drop_column` (теряются только описания). Разметка только добавляет связки, ни одной не снимает (FR-004); пачка атомарна (R5). Подтверждение не требуется: расписание не стирается, добавленная метка снимается в «Изменить». Импорт не меняется. | ✅ |
| V. Простота и объяснённые решения | Внешний сервис и новая зависимость — по прямой просьбе пользователя, не «на будущее» (Complexity Tracking). Без фоновых задач, очередей и порогов уверенности (R4, R8). Фронт — без новых библиотек. README в том же коммите: «Словарь» (разметка), «Метки» (описание), «Настройки» («Разметка»), «API» (новые маршруты, 502/504), установка Ollama как необязательная. | ⚠️ обосновано |
| Стек и ограничения | Новая зависимость через `uv add`. «Секретов в проекте нет»: ключ хранится в базе (`backend/data/*.db` не коммитится), значение по умолчанию — заглушка Ollama; см. Complexity Tracking и рекомендуемую поправку. Корневой `.env` не меняется. | ⚠️ обосновано |

**После Phase 1**: дизайн добавил одну колонку, три ключа в `settings`, два модуля и
пять новых маршрутов и три изменённых (`GET /words`, `POST` и `PATCH /labels`), без серверного состояния. Новых
отступлений сверх Complexity Tracking нет.

## Project Structure

### Documentation (this feature)

```text
specs/007-auto-label-classification/
├── plan.md              # этот файл
├── research.md          # Phase 0: R1–R12
├── data-model.md        # Phase 1: labels.description, ключи settings, курсор, состояние запуска
├── quickstart.md        # Phase 1: тесты и ручные сценарии
├── contracts/
│   └── api.md           # Phase 1: /labels/classify, /settings/classifier, description, from_id
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml, uv.lock          # + typesafe-sdk
├── alembic/versions/
│   └── <rev>_label_description.py   # add_column labels.description
├── app/
│   ├── config.py                    # classifier_base_url/api_key/model (умолчания),
│   │                                #   classifier_timeout_seconds, _check_timeout_seconds,
│   │                                #   classifier_batch_max
│   ├── models.py                    # Label.description
│   ├── schemas.py                   # LABEL_DESCRIPTION_MAX, LabelOut/LabelInput.description,
│   │                                #   LabelUpdate, ClassifyRequest/Result/Batch,
│   │                                #   ClassifierSettings/Input/Check
│   ├── word_filters.py              # filtered_words(): отбор, общий для /words и разметки
│   ├── classifier.py                # build_questions(), parse_choices(), TypeSafeClassifier,
│   │                                #   перевод исключений SDK в 502/504, get_classifier,
│   │                                #   чтение/запись настроек classifier_*
│   ├── labels_service.py            # classify_batch(): отбор → commit → модель → запись
│   └── routers/
│       ├── words.py                 # filtered_words(), параметр from_id
│       ├── labels.py                # description, частичный PATCH, POST /labels/classify
│       └── settings.py              # GET/PUT/DELETE /settings/classifier, POST …/check
└── tests/
    ├── test_api.py                  # разметка, курсор, гонки, настройки, описание, инварианты
    └── test_classifier.py           # build_questions/parse_choices, адаптер с MockTransport

frontend/
└── src/
    ├── api/
    │   ├── types.ts                 # Label.description, ClassifyRequest/Batch, ClassifierSettings
    │   └── client.ts                # classifyBatch, get/save/reset/checkClassifier,
    │                                #   updateLabel, listWords({fromId})
    ├── components/
    │   ├── AutoLabelPanel.tsx       # этап, цикл пачек, прогресс, остановка, сводка
    │   ├── ClassifierSection.tsx    # вкладка «Разметка»
    │   └── LabelsSection.tsx        # поле описания у метки
    └── pages/
        ├── WordsPage.tsx            # кнопка «Разметить автоматически», передача фильтров
        └── SettingsPage.tsx         # третья вкладка (?tab=classifier)

README.md                            # Словарь, Метки, Настройки, API, установка Ollama
```

**Structure Decision**: существующая структура «бэкенд + фронтенд».
`classify_batch` живёт в `labels_service.py`: это работа с метками слов, и сервис уже
владеет ключами и порядком меток. Вызов модели — отдельный `classifier.py`, чтобы
сервис зависел от интерфейса, а тесты подменяли его без сети. Отбор слов уходит из
роутера в `word_filters.py`, потому что теперь его вызывают два роутера. Панель
разметки — отдельный компонент: `WordsPage.tsx` уже 377 строк, а цикл пачек со своим
состоянием в нём бы потерялся.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Внешний сервис (языковая модель) и зависимость `typesafe-sdk` (Принцип V) | Классифицировать тысячи слов по произвольным меткам без модели нельзя; пользователь прямо назвал SDK и дал рабочий пример. Сервис необязателен: без него не работает только разметка | Ручная разметка — есть, и именно её долгость — причина задачи. Правила по ключевым словам — не различают значения и не понимают пользовательские метки |
| Ключ доступа хранится в базе (раздел «Конфигурация»: «появление секрета требует пересмотра») | Адрес, ключ и модель меняются из интерфейса без правки файлов (US3, SC-007); у облачного сервиса ключ настоящий | Ключ только в `backend/.env` — смена требует перезапуска и правки файла; хардкод — правки кода. Рекомендуется поправка конституции (MINOR): «ключ внешнего сервиса хранится в базе, не в репозитории; в README — предупреждение, что он лежит открытым текстом» |
