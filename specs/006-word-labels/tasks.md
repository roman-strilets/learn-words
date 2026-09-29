---
description: "Task list for feature implementation"
---

# Tasks: Метки слов

**Input**: Design documents from `/specs/006-word-labels/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md),
[quickstart.md](./quickstart.md)

**Tests**: обязательны. По принципу III конституции изменение контракта API и импорта
ДОЛЖНО сопровождаться тестом в `backend/tests/`. На фронте тест-раннера нет, поэтому
фронтовые задачи проверяются через `yarn typecheck`, `yarn build` и ручные сценарии
[quickstart.md](./quickstart.md).

**Organization**: задачи сгруппированы по пользовательским историям. Каждая история
заканчивается зелёными воротами и может уйти отдельным коммитом: изменение контракта
API меняет в одном коммите `schemas.py`, роутер, тест, `types.ts` и README.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (другой файл, нет зависимостей)
- **[Story]**: к какой истории относится задача (US1, US2, US3)
- В описании указан точный путь к файлу

## Path Conventions

Веб-приложение: `backend/app/`, `backend/tests/`, `backend/alembic/versions/`,
`frontend/src/`. Новые файлы: `backend/app/labels_service.py`,
`backend/app/routers/labels.py`, миграция `backend/alembic/versions/<rev>_word_labels.py`,
`frontend/src/components/LabelPicker.tsx`, `frontend/src/components/LabelsSection.tsx`.

---

## Phase 1: Setup

**Purpose**: стартовать с чистого дерева и зелёных ворот

- [X] T001 Убедиться, что незакоммиченные правки фичи 005 (`git status`: `README.md`, `backend/app/*`, `frontend/src/*`, миграция `db05d4083721_word_priority.py`, `backend/app/routers/settings.py`) закоммичены отдельно или сознательно оставлены — миграция меток ставится поверх `db05d4083721`. Затем прогнать из корня `yarn test:api`, `yarn typecheck`, `yarn build` и `uv run --directory backend ruff check app tests` и зафиксировать, что всё зелёное

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: таблицы меток, ORM, ключи названия, поле `labels` в ответе со словом и
список меток `GET /labels`. На этом стоят все три истории: US1 пишет связки и
подсказывает метки из списка, US2 фильтрует по связкам и берёт метки для выпадающего
списка, US3 управляет метками.

**⚠️ CRITICAL**: без этой фазы истории не начать

- [X] T002 В `backend/app/models.py`:
  - добавить таблицу-связку `word_labels = Table("word_labels", Base.metadata, Column("word_id", ForeignKey("words.id", ondelete="CASCADE"), primary_key=True), Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True), Index("ix_word_labels_label_id", "label_id"))` с комментарием: каскады дают FR-014/FR-015 без кода в сервисе, индекс по `label_id` — для фильтра и счётчика (research R1, R5);
  - добавить модель `Label` (`__tablename__ = "labels"`): `id`, `name: String(50)`, `name_key: String(50)` с уникальным индексом `ux_labels_name_key`, `created_at` с `default=utcnow`. Докстринг: метка существует независимо от слов; `name_key` считается в Python, потому что `lower()` SQLite не знает кириллицы (R2);
  - в `Word` добавить `labels: Mapped[list["Label"]] = relationship(secondary=word_labels, lazy="selectin", order_by=func.replace(Label.name_key, "ё", "е"))` — тот же порядок, что `label_sort_key` (R6). Обратного `Label.words` не заводить (data-model)
- [X] T003 Создать миграцию `backend/alembic/versions/<rev>_word_labels.py` (`uv run --directory backend alembic revision -m "word labels"`, `down_revision = 'db05d4083721'`). `upgrade`: `op.create_table('labels', …)`, `op.create_index('ux_labels_name_key', 'labels', ['name_key'], unique=True)`, `op.create_table('word_labels', …)` с двумя `ForeignKeyConstraint(..., ondelete='CASCADE')` и составным PK, `op.create_index('ix_word_labels_label_id', 'word_labels', ['label_id'])`. `downgrade`: удалить индексы и обе таблицы. В докстринге модуля, как в `db05d4083721_word_priority.py`: что добавляется и зачем, почему таблица `words` не пересоздаётся (внешние ключи `progress`/`review_log`), что `downgrade` теряет только разметку. Проверить `alembic upgrade head` и `alembic downgrade -1` на копии `backend/data/*.db`
- [X] T004 Создать `backend/app/labels_service.py` с докстрингом модуля (метки — ручная разметка словаря, к занятиям и расписанию отношения не имеют, поэтому живут не в `study_service.py`) и двумя функциями:
  - `label_key(name: str) -> str` — `name.strip().casefold()`, комментарий: регистронезависимость для кириллицы (R2);
  - `label_sort_key(key: str) -> str` — `key.replace("ё", "е")`, комментарий: без замены «ё» ушла бы в конец алфавита; в UTF-8 «а–п» (`D0 B0…BF`) идут перед «р–я» (`D1 80…8F`), поэтому побайтовое сравнение SQLite после той же замены даёт тот же порядок (R6)
- [X] T005 В `backend/app/schemas.py` в секции «слова»: константа `LABEL_NAME_MAX = 50` с комментарием «почему» (метка должна помещаться в строку словаря, R7); модели `LabelRef(BaseModel)` (`from_attributes=True`, поля `id: int`, `name: str`) и `LabelOut(BaseModel)` (поля `id`, `name`, `word_count: int`); поле `labels: list[LabelRef] = Field(default_factory=list)` в `WordOut`
- [X] T006 Добавить в `backend/tests/test_api.py` тест `GET /api/labels` (метки заводить через `db_session`, у двух из них — связки со словами фикстуры `words`): на чистой базе `[]`; с метками «бета», «Альфа», «ёлка», «ежевика», «ягода» — порядок «Альфа, бета, ежевика, ёлка, ягода», `word_count` верный, у метки без слов 0 (FR-009). Убедиться, что падает
- [X] T007 В `backend/app/labels_service.py` добавить `list_labels(session) -> list[LabelOut]` — один запрос `select(Label, func.count(word_labels.c.word_id)).outerjoin(word_labels, word_labels.c.label_id == Label.id).group_by(Label.id)`, сортировка в Python по `label_sort_key(label.name_key)`
- [X] T008 Создать `backend/app/routers/labels.py`: `router = APIRouter(prefix="/labels", tags=["labels"])` с одним маршрутом `GET ""` → `list_labels`. Подключить в `backend/app/main.py`: `app.include_router(labels.router, prefix="/api")`. Остальные маршруты добавит US3
- [X] T009 [P] В `frontend/src/api/types.ts` добавить `export interface LabelRef { id: number; name: string }`, поле `labels: LabelRef[]` в `Word` и `export interface Label { id: number; name: string; word_count: number }`, с комментариями в стиле файла; в `frontend/src/api/client.ts` — `listLabels: () => request<Label[]>('/labels')`
- [X] T010 Прогнать `yarn test:api` и `yarn typecheck`: T006 зелёный, старые тесты зелёные, у слов в ответах `labels: []`

**Checkpoint**: схема и список меток на месте, прежнее поведение не изменилось.
Отдельным коммитом фаза не уходит: `WordOut.labels` и `GET /labels` меняют контракт,
а README к ним приходит в US1 (конституция: `schemas.py`, роутер, тест, `types.ts` и
README — одним коммитом)

---

## Phase 3: User Story 1 — Навесить метки на слово (Priority: P1) 🎯 MVP

**Goal**: метки выбираются и создаются в форме добавления слова и в форме «Изменить»,
сохраняются вместе со словом одной транзакцией и видны в строке словаря.

**Independent Test**: «Изменить» у `knife`, добавить «кухня», создать «инструменты»,
сохранить; после перезагрузки в строке две метки. Снять «инструменты» и сохранить —
осталась «кухня».

### Tests for User Story 1 ⚠️

> Написать до реализации и убедиться, что падают

- [X] T011 [US1] Добавить в `backend/tests/test_api.py` тесты меток на слове (фикстура `words`):
  - (а) `POST /api/words` с `labels: ["Посуда", "кухня"]` → 201, в ответе обе метки по алфавиту («кухня», «Посуда») — сразу, а не только при следующем чтении; повторный `POST` другого слова с `["КУХНЯ"]` берёт существующую «кухня» (тот же `id`, прежнее написание) (FR-001, FR-004a);
  - (б) `POST /api/words`-дубль (409) с `labels: ["тест"]` → строки `Label` с `name_key="тест"` в `db_session` нет (FR-004a);
  - (в) `PATCH /api/words/{id}` без поля `labels` не меняет метки; с `[]` снимает все; с `["b", "a"]` заменяет набор и отдаёт его по алфавиту (FR-003a);
  - (г) `PATCH`, сводящий запись к уже заведённому значению (409), с `labels: ["новая"]` — метки слова прежние, метки «новая» нет (FR-003a);
  - (д) `labels: ["кухня", " КУХНЯ ", "кухня"]` → одна метка на слове (FR-002);
  - (е) параметризованный: `labels: [""]`, `["   "]`, `["x" * 51]` → 422 и в `POST`, и в `PATCH`;
  - (ж) у слова с прогрессом (взять в изучение через `POST /api/study/select`) правка меток не меняет `progress` (`ease`, `lapses`, `due_at`, `status`) и не добавляет строк `review_log` (FR-005, SC-004);
  - (з) `PUT /api/words/{id}/status` в `new` и в `known` не меняет метки слова;
  - (и) `DELETE /api/words/{id}` у слова с меткой: строк `word_labels` с его `word_id` нет, сама метка осталась (FR-015)
- [X] T012 [P] [US1] Добавить в `backend/tests/test_import.py` тест: импорт CSV, через `db_session` дать одной записи метку, импортировать тот же файл повторно — у записи метка на месте, число строк `Label` прежнее, у новых записей меток нет (FR-016)

### Implementation for User Story 1

- [X] T013 [US1] В `backend/app/schemas.py` добавить аннотированный тип названия метки: `LabelName = Annotated[str, AfterValidator(...)]` — обрезает пробелы, пустое → `ValueError("название метки не может быть пустым")`, длиннее `LABEL_NAME_MAX` → `ValueError`. Добавить `labels: list[LabelName] = Field(default_factory=list)` в `WordCreate` и `labels: list[LabelName] | None = None` в `WordUpdate` с комментарием: `None` — «не менять», `[]` — «снять все» (R3)
- [X] T014 [US1] В `backend/app/labels_service.py` добавить `resolve_labels(session, names: list[str]) -> list[Label]`: схлопнуть повторы по `label_key` (первое вхождение побеждает), одним `select(Label).where(Label.name_key.in_(keys))` найти существующие, недостающие создать `Label(name=..., name_key=...)` и `session.add`; вернуть **отсортированными по `label_sort_key`** с комментарием: присвоенный `word.labels` отдаётся в ответе как есть, а `order_by` у связи действует только при загрузке из базы — без сортировки ответ на `POST`/`PATCH` нарушал бы контракт. Докстринг: вызывается в транзакции сохранения слова, поэтому отклонённое сохранение новых меток не оставляет (FR-003a, FR-004a); совпадение по ключу берёт существующую метку с её написанием
- [X] T015 [US1] В `backend/app/routers/words.py`: в `create_word` после проверки дубля присвоить `word.labels = resolve_labels(session, payload.labels)`; в `update_word` после проверки `_same_meaning` — `if payload.labels is not None: word.labels = resolve_labels(session, payload.labels)`. Проверка дубля остаётся **до** разрешения меток. Убедиться, что поле `labels` из `WordCreate` не уходит в конструктор `Word`
- [X] T016 [US1] Прогнать `yarn test:api`: тесты T011 и T012 зелёные, старые тоже
- [X] T017 [P] [US1] В `frontend/src/api/types.ts` добавить `labels?: string[]` в `WordInput` с комментарием: названия, а не id — новые метки создаются вместе со словом; в правке отсутствие поля не меняет метки
- [X] T018 [US1] Создать `frontend/src/components/LabelPicker.tsx` — `LabelPicker({ value, onChange }: { value: string[]; onChange: (next: string[]) => void })`:
  - выбранные названия — чипы с кнопкой-крестиком (`aria-label` «Снять метку «…»»), обёртка `flex flex-wrap`, чтобы много меток переносились (Edge Cases);
  - текстовое поле; при непустом вводе под ним список: существующие метки из `useQuery({ queryKey: ['labels'], queryFn: api.listLabels })`, чьё название содержит ввод без учёта регистра (`toLocaleLowerCase`) и ещё не выбрано, затем — если нет точного совпадения ни с меткой, ни с выбранным — пункт «Создать метку «…»»;
  - Enter выбирает первый пункт (и не отправляет форму), Escape закрывает список, Backspace в пустом поле снимает последний чип;
  - выбор существующей добавляет её `name` (написание метки, а не ввода); повторно выбранное по `toLocaleLowerCase` не добавляется (FR-002);
  - ошибку загрузки меток не показывать отдельно: без подсказок поле всё равно даёт создать метку.
  Комментарий в начале: почему своё, а не `<datalist>` (чипы и пункт «Создать», R9)
- [X] T019 [US1] В `frontend/src/components/WordForm.tsx`: добавить `labels: string[]` в состояние формы (`valuesOf` берёт `word.labels.map((l) => l.name)`), поле `LabelPicker` с подписью «Метки» после «Перевода примера» (в двух колонках — `sm:col-span-2`), и `labels: form.labels` в `onSubmit`. Состояние формы при ошибке 409 не сбрасывается — это уже так, проверить
- [X] T020 [US1] В `frontend/src/pages/AddWordPage.tsx` и `frontend/src/pages/WordsPage.tsx` добавить инвалидацию `['labels']` в `onSuccess` добавления, правки и удаления слова (новые метки и счётчики, R11)
- [X] T021 [US1] В `frontend/src/pages/WordsPage.tsx` в ячейке слова (не в режиме правки) показать метки слова чипами только для чтения (`text-sm`, `flex flex-wrap gap-1`), без кнопок — менять их можно только в «Изменить» (FR-003, Q4). У слова без меток ничего не выводить
- [X] T022 [US1] Обновить `README.md`: новый подраздел «Метки» в «Как устроено обучение» (после «Словаря»): что такое метка, несколько меток на слове, выбор с подсказками и создание в форме добавления и в «Изменить», сохранение вместе со словом, отклонённая правка не создаёт меток, регистр не различается, метки не влияют на занятия и `review_log`. В «Словарь» — упомянуть метки в строке. В «API» — поле `labels` у слова (по алфавиту, «ё» = «е»), `labels` в `POST`/`PATCH /api/words` (названия, `None`/`[]`), 422 на пустое или длиннее 50, `GET /api/labels` со счётчиком. В «Что не сделано» — «Занятие по метке: учить и повторять только слова одной темы»
- [X] T023 [US1] Прогнать `yarn test:api`, `yarn typecheck`, `yarn build`, `ruff check`; пройти ручные сценарии 1–4 и 8 из [quickstart.md](./quickstart.md)

**Checkpoint**: US1 работает сама по себе и уходит коммитом вместе с Phase 2

---

## Phase 4: User Story 2 — Найти слова по метке (Priority: P1)

**Goal**: фильтр словаря по одной метке или «Без меток», в сочетании с поиском,
статусом и «Учить первыми».

**Independent Test**: дать «кухня» трём словам из двадцати, выбрать фильтр — ровно три
слова; добавить поиск — одно.

### Tests for User Story 2 ⚠️

> Написать до реализации и убедиться, что падают

- [X] T024 [US2] Добавить в `backend/tests/test_api.py` тесты фильтра (метки ставить через `POST`/`PATCH /api/words` или прямо через `db_session`):
  - (а) `GET /api/words?label=<id>` отдаёт ровно слова с меткой, `total` верный (FR-007);
  - (б) `?label=none` отдаёт только слова без меток;
  - (в) `?label=<id>&search=…`, `&status=new`, `&priority=true` — пересечение условий (FR-008);
  - (г) неизвестный `id` → 200, `total: 0`; `?label=abc` → 422;
  - (д) после снятия метки со слова через `PATCH` оно не попадает в `?label=<id>`

### Implementation for User Story 2

- [X] T025 [US2] В `backend/app/routers/words.py` в `list_words` добавить `label: str | None = Query(default=None, description="id метки или none — слова без меток")`. `none` → `.where(~exists().where(word_labels.c.word_id == Word.id))`; целое → `.where(exists().where(word_labels.c.word_id == Word.id, word_labels.c.label_id == int(label)))`; иное → `HTTPException(422, detail="Неизвестная метка")`. Комментарий: одно значение вместо пары параметров, чтобы нельзя было передать противоречие (R5, Q3)
- [X] T026 [US2] Прогнать `yarn test:api`: тесты T024 зелёные
- [X] T027 [US2] В `frontend/src/api/client.ts` добавить параметр `label?: number | 'none'` в `listWords`: при заданном — `query.set('label', String(params.label))`
- [X] T028 [US2] В `frontend/src/pages/WordsPage.tsx`: состояние `label: number | 'none' | ''` и `<select>` рядом со статусным фильтром с пунктами «Все метки», «Без меток» и метками из `useQuery({ queryKey: ['labels'], queryFn: api.listLabels })` (по порядку ответа); смена сбрасывает страницу на 0; `label` передаётся в `api.listWords` и в `queryKey`. Если выбранный `id` отсутствует в загруженном списке меток — сбросить на «Все метки» (Edge Cases, R11)
- [X] T029 [US2] Обновить `README.md`: в «Словарь» — фильтр по метке и «Без меток», сочетание с поиском и остальными фильтрами; в «API» — параметр `label` у `GET /api/words` (`id` | `none`, неизвестный `id` — пустая страница, иное — 422). Прогнать ворота; пройти ручной сценарий 5 из [quickstart.md](./quickstart.md)

**Checkpoint**: US1 и US2 работают вместе и по отдельности

---

## Phase 5: User Story 3 — Управлять списком меток (Priority: P2)

**Goal**: вкладка «Метки» в «Настройках»: список по алфавиту с числом слов, создание,
переименование, удаление с подтверждением.

**Independent Test**: создать «кухяня», дать двум словам, переименовать в «кухня» —
оба слова показывают «кухня»; удалить и подтвердить — меток у слов нет, слова и
прогресс на месте.

### Tests for User Story 3 ⚠️

> Написать до реализации и убедиться, что падают

- [X] T030 [US3] Добавить в `backend/tests/test_api.py` тесты изменения меток (список `GET /api/labels` уже покрыт T006):
  - (а) `POST /api/labels {name: " кухня "}` → 201, `name: "кухня"`, `word_count: 0`, метка появилась в `GET /api/labels`; повтор с «КУХНЯ» → 409 с `detail`; пустое и 51 символ → 422 (FR-010, FR-011);
  - (б) `PATCH /api/labels/{id}` → 200, новое название видно в `GET /api/words/{id}` у всех слов с меткой, их набор прежний (FR-012, SC-003); в название другой метки (другой регистр) → 409; «кухня» → «Кухня» у себя самой → 200; несуществующий `id` → 404;
  - (в) `DELETE /api/labels/{id}` → 204; метки нет в `GET /api/labels` и ни у одного слова; число строк `words`, `progress`, `review_log` прежнее (FR-014, SC-004); повтор → 404

### Implementation for User Story 3

- [X] T031 [US3] В `backend/app/schemas.py` добавить `LabelInput(BaseModel)` с полем `name: LabelName` (тип из T013; если US1 ещё не сделана — завести его здесь)
- [X] T032 [US3] В `backend/app/labels_service.py` добавить `find_by_key(session, key, *, exclude_id=None) -> Label | None` для проверки конфликта
- [X] T033 [US3] В `backend/app/routers/labels.py` добавить маршруты: `POST ""` (201) — конфликт по `find_by_key` → 409 `detail=f"Метка «{existing.name}» уже есть"`, иначе создать и вернуть `LabelOut(..., word_count=0)`; `PATCH "/{label_id}"` — 404 если нет, 409 если ключ занят **другой** меткой, иначе обновить `name` и `name_key`, вернуть `LabelOut` со счётчиком; `DELETE "/{label_id}"` (204) — 404 если нет, иначе `session.delete(label)` (связки уходят каскадом)
- [X] T034 [US3] Прогнать `yarn test:api`: тесты T030 зелёные, старые тоже
- [X] T035 [US3] В `frontend/src/api/client.ts` добавить `createLabel(name)` (`POST /labels`), `renameLabel({ id, name })` (`PATCH /labels/{id}`), `deleteLabel(id)` (`DELETE /labels/{id}`)
- [X] T036 [US3] Создать `frontend/src/components/LabelsSection.tsx`: заголовок «Метки», абзац-пояснение (метки ставятся в форме слова, здесь — общий список); форма «Новая метка» (поле + «Добавить», ошибка 409 через `ErrorBox`, введённое при ошибке остаётся); список меток из `['labels']` — название и «N слов» (склонение: 1 слово, 2 слова, 5 слов; если в `frontend/src/lib/format.ts` есть хелпер — использовать его, иначе добавить туда `pluralize`); у каждой «Переименовать» — разворачивает строку в поле с «Сохранить»/«Отмена», ошибка 409 остаётся в строке с введённым; «Удалить» — `window.confirm` с текстом «Удалить метку «…»? Она будет снята с N слов.» или «…Она не стоит ни на одном слове.» (FR-013). После каждой мутации инвалидировать `['labels']` и `['words']` (R11). Пустой список — строка «Меток пока нет»
- [X] T037 [US3] В `frontend/src/pages/SettingsPage.tsx` добавить вкладки «Общие» и «Метки»: активная берётся из `useSearchParams()` (`tab=labels`, иначе «Общие»), кнопки-вкладки с `role="tab"`/`aria-selected` под заголовком «Настройки». «Общие» — нынешние `NewWordsOrderSection` и «Голос озвучки» без изменений, «Метки» — `LabelsSection`. Комментарий: вкладка в адресе, а не в `localStorage`, — это навигация (R10)
- [X] T038 [US3] Обновить `README.md`: в «Метки» — управление на вкладке «Настройки → Метки», переименование, удаление с подтверждением, счётчик слов; в «API» — `POST/PATCH/DELETE /api/labels` с кодами 404/409/422 рядом с `GET /api/labels`; в «Настройки» — упомянуть вкладку. Прогнать ворота; пройти ручные сценарии 6–7 из [quickstart.md](./quickstart.md)

**Checkpoint**: все три истории работают вместе

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T039 Добавить в `backend/tests/test_api.py` тест SC-006: `GET /api/study/session?mode=learn` и `mode=review` отдают те же `id` слов до и после разметки части словаря
- [X] T040 Обновить счётчик тестов в разделе «Проверки» `README.md` (`pytest, N тестов`) по фактическому выводу `yarn test:api`
- [X] T041 Самопроверка по вопросам ревью из конституции: оценку делает сервер, `srs.py` и `study_service.py` не тронуты; на каждое правило из [data-model.md](./data-model.md) есть тест; миграция с докстрингом есть и откатывается; README, `schemas.py` и `types.ts` синхронны. Пройти [quickstart.md](./quickstart.md) целиком, включая сценарий 9

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → US1 → US2 → US3 → Polish
- После Phase 2 все три истории независимы: `GET /labels` уже есть, поэтому подсказки
  `LabelPicker` (US1) и выпадающий список фильтра (US2) работают без US3, а тесты US2 и
  US3 могут ставить метки прямо через `db_session`. Порядок историй — по приоритету.
- Тип `LabelName` (T013) заводит та история, что идёт первой из US1 и US3.

### Within Each User Story

- Тесты (T006 в основе; T011/T012, T024, T030) пишутся первыми и падают
- Схемы → сервис → роутер → зелёные тесты → фронт (типы → клиент → компоненты →
  страница) → README → ворота
- `test_api.py`, `schemas.py`, `labels_service.py`, `routers/words.py`,
  `WordsPage.tsx` правятся несколькими историями — внутри истории последовательно

### Parallel Opportunities

- T009 (`types.ts`, `client.ts`) параллельно с бэкендом Phase 2 (T002–T008)
- T012 (`test_import.py`) параллельно с T011 (`test_api.py`)
- T017 (`types.ts`) параллельно с бэкендом US1 (T013–T015)
- `LabelPicker.tsx` (T018) и `LabelsSection.tsx` (T036) — разные новые файлы, их можно
  писать одновременно: контракт зафиксирован в [contracts/api.md](./contracts/api.md)

## Parallel Example: User Story 1

```text
# После написания T011 одновременно:
Task: "T012 [US1] Тест импорта меток в backend/tests/test_import.py"
Task: "T017 [US1] WordInput.labels в frontend/src/api/types.ts"
Task: "T018 [US1] LabelPicker в frontend/src/components/LabelPicker.tsx"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 и Phase 2
2. Phase 3 (US1) → ворота → коммит «Let words carry labels» (вместе с Phase 2)
3. Остановиться и проверить: метки ставятся с подсказками, создаются и видны;
   переименовать и удалить их ещё нельзя, но и мусора нет — отклонённые правки меток
   не создают

### Incremental Delivery

1. Phase 2 + US1 → коммит с миграцией, тестами, README и типами
2. US2 → коммит «Filter the dictionary by label»
3. US3 → коммит «Manage labels from the settings»
4. Polish входит в коммит последней истории
