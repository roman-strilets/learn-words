---
description: "Task list for feature implementation"
---

# Tasks: Порядок изучения новых слов и поднятые слова

**Input**: Design documents from `/specs/005-new-words-order/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md),
[quickstart.md](./quickstart.md)

**Tests**: обязательны. По принципу III конституции изменение отбора слов, контракта API
и импорта ДОЛЖНО сопровождаться тестом в `backend/tests/`. На фронте тест-раннера нет,
поэтому фронтовые задачи проверяются через `yarn typecheck`, `yarn build` и ручные
сценарии [quickstart.md](./quickstart.md).

**Organization**: задачи сгруппированы по пользовательским историям. Каждая история
заканчивается зелёными воротами и может уйти отдельным коммитом: изменение контракта
API меняет в одном коммите `schemas.py`, роутер, тест, `types.ts` и README.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (другой файл, нет зависимостей)
- **[Story]**: к какой истории относится задача (US1, US2)
- В описании указан точный путь к файлу

## Path Conventions

Веб-приложение: `backend/app/`, `backend/tests/`, `backend/alembic/versions/`,
`frontend/src/`. Новые файлы: `backend/app/routers/settings.py` и миграция
`backend/alembic/versions/<rev>_word_priority.py`.

---

## Phase 1: Setup

**Purpose**: убедиться, что стартуем с зелёных ворот

- [X] T001 Прогнать из корня репозитория `yarn test:api`, `yarn typecheck`, `yarn build` и `uv run --directory backend ruff check app tests` и зафиксировать, что всё зелёное до начала правок

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: отбор новых слов получает параметр порядка. На нём стоят обе истории:
US1 выбирает направление, US2 добавляет перед ним ключ «поднятые первыми».

**⚠️ CRITICAL**: без этой фазы истории не начать

- [X] T002 Добавить в `backend/app/schemas.py`, в секцию «слова» или новую секцию «настройки», перечисление `class NewWordsOrder(StrEnum)` со значениями `OLDEST_FIRST = "oldest_first"` и `NEWEST_FIRST = "newest_first"`. В докстринге объяснить, что порядок касается только новых слов в «Изучении», а «Повторение» идёт по сроку (FR-013)
- [X] T003 В `backend/app/study_service.py` изменить `new_words_query(limit, exclude_ids=(), order=NewWordsOrder.OLDEST_FIRST)`: сортировка `Word.id.asc()` для `OLDEST_FIRST` и `Word.id.desc()` для `NEWEST_FIRST`. В докстринге объяснить, почему `id`, а не `created_at` (research R2: импорт ставит всем строкам один `now`, а `id` растёт в порядке вставки). Поведение по умолчанию не меняется, поэтому существующие тесты `backend/tests/test_api.py` остаются зелёными

**Checkpoint**: `yarn test:api` зелёный, поведение прежнее

---

## Phase 3: User Story 1 — Выбрать порядок изучения новых слов (Priority: P1) 🎯 MVP

**Goal**: на странице «Настройки» выбирается «В порядке добавления» или «Сначала недавно
добавленные»; «Изучение», замена после «Уже знаю» и `GET /study/new` отбирают новые слова
в выбранном порядке. Выбор хранится в базе.

**Independent Test**: выбрать «Сначала недавно добавленные» и начать «Учить слова»: на
знакомство приходят 5 последних добавленных слов, от нового к старому. Вернуть «В порядке
добавления»: приходят 5 самых старых, как раньше.

### Tests for User Story 1 ⚠️

> Написать до реализации и убедиться, что падают

- [X] T004 [US1] Добавить в `backend/tests/test_api.py` тесты настроек и порядка (фикстура `words` — 12 слов, `id` по порядку `VOCABULARY`):
  - (а) `GET /api/settings` на чистой базе отдаёт `{"new_words_order": "oldest_first"}` (FR-002);
  - (б) `PUT /api/settings` с `newest_first` отдаёт 200 и то же значение, следующий `GET` его возвращает (FR-003); `PUT` с `"random"` и с пустым телом → 422;
  - (в) параметризованный тест по `order`: после `PUT` `GET /api/study/session?mode=learn` отдаёт в `new_words` первые 5 `id` по возрастанию для `oldest_first` и последние 5 по убыванию для `newest_first` (FR-004, SC-001, SC-004);
  - (г) при `newest_first` `POST /api/study/select` с `action="know"` для первого слова и `exclude_ids` из показанных пяти возвращает `replacement` — шестое с конца слово (FR-004);
  - (д) `GET /api/study/new?limit=3` при `newest_first` отдаёт три последних слова;
  - (е) `GET /api/study/session?mode=review` отдаёт тех же слов в том же порядке сроков при обеих настройках (FR-013);
  - (ж) `PUT /api/settings` не добавляет строк в `review_log` (FR-014).

### Implementation for User Story 1

- [X] T005 [US1] Добавить в `backend/app/schemas.py` модель `AppSettings(BaseModel)` с полем `new_words_order: NewWordsOrder` (без значения по умолчанию, чтобы пустой `PUT` давал 422). В докстринге указать, что это настройки приложения из интерфейса, в отличие от параметров алгоритма в `app/config.py`
- [X] T006 [US1] В `backend/app/study_service.py` добавить константу ключа `NEW_WORDS_ORDER_KEY = "new_words_order"` и функции `get_new_words_order(session) -> NewWordsOrder` и `set_new_words_order(session, order) -> None` поверх модели `Setting`. Если строки нет или в ней неизвестное значение, `get_` возвращает `OLDEST_FIRST` (data-model: правка руками не должна ронять отбор). `set_` делает upsert через `session.get(Setting, key)` и `flush()`. Затем в `fetch_new_words` передать `get_new_words_order(session)` в `new_words_query`. Комментарий: настройка читается при каждом отборе, а не кешируется, потому что сервер stateless (Принцип I)
- [X] T007 [US1] Создать `backend/app/routers/settings.py`: `router = APIRouter(prefix="/settings", tags=["settings"])`, `GET ""` → `AppSettings(new_words_order=get_new_words_order(session))`, `PUT ""` принимает `AppSettings`, вызывает `set_new_words_order` и возвращает сохранённое. Подключить роутер в `backend/app/main.py` рядом с остальными: `app.include_router(settings_router.router, prefix="/api")`. Импортировать его под другим именем, потому что `settings` в `main.py` уже занято конфигом
- [X] T008 [US1] Прогнать `yarn test:api`: тесты T004 зелёные
- [X] T009 [P] [US1] В `frontend/src/api/types.ts` добавить `export type NewWordsOrder = 'oldest_first' | 'newest_first'` и `export interface AppSettings { new_words_order: NewWordsOrder }`, с комментарием в стиле файла
- [X] T010 [US1] В `frontend/src/api/client.ts` добавить `getSettings: () => request<AppSettings>('/settings')` и `updateSettings: (payload: AppSettings) => request<AppSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) })`
- [X] T011 [US1] В `frontend/src/pages/SettingsPage.tsx` добавить над «Голосом озвучки» секцию `<section>` с заголовком `<h2>` «Порядок новых слов» и двумя пунктами-кнопками в стиле `VoiceItem`: «В порядке добавления» (note: «сначала давно добавленные») и «Сначала недавно добавленные». Данные брать через `useQuery({ queryKey: ['settings'], queryFn: api.getSettings })`. Выбор сохранять сразу через `useMutation({ mutationFn: api.updateSettings })`, в `onSuccess` класть ответ в кеш `['settings']`, без кнопки «Сохранить». Пока идёт загрузка — `Spinner`, ошибку показать через `ErrorBox`. Абзац под заголовком: порядок действует со следующего занятия «Учить слова», на «Повторение» не влияет. Если `VoiceItem` переиспользуется, переименовать его в нейтральное имя (например, `OptionItem`) и поправить комментарий
- [X] T012 [US1] Обновить `README.md`: в «Как устроено обучение» → «Знакомство с новыми словами» (или новым подразделом рядом) описать выбор порядка и что замена после «Уже знаю» идёт тем же порядком; в «API» добавить строки `GET /api/settings` и `PUT /api/settings {new_words_order}` и абзац о значениях и умолчании; в «Настройки» отметить, что порядок новых слов меняется из интерфейса, а не через `backend/.env`
- [X] T013 [US1] Прогнать `yarn test:api`, `yarn typecheck`, `yarn build`, `ruff check`; пройти ручные сценарии 1–3 и 6 из [quickstart.md](./quickstart.md)

**Checkpoint**: US1 работает сама по себе и может уйти отдельным коммитом

---

## Phase 4: User Story 2 — Поднять выбранные слова в очереди (Priority: P2)

**Goal**: новое слово в «Словаре» отмечается «Учить первым»; поднятые слова идут в
«Изучение» раньше остальных, внутри групп — по порядку из US1. Отметка снимается, когда
слово уходит в изучение.

**Independent Test**: отметить три слова из середины словаря и начать «Учить слова»:
первые три слова знакомства — отмеченные, затем два по выбранному порядку. После
«Изучить» отметки у них нет.

### Tests for User Story 2 ⚠️

> Написать до реализации и убедиться, что падают

- [X] T014 [US2] Добавить в `backend/tests/test_api.py` тесты поднятия (фикстура `words`, 12 слов):
  - (а) `PUT /api/words/{id}/priority` с `true` отдаёт 200 и `priority: true`, повтор — тоже 200; с `false` снимает; у несуществующего слова → 404 (FR-007);
  - (б) параметризованный по `order` тест: поднять слова с индексами 6, 3 и 9, `GET /api/study/session?mode=learn` отдаёт первыми эти три `id`, отсортированные по выбранному порядку, затем два неподнятых по тому же порядку (FR-009, SC-002);
  - (в) при 7 поднятых занятие состоит из 5 поднятых (сценарий US2-3);
  - (г) `monkeypatch.setattr(settings, "daily_new_limit", 9)` (`from app.config import settings`), взять в изучение 7 первых слов через `POST /api/study/select` с `learn`, поднять 3 из оставшихся 5 — занятие отдаёт `min(5, 9 − 7) = 2` слова, оба поднятые: лимит не обойдён (FR-012);
  - (д) замена после «Уже знаю» — поднятое слово, если оно есть вне `exclude_ids`;
  - (е) `POST /api/study/select` с `learn` и с `know` для поднятого слова: в `GET /api/words/{id}` у него `priority: false` (FR-010);
  - (ж) `PUT /api/words/{id}/status` в `learning` для поднятого слова отдаёт `priority: false`; после возврата в `new` отметки нет (FR-010, edge case);
  - (з) у слова в изучении `PUT …/priority` с `true` → 409 с `detail`, с `false` → 200 (FR-008);
  - (и) `GET /api/words?priority=true` отдаёт только поднятые, `&search=` сужает дальше, `&status=new` сочетается (FR-011);
  - (к) ни `PUT …/priority`, ни снятие отметки не пишут в `review_log` (FR-014).
- [X] T015 [P] [US2] Добавить в `backend/tests/test_import.py` тест: импорт CSV, пометить одну запись `priority = True` через `db_session`, импортировать тот же файл повторно — у записи по-прежнему `priority is True`, у новых записей `False` (FR-015)

### Implementation for User Story 2

- [X] T016 [US2] В `backend/app/models.py` добавить в `Word` поле `priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())` (импорт `false` из `sqlalchemy`), с комментарием: отметка «Учить первым», бывает только у слова без прогресса и снимается при первом прогрессе
- [X] T017 [US2] Создать миграцию `backend/alembic/versions/<rev>_word_priority.py` (`uv run --directory backend alembic revision -m "word priority"`, `down_revision = 'b71c4d2e9f30'`). `upgrade`: `op.add_column('words', sa.Column('priority', sa.Boolean(), nullable=False, server_default=sa.false()))`. `downgrade`: `op.drop_column('words', 'priority')`. В докстринге модуля, как в `b71c4d2e9f30_review_log_session_id.py`, объяснить: что добавляется и зачем, почему `add_column`, а не `batch_alter_table` (внешние ключи `progress` и `review_log` на `words`), и что `downgrade` теряет только отметки. Проверить `alembic upgrade head` и `alembic downgrade -1` на копии базы
- [X] T018 [US2] В `backend/app/schemas.py` добавить поле `priority: bool` в `WordOut` и модель `WordPriorityUpdate(BaseModel)` с полем `priority: bool` и докстрингом (ручное действие со словарём, не ответ)
- [X] T019 [US2] В `backend/app/study_service.py`:
  - в `new_words_query` сортировать `Word.priority.desc()` перед `id` (research R4), обновить докстринг;
  - в `select_word` и `set_word_status`, в ветках, где создаётся `Progress`, ставить `word.priority = False` с комментарием «отметка живёт, пока слово новое» (research R5);
  - добавить `set_word_priority(session, word, priority) -> None`: при `priority=True` и `word.progress is not None` бросает `ValueError`, иначе присваивает и делает `flush()`
- [X] T020 [US2] В `backend/app/routers/words.py`:
  - добавить `PUT /{word_id}/priority` (`response_model=WordWithProgress`), который вызывает `set_word_priority` и превращает `ValueError` в `HTTPException(409, detail="Поднять можно только новое слово")`;
  - в `list_words` добавить `priority: bool | None = Query(default=None, description="Только слова с отметкой «Учить первым»")`: при `True` добавить `.where(Word.priority.is_(True))`
- [X] T021 [US2] Прогнать `yarn test:api`: тесты T014 и T015 зелёные, старые тоже
- [X] T022 [P] [US2] В `frontend/src/api/types.ts` добавить `priority: boolean` в `Word`
- [X] T023 [US2] В `frontend/src/api/client.ts` добавить `setWordPriority: ({ id, priority }: { id: number; priority: boolean }) => request<WordWithProgress>(\`/words/${id}/priority\`, { method: 'PUT', body: JSON.stringify({ priority }) })` и параметр `priority?: boolean` в `listWords`: при `true` ставить `query.set('priority', 'true')`
- [X] T024 [P] [US2] В `frontend/src/components/icons.tsx` добавить `ArrowUpIcon` по образцу `ChevronIcon` (`IconProps`, `stroke="currentColor"`, `aria-hidden`)
- [X] T025 [US2] В `frontend/src/pages/WordsPage.tsx`:
  - в ячейке слова рядом с кнопкой-динамиком для слов без `progress` добавить кнопку-переключатель с `ArrowUpIcon`, `aria-pressed={word.priority}`, `title`/`aria-label` «Учить первым» / «Не поднимать» и цветом `text-accent`, когда отметка стоит. По клику `priorityMutation.mutate({ id, priority: !word.priority })` через `useMutation({ mutationFn: api.setWordPriority, onSuccess: invalidate })`. У слов с прогрессом кнопки нет (FR-008);
  - добавить состояние `priorityOnly` и отдельную кнопку-фильтр «Учить первыми» после `FILTERS`, которая переключается независимо от статусного фильтра и сбрасывает страницу на 0. Передавать `priority: priorityOnly || undefined` в `api.listWords` и в `queryKey`;
  - добавить `priorityMutation.error` в `rowError`
- [X] T026 [US2] Обновить `README.md`: в «Словарь» добавить строку таблицы действий «Стрелка вверх — Учить первым: слово придёт в „Учить слова“ раньше остальных новых» и абзац о том, что отметка бывает только у новых слов и снимается, когда слово уходит в изучение; упомянуть фильтр. В «API» добавить `PUT /api/words/{id}/priority {priority}`, параметр `priority` у `GET /api/words`, поле `priority` у слова, 409 для слова не в статусе «Новое»; описать порядок отбора «сначала поднятые, внутри групп — `new_words_order`»
- [X] T027 [US2] Прогнать `yarn test:api`, `yarn typecheck`, `yarn build`, `ruff check`; пройти ручные сценарии 4–5 из [quickstart.md](./quickstart.md)

**Checkpoint**: US1 и US2 работают вместе и по отдельности

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T028 Обновить счётчик тестов в разделе «Проверки» `README.md` (`pytest, N тестов`) по фактическому выводу `yarn test:api`
- [X] T029 Самопроверка по вопросам ревью из конституции: оценку по-прежнему делает сервер; `srs.py` не тронут; на каждое изменение отбора и API есть тест; миграция с докстрингом есть и откатывается; README, `schemas.py` и `types.ts` синхронны. Пройти [quickstart.md](./quickstart.md) целиком

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → US1 → US2 → Polish
- US2 технически зависит только от Phase 2: сортировка по `priority` ставится перед
  направлением порядка и работает и с умолчанием `oldest_first`. Но тест T014 (б)
  параметризован по порядку и использует `PUT /api/settings` из US1, поэтому истории
  идут по приоритету. Если US2 делается первой, этот тест стоит свести к `oldest_first`.

### Within Each User Story

- Тесты (T004, T014/T015) пишутся первыми и падают
- Схемы → сервис → роутер → зелёные тесты → фронт (типы → клиент → страница) → README → ворота
- Все правки `study_service.py` в истории идут последовательно (один файл)

### Parallel Opportunities

- T009 (`types.ts`) можно делать параллельно с T005–T007: файлы разные, контракт
  зафиксирован в [contracts/api.md](./contracts/api.md)
- T015 (`test_import.py`) параллельно с T014 (`test_api.py`)
- T022 (`types.ts`) и T024 (`icons.tsx`) параллельно с бэкендом US2 (T016–T020)

## Parallel Example: User Story 2

```text
# После написания T014 одновременно:
Task: "T015 [US2] Тест импорта priority в backend/tests/test_import.py"
Task: "T022 [US2] Поле priority в frontend/src/api/types.ts"
Task: "T024 [US2] ArrowUpIcon в frontend/src/components/icons.tsx"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 и Phase 2
2. Phase 3 (US1) → ворота → коммит «Let the learner choose the order of new words»
3. Остановиться и проверить: основная просьба закрыта, миграции ещё нет

### Incremental Delivery

1. US1 → коммит с тестами, README и типами
2. US2 → отдельный коммит «Let the learner raise words to learn first» с миграцией,
   тестами, README и типами
3. Polish входит в коммит последней истории
