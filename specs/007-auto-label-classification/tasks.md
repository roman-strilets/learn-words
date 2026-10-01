---
description: "Task list for feature implementation"
---

# Tasks: Автоматическая разметка слов по меткам

**Input**: Design documents from `/specs/007-auto-label-classification/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md),
[quickstart.md](./quickstart.md)

**Tests**: обязательны. По принципу III конституции изменение контракта API ДОЛЖНО
сопровождаться тестом в `backend/tests/`; тесты не ходят в сеть — классификатор
подменяется фейком (`app.dependency_overrides`), HTTP SDK — `httpx2.MockTransport`
(research R11). На фронте тест-раннера нет: фронтовые задачи проверяются `yarn
typecheck`, `yarn build` и ручными сценариями [quickstart.md](./quickstart.md).

**Organization**: задачи сгруппированы по пользовательским историям. Каждая история
заканчивается зелёными воротами и может уйти отдельным коммитом: изменение контракта
API меняет в одном коммите `schemas.py`, роутер, тест, `types.ts` и README.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (другой файл, нет зависимостей)
- **[Story]**: к какой истории относится задача (US1, US2, US3)
- В описании указан точный путь к файлу

## Path Conventions

Веб-приложение: `backend/app/`, `backend/tests/`, `backend/alembic/versions/`,
`frontend/src/`. Новые файлы: `backend/app/word_filters.py`,
`backend/app/classifier.py`, `backend/tests/test_classifier.py`, миграция
`backend/alembic/versions/<rev>_label_description.py`,
`frontend/src/components/AutoLabelPanel.tsx`,
`frontend/src/components/ClassifierSection.tsx`.

---

## Phase 1: Setup

**Purpose**: чистое окружение, зелёные ворота, зависимость SDK в lock-файле

- [X] T001 Убедиться, что в `git status` нет незакоммиченных правок, кроме `specs/007-auto-label-classification/`. Выполнить `uv sync --directory backend`: в `backend/.venv` при исследовании вручную поставили `typesafe-sdk` и `tenacity` мимо `uv.lock`, синхронизация вернёт окружение к lock-файлу. Прогнать из корня `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests` и зафиксировать, что всё зелёное
- [X] T002 Добавить зависимость: `uv add --directory backend typesafe-sdk` (меняет `backend/pyproject.toml` и `backend/uv.lock`; транзитивно приходит `tenacity`). Проверить импорт: `uv run --directory backend python -c "from typesafe_sdk import Choice, TypeSafeClient, TypeSafeError, TypeSafeAPIError, TypeSafeAPIConnectionError, TypeSafeAPITimeoutError, TypeSafeNotFoundError, TypeSafeAuthenticationError, TypeSafePermissionDeniedError, TypeSafeAPIResponseValidationError"` и найти публичный путь импорта `RetryPolicy` (определён в `typesafe_sdk/_core/retry.py`; если он не экспортирован из `typesafe_sdk`, импортировать из ближайшего публичного модуля и записать это комментарием в `classifier.py` в T009)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: параметры, колонка описания, общий отбор слов и модуль классификатора. На
этом стоят все три истории: US1 и US2 размечают через `classifier.py` и
`word_filters.py`, US3 проверяет подключение тем же адаптером и правит описание,
которое адаптер уже передаёт модели.

**⚠️ CRITICAL**: без этой фазы истории не начать

- [X] T003 В `backend/app/config.py` в класс `Settings` добавить блок «Классификатор меток» с комментариями «почему» (data-model, «Параметры в `app/config.py`»): `classifier_base_url: str = "http://localhost:11434"`, `classifier_api_key: str = "ollama"`, `classifier_model: str = "nimble"` (значения по умолчанию; действующие лежат в таблице `settings` и меняются из интерфейса), `classifier_timeout_seconds: float = 120.0` (предел одной пачки, как в примере пользователя), `classifier_check_timeout_seconds: float = 15.0` (проверка подключения не должна висеть две минуты), `classifier_batch_max: int = 100` (больше — одна пачка не укладывается в таймаут на локальной модели)
- [X] T004 В `backend/app/models.py` в модель `Label` добавить `description: Mapped[str | None] = mapped_column(String(200), nullable=True)` с комментарием: необязательное пояснение темы, классификатор берёт его критерием вместо названия (research R8, R9). Дополнить докстринг `Label`
- [X] T005 Создать миграцию `backend/alembic/versions/<rev>_label_description.py` (`uv run --directory backend alembic revision -m "label description"`, `down_revision = '8735d2f5c996'`). `upgrade`: `op.add_column('labels', sa.Column('description', sa.String(200), nullable=True))`. `downgrade`: `op.drop_column('labels', 'description')`. Докстринг модуля по образцу `db05d4083721_word_priority.py`: что добавляется и зачем (описание метки — критерий для автоматической разметки), что таблица не пересоздаётся и внешние ключи `word_labels` не уезжают, что `downgrade` теряет только описания. Проверить `alembic upgrade head` и `alembic downgrade -1` на копии `backend/data/*.db`
- [X] T006 Создать `backend/app/word_filters.py` с докстрингом (отбор слов «Словаря» общий для списка и разметки, чтобы «Без меток» + «Изучается» значили одно и то же, research R3): перенести из `list_words` в `backend/app/routers/words.py` построение запроса в функцию `filtered_words(*, search: str | None, status: str | None, priority: bool | None, label: str | None, from_id: int | None = None) -> Select` — `select(Word).outerjoin(Progress, …)` с теми же условиями поиска, статуса, «Учить первым» и метки, плюс `Word.id >= from_id`, если `from_id` задан. Неизвестный статус и нечисловая метка — исключение `WordFilterError(ValueError)` с прежними текстами «Неизвестный статус» / «Неизвестная метка» (HTTP-код выбирает роутер)
- [X] T007 В `backend/app/routers/words.py` `list_words` вызывает `filtered_words(...)` и переводит `WordFilterError` в `HTTPException(422, detail=str(err))`; сортировка `order_by(Word.id)`, `total`, `limit/offset` — без изменений. Чистый рефакторинг: существующие тесты `backend/tests/test_api.py` на фильтры остаются зелёными без правок
- [X] T008 [P] Создать `backend/tests/test_classifier.py` — тесты пишутся первыми и падают (quickstart, первые четыре строки таблицы):
  - `build_questions` (`parametrize`): ключ вопроса — `str(word.id)`; в `instructions` есть слово и перевод; в `criteria` все метки набора (`description` вместо названия, если задано) и вариант «ни одна»; два значения одного слова — два вопроса; метка «None of the above» — ключ «ни одна» получает суффикс ` (2)`;
  - `parse_choices` (`parametrize`): название метки → её id; ключ «ни одна», ответ вне набора, отсутствующий ключ вопроса → `None`;
  - `TypeSafeClassifier` с `transport=httpx2.MockTransport(handler)`: запрос уходит `POST {base_url}/v1/systemone` с переданными моделью и `Authorization: Bearer <key>`, ответ разбирается в `{word_id: label_id | None}`; handler вызывается ровно один раз (повторов нет); 404 → `ClassifierError(502, «Модель «…» не найдена»)`, 401 → 502 «Сервис отклонил ключ доступа», `httpx2.ConnectError` → 502 «Сервис разметки недоступен по адресу …», `httpx2.ReadTimeout` → 504. Формат тела ответа — взять из `SystemOneResponse` SDK (`typesafe_sdk/_core/response_types.py`, `ChoiceAnswer` в `_schemas/models.py`)
- [X] T009 Создать `backend/app/classifier.py` с докстрингом (зачем модель, почему вызов изолирован от сервиса и как тесты его подменяют) — research R1, R6, R7, R8:
  - `@dataclass(frozen=True)` `WordItem(id, word, translation)`, `LabelItem(id, name, description)`, `ClassifierConfig(base_url, api_key, model)`;
  - `NONE_CHOICE = "none of the above"` и `none_key(labels)` — с суффиксом ` (2)`, ` (3)`…, если ключ совпал с названием метки без учёта регистра;
  - `build_questions(words, labels) -> dict[str, Choice]` и `parse_choices(choices, words, labels) -> dict[int, int | None]` — чистые функции; `instructions` по-английски: `Which category does the English word "{word}" (Russian translation: "{translation}") belong to? Choose "{none}" if none of the categories fits.`;
  - `class ClassifierError(Exception)` с `status_code` (502 | 504) и `detail`; `translate_error(exc, config) -> ClassifierError` по таблице R6, от частного к общему (`TypeSafeAPITimeoutError` раньше `TypeSafeAPIConnectionError`);
  - `class Classifier(Protocol)`: `classify(words: list[WordItem], labels: list[LabelItem]) -> dict[int, int | None]` и `check() -> None`;
  - `class TypeSafeClassifier`: принимает `ClassifierConfig`, `timeout: float`, `transport: httpx2.BaseTransport | None = None`; создаёт `TypeSafeClient(base_url=…, api_key=…, model=…, timeout=…, retry=RetryPolicy(max_retries=0), transport=…)` в `with`; `classify` — один `system_one(state={"words": [...]}, questions=build_questions(...))`; `check` — один вопрос `Choice` про `apple` с критериями `fruit` / `tool`; любое `TypeSafeError` → `raise translate_error(...)`. Комментарий: значения передаются явно, поэтому переменные `TYPESAFE_*` окружения их не перебивают; повторы выключены, чтобы две минуты ожидания не стали шестью;
  - чтение настроек: ключи `CLASSIFIER_BASE_URL_KEY = "classifier_base_url"` и т. д.; `load_classifier_config(session) -> tuple[ClassifierConfig, bool]` — значения из таблицы `settings`, недостающие из `app.config.settings`; второй элемент — `is_default` (ни одной строки нет);
  - зависимости FastAPI: `get_classifier_factory() -> Callable[[ClassifierConfig, float], Classifier]` (по умолчанию `TypeSafeClassifier`) и `get_classifier(session=Depends(get_session), factory=Depends(get_classifier_factory)) -> Classifier` — фабрика с сохранённой конфигурацией и `classifier_timeout_seconds`
- [X] T010 Прогнать `uv run --directory backend pytest -q tests/test_classifier.py` (зелёный), затем все ворота из T001

**Checkpoint**: колонка описания есть, отбор слов общий, классификатор вызывается и
проверяется без сети — истории можно начинать

---

## Phase 3: User Story 1 — Разложить словарь по меткам одной кнопкой (Priority: P1) 🎯 MVP

**Goal**: кнопка «Разметить автоматически» на «Словаре» проходит пачками по 20 все
слова под текущими фильтрами и ставит каждому самую подходящую метку из всех меток
или ничего; прежние метки не снимаются, прогресс не трогается.

**Independent Test**: метки «кухня», «тело», «растения»; слова `spoon`, `elbow`, `oak`,
`kettle`, `knee`, `tulip`, `bicycle`, `democracy`. «Разметить автоматически» →
«Запустить»: шесть слов получили свои метки, `bicycle` и `democracy` — нет; сводка по
меткам верна; повторный запуск ничего не меняет.

### Tests for User Story 1 ⚠️

> Пишутся первыми и падают

- [X] T011 [US1] В `backend/tests/test_api.py` добавить фикстуру фейкового классификатора: класс с таблицей `{слово: название метки | None}`, записью полученных `words`/`labels` и необязательным исключением `ClassifierError` или колбэком «во время вызова» (для удаления слова или метки через `db_session`); подключается `app.dependency_overrides[get_classifier] = lambda: fake`. Тесты `POST /api/labels/classify` (quickstart, строки про разметку):
  - `spoon` → «кухня», `bicycle` → `None`: у `spoon` связка, у `bicycle` нет; в `results` `label` и `added` верные, порядок по `id`;
  - у слова уже «кухня» и «тело», фейк выбирает «кухня» → связки прежние, `added: false`, ни одна не снята (FR-004, SC-003);
  - фейк возвращает id метки вне `label_ids` → не ставится;
  - курсор: 12 слов из фикстуры `words`, `limit=5` → пачки 5/5/2, `next_from_id` последней `null`, `remaining` 7 → 2 → 0;
  - `ClassifierError(504)` → 504 с `detail`, ни одной новой связки; `ClassifierError(502)` → 502;
  - колбэк удаляет одно слово пачки → `skipped: 1`, остальные размечены; колбэк удаляет выбранную метку → не ставится, ответ 200;
  - `label_ids: []` → 422; только удалённые id → 422 «Нет меток для разметки»; `limit=0` и `limit=101` → 422; `status=bogus` → 422;
  - пустая выборка (`search` без совпадений) → 200, `results: []`, `next_from_id: null`, фейк не вызван;
  - после разметки число строк и содержимое `progress`, `review_log`, `words` прежние (FR-008, SC-004);
  - фейк получил описание метки в `LabelItem.description` (задать `label.description` прямо через `db_session`)

### Implementation for User Story 1

- [X] T012 [US1] В `backend/app/schemas.py` добавить (contracts/api.md, «Типы»): `ClassifyRequest` — `search`, `status`, `priority`, `label` как query у `GET /words`, `label_ids: list[int] = Field(min_length=1)`, `from_id: int | None = Field(default=None, ge=1)`, `limit: int` с валидатором `1 ≤ limit ≤ settings.classifier_batch_max`; `ClassifyResult` (`word_id`, `word`, `translation`, `label: LabelRef | None`, `added: bool`); `ClassifyBatch` (`results`, `skipped`, `next_from_id: int | None`, `remaining`). Докстринги по-русски: пачка — одна из цепочки независимых запросов, сервер не помнит этап (R4)
- [X] T013 [US1] В `backend/app/labels_service.py` добавить `class NoLabelsError(ValueError)` и `classify_batch(session, request: ClassifyRequest, classifier: Classifier) -> ClassifyBatch` по research R5:
  1. метки: `select(Label).where(Label.id.in_(request.label_ids))`; ни одной → `NoLabelsError("Нет меток для разметки")`;
  2. слова: `filtered_words(...)` (из T006) с `from_id`, `order_by(Word.id).limit(request.limit)`; пусто → `ClassifyBatch(results=[], skipped=0, next_from_id=None, remaining=0)` без вызова классификатора;
  3. собрать `WordItem`/`LabelItem`, затем `session.commit()` с комментарием: транзакция чтения не должна быть открыта, пока модель думает до двух минут, иначе запись после чужой записи упадёт `SQLITE_BUSY_SNAPSHOT` в WAL;
  4. `choices = classifier.classify(words, labels)` (исключения не ловить — их переводит роутер);
  5. заново загрузить слова и метки по id; удалённое слово → `skipped += 1`; выбранная метка удалена или не из набора → `label=None`; иначе, если связки нет, `word.labels.append(label)` и `added=True`;
  6. `next_from_id = last_word_id + 1`, если `filtered_words(..., from_id=next_from_id)` даёт хоть одну строку, иначе `None`; `remaining` — `COUNT` того же запроса.

  Комментарий у функции: метки только добавляются; `progress` и `review_log` не трогаются, это не ответ на упражнение (FR-008)
- [X] T014 [US1] В `backend/app/routers/labels.py` добавить `POST /classify` (`response_model=ClassifyBatch`, обычный `def` — FastAPI выполнит его в пуле потоков, долгий вызов модели не блокирует другие запросы): зависимости `get_session` и `get_classifier`; `WordFilterError` и `NoLabelsError` → 422 с `detail`; `ClassifierError` → `HTTPException(err.status_code, detail=err.detail)`. Проверить, что маршрут не конфликтует с `/{label_id}` (у того нет `POST`). Прогнать T011 — зелёный
- [X] T015 [P] [US1] В `frontend/src/api/types.ts` добавить `ClassifyFilters` (`search?`, `status?`, `priority?`, `label?: number | 'none'`), `ClassifyRequest`, `ClassifyResult`, `ClassifyBatch` в точном соответствии со схемами T012; в `frontend/src/api/client.ts` — `classifyBatch: (payload: ClassifyRequest) => request<ClassifyBatch>('/labels/classify', { method: 'POST', … })`
- [X] T016 [US1] Создать `frontend/src/components/AutoLabelPanel.tsx` (research R10): пропсы — текущие фильтры «Словаря» и `onClose`. Метки — из `useQuery(['labels'])`; если их нет — текст «Сначала заведите метки на вкладке «Метки»» со ссылкой на `/settings?tab=labels` и неактивное «Запустить» (FR-010). «Запустить» гоняет цикл пачек: `label_ids` — все метки, `limit = DEFAULT_BATCH_SIZE` (20, именованная константа с комментарием), `from_id` из ответа предыдущей пачки, пока `next_from_id !== null`. Состояние `idle | running | done | failed` (data-model, «Состояние запуска»). Во время работы — «обработано X из Y» (Y = обработано + `remaining`) и полоса; после каждой пачки `queryClient.invalidateQueries` для `['words']` и `['labels']`. Итог (FR-017, US1 сценарий 5): обработано, получили метку — по каждой метке, остались без новой метки, пропущено удалённых. Ошибка — `ApiError.detail` в панели, результаты прежних пачек уже на словах. Стили — как у соседних секций (`ui.tsx`, токены Tailwind проекта), тексты по-русски
- [X] T017 [US1] В `frontend/src/pages/WordsPage.tsx` добавить кнопку «Разметить автоматически» рядом с фильтрами; она показывает/скрывает `AutoLabelPanel` над списком и передаёт текущие `search`, `status`, `priorityOnly`, `label`
- [X] T018 [US1] README.md: в «Требования»/«Установка» — необязательная локальная Ollama с моделью `nimble` (без неё не работает только разметка); в «Словарь» — подраздел «Автоматическая разметка» (кнопка, одна метка на слово или ничего, прежние метки не снимаются, прогресс не меняется, пачки по 20); в «API» — `POST /api/labels/classify` и коды 502/504 (contracts/api.md)
- [X] T019 [US1] Ворота: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests`; ручные сценарии 1 и 6 из [quickstart.md](./quickstart.md) на живой модели

**Checkpoint**: одна кнопка размечает весь словарь — MVP готов

---

## Phase 4: User Story 2 — Разметка по этапам (Priority: P1)

**Goal**: пользователь сам режет работу: набор меток, лимит слов, «Начать с», размер
пачки, число слов в этапе до запуска, «Остановить» и «Продолжить с «…»», запоминание
между запусками.

**Independent Test**: «Без меток», «Не больше 40», пачка 10 → прогресс 10/20/30/40.
Остановить после второй: 20 слов размечены, показано «Продолжить с «…»».
Перезагрузить, открыть панель: предложено место остановки, пачка 10; «Продолжить»
обрабатывает оставшиеся.

### Tests for User Story 2 ⚠️

- [X] T020 [US2] В `backend/tests/test_api.py`: `GET /api/words?from_id=<id>` считает и отдаёт только записи с `id ≥ from_id`, складывается с `search`/`status`/`label`; `from_id=0` → 422. Разметка с `label=none`: фейк размечает все слова первой пачки — вторая пачка начинается ровно со следующего `id`, ни одно слово не пропущено и не обработано дважды (R4). Для `status`, `search`, `priority`, `label` (`parametrize`): разметка одной пачкой с `limit=100` (весь набор из фикстуры `words` влезает) обрабатывает ровно те `word_id`, что `GET /words` с теми же параметрами (R3)

### Implementation for User Story 2

- [X] T021 [US2] В `backend/app/routers/words.py` добавить `from_id: int | None = Query(default=None, ge=1, description="Только записи с id ≥ from_id — курсор разметки")` и передать в `filtered_words`. Прогнать T020 — зелёный
- [X] T022 [P] [US2] В `frontend/src/api/client.ts` `listWords` принимает `fromId?: number` и шлёт `from_id`
- [X] T023 [US2] В `frontend/src/components/AutoLabelPanel.tsx` добавить управление этапом (FR-012–FR-019, data-model «Этап разметки»):
  - чипы меток, все включены; выключенные не уходят в `label_ids`; метки, исчезнувшие из `['labels']` после инвалидации, выпадают из набора; ни одной включённой — «Запустить» неактивна;
  - «Не больше N слов» (пусто — вся выборка) и «Размер пачки» 1…100 (по умолчанию 20); последняя пачка получает `limit = min(batchSize, N − обработано)`;
  - «Начать с»: «с начала» / «с места остановки» (если есть `autoLabel.resume`) / «выбрать слово» — поле поиска по `api.listWords({ search, limit: 10 })` с выбором записи, её `id` становится `from_id`;
  - до запуска — «В этап попадёт N слов»: `api.listWords({ ...фильтры, fromId, limit: 1 }).total`, ограниченное лимитом; 0 — «Запустить» неактивна с объяснением;
  - «Остановить» → состояние `stopping` («Останавливается после текущей пачки…»), новая пачка не начинается → `stopped`; запрос не обрывается (R10);
  - `stopped` и `failed` показывают «Продолжить с «<слово>»»: слово берётся `api.listWords({ ...фильтры, fromId: next_from_id, limit: 1 }).items[0]`; кнопка запускает этап с этим `from_id`;
  - `useLocalStorage` (`frontend/src/hooks/useLocalStorage.ts`): `autoLabel.batchSize`, `autoLabel.limit`, `autoLabel.resume` (`{ from_id, word }`, пишется после каждой пачки, стирается при `done`); комментарий — удобство одного браузера, а не данные
- [X] T024 [US2] README.md: в «Автоматическая разметка» — этапы (набор меток, лимит, «Начать с», размер пачки, остановка и продолжение, порядок обхода — как в «Словаре»); в «API» — параметр `from_id` у `GET /api/words`
- [X] T025 [US2] Ворота (как T019); ручные сценарии 2 и 3 из [quickstart.md](./quickstart.md)

**Checkpoint**: разметку можно резать на этапы, останавливать и продолжать

---

## Phase 5: User Story 3 — Настройки подключения к классификатору (Priority: P2)

**Goal**: вкладка «Разметка» в «Настройках»: адрес, ключ, модель, «Сохранить»,
«Проверить подключение», «Сбросить»; описание метки на вкладке «Метки».

**Independent Test**: «Настройки» → «Разметка»: значения по умолчанию. Модель `nimbel`
→ «Проверить подключение» → «Модель «nimbel» не найдена». «Сбросить» → `nimble`,
проверка проходит. Перезагрузить — значения на месте. Метке «кухня» задать описание —
оно видно и уходит модели.

### Tests for User Story 3 ⚠️

- [X] T026 [US3] В `backend/tests/test_api.py` (quickstart, строки про настройки и описание):
  - `GET /api/settings/classifier` без строк → значения `config.py`, `is_default: true`; `PUT` → сохранены, `is_default: false`, `GET` их отдаёт; `DELETE` → снова по умолчанию, строк `classifier_*` в `settings` нет;
  - `PUT`: `ftp://x`, пустая модель, ключ с пробелом, адрес длиннее 512 → 422;
  - `POST /api/settings/classifier/check` с подменённой `get_classifier_factory`: фейк ок → `200 {ok: true}`; фейк бросает `ClassifierError(502, «Модель «nimbel» не найдена»)` → `200 {ok: false, detail: …}`; фабрика получила переданные (несохранённые) значения и `classifier_check_timeout_seconds`;
  - `load_classifier_config` берёт значения из `settings`, даже если `monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "other")`;
  - `POST /api/labels` с `description` → в ответе и в `GET /api/labels`; `PATCH {name}` не трогает описание; `PATCH {description: "  "}` → `null`; описание из 201 символа → 422; `PATCH {}` → 422

### Implementation for User Story 3

- [X] T027 [US3] В `backend/app/schemas.py`: `LABEL_DESCRIPTION_MAX = 200` с комментарием и тип `LabelDescription` (обрезка; пустая → `None`; длиннее — `ValueError`); `LabelOut.description: str | None`; `LabelInput.description: LabelDescription | None = None`; `LabelUpdate` (`name: LabelName | None = None`, `description: LabelDescription | None = None`, `model_validator` — хотя бы одно поле в `model_fields_set`); `ClassifierInput` (`base_url` — `http://` или `https://`, 1…512; `api_key` — 1…512 печатных ASCII без пробелов, как требует SDK; `model` — 1…128, обрезка), `ClassifierSettings(ClassifierInput)` с `is_default: bool`, `ClassifierCheck(ok: bool, detail: str)`
- [X] T028 [US3] В `backend/app/labels_service.py` `list_labels` отдаёт `description`; в `backend/app/routers/labels.py` `create_label` сохраняет `description`, `PATCH /{label_id}` принимает `LabelUpdate` и меняет только поля из `model_fields_set` (смена названия — прежняя проверка конфликта 409), ответы `LabelOut` с `description`
- [X] T029 [US3] В `backend/app/classifier.py` добавить `save_classifier_config(session, config)` (три строки `settings` одной транзакцией) и `reset_classifier_config(session)` (удаляет строки `classifier_*`; комментарий — удаление, а не запись значений по умолчанию, чтобы смена умолчаний в `config.py` доходила до пользователя). В `backend/app/routers/settings.py` — `GET`, `PUT`, `DELETE /classifier` (ответ `ClassifierSettings`) и `POST /classifier/check`: `factory(config, settings.classifier_check_timeout_seconds).check()`, `ClassifierError` → `ClassifierCheck(ok=False, detail=err.detail)`, успех → `ClassifierCheck(ok=True, detail="Модель отвечает")`. Прогнать T026 — зелёный
- [X] T030 [P] [US3] В `frontend/src/api/types.ts`: `Label.description: string | null`, `LabelUpdate`, `ClassifierInput`, `ClassifierSettings`, `ClassifierCheck`. В `frontend/src/api/client.ts`: `createLabel({ name, description })`, `updateLabel({ id, name?, description? })` вместо `renameLabel` (обновить вызовы в `frontend/src/components/LabelsSection.tsx`), `getClassifier`, `saveClassifier`, `resetClassifier`, `checkClassifier`
- [X] T031 [US3] Создать `frontend/src/components/ClassifierSection.tsx`: поля «Адрес сервиса», «Ключ доступа», «Модель» из `useQuery(['classifier'])`; «Сохранить» (`saveClassifier`, ошибка 422 — `detail` под формой, введённое остаётся); «Проверить подключение» — проверяет значения из полей, не сохраняя, показывает «Модель отвечает» или причину, во время проверки кнопка неактивна; «Сбросить» — `resetClassifier` и подстановка ответа в поля; подсказка, что ключ хранится в базе открытым текстом. Стили — как у `NewWordsOrderSection` в `frontend/src/pages/SettingsPage.tsx`
- [X] T032 [US3] В `frontend/src/pages/SettingsPage.tsx` добавить в `TABS` вкладку `{ value: 'classifier', label: 'Разметка' }`; вкладка читается из `?tab=classifier`, рендерит `ClassifierSection`
- [X] T033 [US3] В `frontend/src/components/LabelsSection.tsx`: необязательное поле «Описание для разметки» при создании метки и в режиме правки строки (вместе с переименованием, сохраняется `updateLabel`); в строке списка описание показано приглушённым текстом под названием; 422 — `detail` у поля
- [X] T034 [US3] README.md: «Настройки» — вкладка «Разметка» (поля, значения по умолчанию, проверка, сброс; ключ хранится в базе открытым текстом); «Метки» — описание для разметки; «API» — `GET/PUT/DELETE /api/settings/classifier`, `POST /api/settings/classifier/check`, `description` у меток и частичный `PATCH /api/labels/{id}`
- [X] T035 [US3] Ворота (как T019); ручные сценарии 4 и 5 из [quickstart.md](./quickstart.md)

**Checkpoint**: все три истории работают независимо

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T036 Пройти все ручные сценарии [quickstart.md](./quickstart.md) на живой Ollama подряд; для контрольного набора SC-002 записать в описание коммита, сколько из 16 слов размечено верно
- [X] T037 README.md, «Что не сделано»: несколько меток за один прогон, отмена прогона одной кнопкой, порог уверенности модели, разметка при добавлении слова и импорте
- [ ] T038 Только с согласия пользователя: поправка конституции отдельным коммитом `docs: amend constitution to v1.1.0 (external classifier key)` — в `.specify/memory/constitution.md` раздел «Технологический стек и ограничения», «Конфигурация»: ключ внешнего сервиса хранится в базе приложения, не в репозитории; Принцип V: внешний сервис допустим, если он необязателен и без него работает всё, кроме зависящей от него функции. Обновить Sync Impact Report и версию в подвале (plan.md, Complexity Tracking)
- [X] T039 Финальные ворота из T001 и самопроверка по вопросам ревью конституции: проверяет сервер; `srs.py` не тронут; тест на каждое новое поведение; миграция есть; README обновлён

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → US1 → US2 → US3 → Polish
- US2 опирается на `AutoLabelPanel` и маршрут разметки из US1: это та же панель с
  управлением этапом. Бэкенд US2 (T020–T021) от US1 не зависит и может идти сразу
  после Phase 2.
- US3 от US1/US2 не зависит: разметка с первого дня берёт значения по умолчанию
  через `load_classifier_config` (T009), а колонка описания есть с Phase 2.

### Within Each User Story

- Тесты (T011, T020, T026) пишутся первыми и падают
- Схемы → сервис → роутер → зелёные тесты → фронт (типы → клиент → компоненты →
  страница) → README → ворота
- `test_api.py`, `schemas.py`, `labels_service.py`, `routers/labels.py`,
  `classifier.py`, `AutoLabelPanel.tsx`, `client.ts` правятся несколькими историями —
  внутри истории последовательно

### Parallel Opportunities

- T008 (`test_classifier.py`) параллельно с T003–T007
- T015 (`types.ts`, `client.ts`) параллельно с бэкендом US1 (T012–T014): контракт
  зафиксирован в [contracts/api.md](./contracts/api.md)
- T022 (`client.ts`) параллельно с T020–T021
- T030 (`types.ts`, `client.ts`) параллельно с бэкендом US3 (T027–T029);
  `ClassifierSection.tsx` (T031) — новый файл, параллельно с T033
- Бэкенд US3 (T026–T029) можно делать параллельно с фронтом US1/US2 — разные файлы,
  кроме `test_api.py`

## Parallel Example: User Story 1

```text
# После T011 одновременно:
Task: "T012 [US1] ClassifyRequest/Result/Batch в backend/app/schemas.py"
Task: "T015 [US1] Типы и classifyBatch в frontend/src/api/types.ts и client.ts"
```

## Parallel Example: User Story 3

```text
# После T026 одновременно:
Task: "T027 [US3] Схемы описания и настроек в backend/app/schemas.py"
Task: "T030 [US3] Типы и методы клиента в frontend/src/api/types.ts и client.ts"
Task: "T031 [US3] ClassifierSection в frontend/src/components/ClassifierSection.tsx"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 и Phase 2
2. Phase 3 (US1) → ворота → коммит «Label the dictionary automatically» (вместе с
   Phase 1–2: зависимость, миграция, классификатор)
3. Остановиться и проверить: одна кнопка размечает словарь со значениями подключения
   по умолчанию; управлять этапом и менять модель ещё нельзя

### Incremental Delivery

1. Phase 1–2 + US1 → коммит с зависимостью, миграцией, тестами, README и типами
2. US2 → коммит «Let the user run auto-labelling in stages»
3. US3 → коммит «Configure the label classifier from the settings»
4. T037 входит в коммит последней истории; T038 — отдельный коммит поправки
   конституции, только по согласию пользователя
