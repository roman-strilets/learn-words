---

description: "Task list for studying a group of words by label"
---

# Tasks: Занятие по группе слов

**Input**: Design documents from `/specs/010-label-group-study/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Обязательны по конституции (принцип III): новая схема, проверка ответов и
контракт API сопровождаются тестами в `backend/tests/`. Тесты каждой истории пишутся
первыми и должны падать до реализации. Существующие тесты не правятся — они
доказывают, что обычные занятия и статистика не изменились.

**Organization**: Phase 2 заводит таблицы, схемы, чистую логику круга и выносит
маршруты из `RoundsRunner`. Дальше — по истории на фазу: US1 само занятие по метке,
US2 изоляция от основного обучения, US3 круг по всей группе, US4 «Начать круг заново».

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (разные файлы, нет зависимостей)
- **[Story]**: история из spec.md (US1–US4)

## Path Conventions

- Бэкенд: `backend/app/`, `backend/tests/`, `backend/alembic/versions/`
- Фронтенд: `frontend/src/`
- Тексты интерфейса, докстринги и комментарии — на русском; идентификаторы и
  сообщения коммитов — на английском (конституция, «Стиль»)

---

## Phase 1: Setup

**Purpose**: поправка конституции под второй журнал и параметр порции.

- [X] T001 **Только после согласия пользователя** (plan.md, Complexity Tracking): amend `.specify/memory/constitution.md` in a separate commit `docs: amend constitution to v1.1.0 (per-session-kind answer logs)`. In principle I replace «Каждая попытка ДОЛЖНА попадать в `review_log`» with a rule that every attempt goes to the answer log of its kind of session (`review_log` — обычные занятия со словами, `phrase_review_log` — фразы, `group_review_log` — занятия по группе), statistics are built from these logs only, and a session kind must not write another kind's log. Bump version to 1.1.0, update `Last Amended` to 2026-10-16 and the Sync Impact Report at the top. Change nothing else in the file. If the user declines, skip this task and leave the deviation recorded in plan.md
- [X] T002 Add `group_words_per_session: int = 5` to `Settings` in `backend/app/config.py` right after the phrase session settings, with a Russian comment: the size of one portion of a group session, separate from the normal sessions, with no daily limit (FR-002, FR-007). Add `# GROUP_WORDS_PER_SESSION=5` next to the other session variables in `backend/.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: таблицы, схемы, чистая логика круга и раннер раундов, которому можно
передать маршруты. Пока нет ни одного маршрута `/api/group-study`, ни один
существующий тест не должен измениться.

**⚠️ CRITICAL**: ни одна история не начинается до конца этой фазы.

### Модели и миграция

- [X] T003 Add models to `backend/app/models.py` after `ReviewLog`, per data-model.md: `GroupCycleWord` (`group_cycle_words`: `label_id` FK → `labels.id` ondelete CASCADE, `cycle` Integer, `word_id` FK → `words.id` ondelete CASCADE — composite PK `(label_id, cycle, word_id)`; `position` Integer NOT NULL; `done_at` DateTime NULL; `done_session_id` String(36) NULL; index `ix_group_cycle_words_word_id` on `word_id`) and `GroupReviewLog` (`group_review_log`: `id` PK; `word_id` FK → `words.id` CASCADE NOT NULL indexed; `label_id` FK → `labels.id` ondelete SET NULL nullable; `exercise` String(24); `correct` Boolean; `answer` Text NULL; `used_hint` Boolean default False; `attempt` Integer default 1; `quality` Integer; `duration_ms` Integer NULL; `session_id` String(36) NOT NULL indexed; `created_at` DateTime default `utcnow` indexed). Russian docstrings: why a cycle is stored as one row per (label, cycle, word) (research R2), and why group answers have their own log with no schedule columns (R1). No relationships on `Word`/`Label` are needed
- [X] T004 Create Alembic migration `backend/alembic/versions/<rev>_group_study.py` with `down_revision = '31a578309216'` (check with `uv run --directory backend alembic heads`) that creates both tables with all FKs and indexes from T003 and touches no existing table. Docstring: what is added and why (занятие по группе не трогает основной прогресс и журнал). `downgrade` drops `group_review_log` and `group_cycle_words`
- [X] T005 [P] Extend `backend/tests/test_migrations.py`: after `alembic upgrade head` on a database with a word, its progress, a review_log row and a label link, assert `group_cycle_words` and `group_review_log` exist with the expected columns, the existing rows are intact, and `downgrade -1` removes only the two new tables (reuse the `alembic_db` fixture)

### Схемы и типы

- [X] T006 Add schemas to `backend/app/schemas.py` per contracts/api.md: `GroupOut` (`label_id`, `name`, `word_count`, `done`, `cycle`), `GroupSessionRequest` (`label_id`), `GroupSessionOut` (`label_id`, `name`, `session_id: str | None`, `rounds: list[ExerciseRound]`, `word_count`, `done`, `cycle`), `GroupAnswerRequest` (`word_id`, `label_id`, `session_id`, `exercise: ExerciseType` with a validator rejecting `intro` → 422, `answer`, `used_hint`, `attempt ≥ 1`, `duration_ms ≥ 0 | None`), `GroupAnswerResponse` (same fields as `AnswerResponse` except `progress`), `GroupFinishRequest` (`session_id`), `GroupFinishResult` (`word_id`, `mistakes`). Russian docstrings say what each one is for
- [X] T007 [P] Mirror T006 in `frontend/src/api/types.ts`: `GroupSummary`, `GroupSessionPayload`, `GroupAnswerPayload`, `GroupAnswerResponse`, `GroupFinishResult` with the same field names and nullability (принцип III: `types.ts` синхронен со `schemas.py`)

### Чистая логика круга

- [X] T008 [P] Write table tests `backend/tests/test_group_cycles.py` for `app/group_cycles.py` (they must fail first), using `random.Random(seed)` and plain ints as word ids: (a) no members → empty portion, no inserts; (b) no rows → cycle 1 created over all members, portion = first `n` by position; (c) 12 members, `n=5`: three consecutive plans with done marks applied between them give 5, 5, then 2 remainder + 3 from cycle 2, with no word twice in one portion and the 3 top-ups not among the 2 remainder words; (d) group of 3 with `n=5` → portion of 3, no top-up; (e) a finished cycle → next plan creates cycle `C+1` whose order differs from cycle `C` and, for ≥3 members, does not start with the last word of `C` (check over many seeds); (f) 2 members → the new cycle is the swapped order; (g) 1 member → each cycle is that word; (h) a member without a row is appended to the end of the current cycle (and of `C+1` when it exists) and not marked done; (i) rows of a word that left the group are ignored for the portion and for `done`, and count again if it rejoins; (j) the next cycle once created is reused unchanged by the following plan (no reshuffle on retry); (k) rows of cycles below the current one are reported for deletion; (l) `summary()` returns `word_count`, `done`, `cycle` per data-model.md «Правила», including `done == word_count` for a fully finished cycle and `cycle == 0` with no rows
- [X] T009 Create `backend/app/group_cycles.py` — pure, no SQLAlchemy, no clock (принцип II). Define a frozen dataclass `CycleEntry(word_id, cycle, position, done: bool)`, a frozen `PortionPlan(word_ids: list[int], inserts: list[CycleEntry], delete_below: int | None, cycle: int)`, `plan_portion(members: Sequence[int], entries: Sequence[CycleEntry], size: int, rng: random.Random) -> PortionPlan` implementing steps 1–7 of data-model.md «Переходы при сборке порции», and `summary(members, entries) -> tuple[int, int, int]` (`word_count`, `done`, `cycle`). New cycle orders use `exercises.order_round(members, previous, last, rng)` with `previous` = the previous cycle's order filtered to current members (research R3). Members appended to a cycle are shuffled among themselves with `rng`. Module docstring in Russian: what a cycle is, why the next cycle is fixed once chosen (FR-012a) and why rows of members who lost the label are kept (R5). Make T008 pass

### Раннер раундов

- [X] T010 Refactor `frontend/src/components/RoundsRunner.tsx` to take `api: RoundsApi` instead of `deck` + `mode`, where `RoundsApi = { answer(payload: RoundAnswer): Promise<RoundFeedback>; finish(sessionId: string): Promise<unknown> }`; `RoundAnswer` is the common part of the answer payload (`word_id`, `exercise`, `answer`, `used_hint`, `attempt`, `duration_ms`, `session_id`) and `RoundFeedback` is the common part of `AnswerResponse`/`GroupAnswerResponse` (`correct`, `word`, `translation`, `example`, `example_translation`, `next_exercise`). Export the types from the component file. Add an optional `finishErrorText` prop for the finish error message, defaulting to the current «Ответы занятия сохранены, но расписание слов ещё не пересчитано.». Keep all round rules, `isGone` handling and comments as they are
- [X] T011 Update callers to build the `api` from `deckApi(deck)` and the mode — `frontend/src/pages/StudyPage.tsx` (review) and `frontend/src/components/StudySession.tsx` (learn): `answer: (p) => client.answer({ ...p, mode })`, `finish: (id) => client.finishSession(id, mode)`. Memoize with `useMemo` so the runner does not see a new object on every render. Behaviour of normal sessions must not change; `yarn typecheck` passes

**Checkpoint**: `yarn test:api`, `yarn typecheck`, `yarn build` green; обычные занятия
работают как раньше.

---

## Phase 3: User Story 1 — Позаниматься словами одной метки (Priority: P1) 🎯 MVP

**Goal**: с главной выбрать метку и пройти порцию её слов пятью раундами без знакомства.

**Independent Test**: метка «кухня» у 3 слов из 20; «Учить группу» → «кухня»: первая
карточка — упражнение, во всех раундах только эти 3 слова, раундов пять.

### Tests for User Story 1

- [X] T012 [P] [US1] Write API tests in new `backend/tests/test_group_study_api.py` (they must fail first). Local helpers: `_label(client, name, word_ids)` creates a label via `POST /api/labels` and attaches it through `PATCH /api/words/{id}` with `labels`, `_session(client, label_id)`, `_answer(...)`, `_play(client, session)` answering every card correctly using the words' known answers (pattern of `_play` in `backend/tests/test_phrases_api.py`), `_finish(client, session_id)`. Cases: `GET /api/group-study/groups` lists all word labels alphabetically with `word_count` over any status and `done=0`, `cycle=0`, and no phrase labels; `POST /session` for a label of 3 words returns a `session_id`, five rounds in `EXERCISE_ROUNDS` order with exactly those 3 words in each and no `intro`; a label of 12 words gives 5 words; a label without words → `session_id` null and `rounds` empty; unknown label → 404; a new word (no progress) can be answered: 200 with `correct`, a wrong answer returns `repeat_in_session` and a rebuilt `next_exercise` of the same type; `exercise="intro"` → 422; answer for a word without this label → 409; unknown word → 404; every answer adds a row to `group_review_log` with the label and session id; `finish` after all rounds returns each word with its `mistakes`, and `GET /groups` then shows `done` = number of finished words; choice cards' options may include words outside the label (FR-004a: assert at least one distractor is not a member, with the 12-word dictionary fixture and a 3-word label)

### Implementation for User Story 1

- [X] T013 [US1] Create `backend/app/group_study_service.py` with: `members(session, label_id) -> list[int]` (word ids from `word_labels`, ascending); `_entries(session, label_id) -> list[CycleEntry]`; `list_groups(session) -> list[GroupOut]` (all `Label` rows in `labels_service` order, `summary()` per label, read-only); `build_group_session(session, label, now, rng=None) -> GroupSessionOut` — loads members and entries, calls `plan_portion(..., settings.group_words_per_session, rng)`, applies `inserts` as `GroupCycleWord` rows and deletes rows with `cycle < delete_below`, loads the portion's `Word`s in plan order and builds rounds with `study_service._rounds_for(session, words, rng, WORDS)`, returns `session_id = uuid4` only when there are words; `answer_group_exercise(session, word, label, request, now, rng=None) -> GroupAnswerResponse` — 409-error class `WordNotInGroupError` when the word lacks the label, otherwise `check_answer`, `derive_quality`, rebuilt `build_exercise` on a wrong answer (same as `answer_exercise`, `show_letters=True`, `attempt + 1`), writes a `GroupReviewLog` row; never reads or creates `Progress`; `finish_group_session(session, session_id, now) -> list[GroupFinishResult]` per data-model.md «Переход при `finish`»: words with correct answers in all `EXERCISE_ROUNDS` get `done_at`/`done_session_id` on their earliest undone row of the log's `label_id`, skipped when a row with this `done_session_id` already exists (idempotent, research R6). Module docstring in Russian: the service never writes `progress` or `review_log` (FR-006) and why `session` writes cycle rows (research R7)
- [X] T014 [US1] Create `backend/app/routers/group_study.py` — thin router `APIRouter(prefix="/group-study", tags=["group-study"])` with `GET /groups`, `POST /session`, `POST /answer`, `POST /finish` per contracts/api.md, using `utcnow()`; 404 «Метка не найдена» / «Слово не найдено», 409 «Слова больше нет в группе». Include it in `backend/app/main.py` with `prefix="/api"` and a one-line Russian comment. Make T012 pass
- [X] T015 [P] [US1] Add `groupApi` to `frontend/src/api/client.ts`: `groups()`, `session(labelId)` (POST), `answer(payload)`, `finish(sessionId)`, plus a query key `['group-study', 'groups']`
- [X] T016 [US1] Create `frontend/src/pages/GroupStudyPage.tsx`. Without `?label=` in the URL: heading «Учить группу», list of groups from `groupApi.groups()` — name, «N слов · пройдено X из N» (`plural` from `lib/format`), button «Учить» linking to `/study/group?label=ID`, disabled with «нет слов» when `word_count` is 0; empty state with a link to `/settings?tab=labels` when there are no labels. With `?label=ID`: fetch `groupApi.session(id)` with the same query options as `StudyPage` (`staleTime: Infinity`, `refetchOnWindowFocus: false`, `gcTime: 0`); `session_id` null → «В группе нечего учить» and links back; otherwise render `RoundsRunner` with `api = { answer: (p) => groupApi.answer({ ...p, label_id }), finish: groupApi.finish }` and `finishErrorText` «Ответы сохранены, но круг группы ещё не отмечен.». After finish: «Сессия завершена», answers and accuracy like `StudyPage`, «пройдено X из N» from a refetched `groups()`, buttons «На главную» and «Следующая порция» (refetches the session, FR-005). Invalidate the groups query on finish. Unknown label (404) → `ErrorBox` and a link to the group list
- [X] T017 [US1] Register route `/study/group` → `GroupStudyPage` in `frontend/src/App.tsx` (before `/study` is fine: react-router matches exact paths), and add a third button «Учить группу» to the words block in `frontend/src/pages/HomePage.tsx` linking to `/study/group` (style of the review button, hint «по метке»); phrases block unchanged (FR-020)

**Checkpoint**: US1 работает сама по себе — главная → «Учить группу» → «Учить» →
пять раундов → итог.

---

## Phase 4: User Story 2 — Группа не трогает основное обучение (Priority: P1)

**Goal**: занятия по группе не меняют статусы, расписание, «Учить первым», лимит новых,
обычные занятия и статистику.

**Independent Test**: снимок прогресса, журнала, статистики и составов обычных занятий
до и после занятия по группе с ошибками совпадает.

### Tests for User Story 2

- [X] T018 [US2] Add isolation tests to `backend/tests/test_group_study_api.py`: a label over words in every status (new with `priority=True`, learning, review due in 10 days, review already due, known, suspended — set via `PUT /api/words/{id}/status` and `PUT /api/words/{id}/priority`); snapshot all `progress` rows (every column), `words.priority`, `review_log` count, `GET /api/stats/overview` and `GET /api/stats/daily`, and the word ids of `GET /api/study/session?mode=learn` and `?mode=review`; play two group portions with wrong answers and finish them; assert every snapshot is identical (FR-006, FR-008, FR-010, SC-002). Separate test: exhaust `daily_new_limit` (monkeypatch `settings.daily_new_limit` to 1 and start one new word via `/api/study/select`), then 20 consecutive group portions all return a `session_id` (FR-007, SC-005). Separate test: `GroupAnswerResponse` has no `progress` field

### Implementation for User Story 2

- [X] T019 [US2] Make T018 pass without touching `study_service.py`, `stats.py` or `srs.py`; if anything in `backend/app/group_study_service.py` reads `word.progress` or writes `Progress`/`ReviewLog`, remove it. Add a module-level Russian comment in `group_study_service.py` listing what the service never writes and pointing to the isolation test

**Checkpoint**: US1 + US2 — занятие по метке безопасно для основного прогресса.

---

## Phase 5: User Story 3 — Группа проходится по кругу в новом порядке (Priority: P1)

**Goal**: порции идут по всей группе без повторов, на стыке добираются из нового круга,
новый круг — в другом порядке; место в круге хранится на сервере для каждой метки.

**Independent Test**: 7 слов, порция 5: первое занятие — 5 слов, второе — 2 оставшихся
+ 3 из нового круга; порядок второго круга отличается от первого.

### Tests for User Story 3

- [X] T020 [US3] Add cycle tests through the API to `backend/tests/test_group_study_api.py`: 12 words, three played-and-finished portions give 5, 5, 2+3 with no word twice per cycle (track by `done`/`cycle` from `GET /groups`); after a full cycle the next portion starts cycle 2; an interrupted portion (some answers, no finish) → the next `POST /session` returns the same set of words; two labels keep independent cycles (a word in both labels, finished in one, is still undone in the other); repeating `finish` with the same `session_id` changes nothing and returns the same list; adding the label to a new word mid-cycle → `word_count + 1` and the word comes before the cycle ends; removing the label from a word → it no longer appears in portions and `word_count − 1`; answering for that removed word mid-session → 409; deleting a word or the label removes its `group_cycle_words` rows (FK cascade, check with `PRAGMA foreign_keys` enabled as in `app/db.py`); renaming the label keeps the cycle

### Implementation for User Story 3

- [X] T021 [US3] Make T020 pass in `backend/app/group_study_service.py`: membership sync and cycle cleanup must come only from `plan_portion` output (no extra logic in the router); confirm the test database enables `PRAGMA foreign_keys=ON` (see `app/db.py` and `tests/conftest.py`) and, if the test engine does not, enable it in the `db_session` fixture of `backend/tests/conftest.py` with a Russian comment, without changing other tests' behaviour
- [X] T022 [P] [US3] In `frontend/src/pages/GroupStudyPage.tsx` show the cycle on the group list and the result screen: «круг K · пройдено X из N»; when `done == word_count` add «следующее занятие начнёт новый круг»

**Checkpoint**: US1–US3 — полный круг по группе.

---

## Phase 6: User Story 4 — Начать круг группы заново (Priority: P3)

**Goal**: сбросить место в круге одной кнопкой, не трогая прогресс.

**Independent Test**: группа из 12 слов, пройдена одна порция; «Начать круг заново» →
«пройдено 0 из 12», следующая порция начинает новый круг.

### Tests for User Story 4

- [X] T023 [P] [US4] Add to `backend/tests/test_group_cycles.py`: `plan_restart(members, entries, rng)` creates cycle `max+1` whose order differs from the latest cycle (≥2 members), deletes all lower cycles, and returns nothing for an empty group. Add to `backend/tests/test_group_study_api.py`: `POST /api/group-study/groups/{id}/restart` → 204, `GET /groups` shows `done=0` and `cycle` + 1, progress snapshot unchanged; unknown label → 404; group without words → 204 and no rows

### Implementation for User Story 4

- [X] T024 [US4] Add `plan_restart(...) -> PortionPlan` (empty `word_ids`) to `backend/app/group_cycles.py`, `restart_group(session, label, rng=None)` to `backend/app/group_study_service.py`, and `POST /groups/{label_id}/restart` (204) to `backend/app/routers/group_study.py`. Make T023 pass
- [X] T025 [US4] Add `restart(labelId)` to `groupApi` in `frontend/src/api/client.ts` and a «Начать круг заново» button per group in `frontend/src/pages/GroupStudyPage.tsx` (secondary style, shown only when `done > 0`; no confirmation — progress is not erased, plan.md principle IV), invalidating the groups query on success

**Checkpoint**: все истории готовы.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T026 Update `README.md`: new section «Занятие по группе» under «Как устроено обучение» (выбор метки, без знакомства, пять раундов, порция `GROUP_WORDS_PER_SESSION`, без лимитов, круг и новый порядок, добор на стыке, прерванное занятие, изменение меток, «Начать круг заново», не влияет на статусы, расписание и «Статистику», варианты ответа из всего словаря, таблицы `group_cycle_words` и `group_review_log`); the five routes in «API» per contracts/api.md; `GROUP_WORDS_PER_SESSION` in «Настройки»; in «Что не сделано» replace «Занятие по метке: учить и повторять только слова одной темы» with «Повторение по расписанию только для слов одной метки» and add «Занятие по метке фраз» and «Статистика занятий по группе»
- [X] T027 Run `yarn test:api`, `uv run --directory backend ruff check app tests`, `yarn typecheck`, `yarn build` from the repo root (`package.json` scripts); fix anything that fails in `backend/` or `frontend/src/`
- [X] T028 Walk through the manual scenarios in `specs/010-label-group-study/quickstart.md` with `yarn dev` and note any deviation in the commit message or fix it
- [X] T029 Commit to `main` (no feature branch): one commit for the feature with an imperative English title (e.g. `Study the words of one label in rounds, apart from the schedule`) and a body explaining observation, reason and decision; the constitution amendment (T001), if approved, goes in its own earlier commit. Do not commit `backend/data/` (the database and `app.db.bak-*` files)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 needs user approval and is independent of the rest; T002 first
- **Foundational (Phase 2)**: after T002; blocks all stories
- **US1 (Phase 3)**: after Phase 2 — MVP
- **US2 (Phase 4)**: after US1 (tests play group sessions through US1 routes)
- **US3 (Phase 5)**: after US1; independent of US2
- **US4 (Phase 6)**: after US1; T023 extends the files from T008 and T012
- **Polish (Phase 7)**: after all stories

### Within Phase 2

- T003 → T004 → T005
- T006 → T007
- T008 → T009 (tests first)
- T010 → T011
- The four chains are independent of each other

### Within each story

- Tests first, failing, then implementation
- Service (T013) → router (T014); client (T015) → page (T016) → route and button (T017)

### Parallel Opportunities

- Phase 2: T005, T007, T008 and T010 touch different files and can run together once their predecessor is done
- US1: T012 (backend tests) and T015 (frontend client) in parallel; backend T013–T014 and frontend T016–T017 are separate tracks
- US3 and US2 can run in parallel after US1 (T018 and T020 both edit `test_group_study_api.py` — append in separate sections or do them sequentially)
- T022 (frontend) in parallel with T020–T021 (backend)

---

## Parallel Example: User Story 1

```bash
# Backend tests and the frontend client at the same time:
Task: "T012 [US1] API tests in backend/tests/test_group_study_api.py"
Task: "T015 [US1] groupApi in frontend/src/api/client.ts"

# Then two tracks:
Task: "T013 → T014 service and router (backend)"
Task: "T016 → T017 page, route, home button (frontend)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (T002; T001 only if approved)
2. Phase 2 — tables, schemas, pure cycle logic with tests, runner with an `api` prop
3. Phase 3 — US1: the group session from the home page
4. **STOP and VALIDATE**: quickstart scenarios 1–2

### Incremental Delivery

1. US1 → занятие по метке работает
2. US2 → доказанная изоляция от основного прогресса (тесты-снимки)
3. US3 → круг по всей группе, стык, разные метки, изменения состава
4. US4 → «Начать круг заново»
5. Polish → README, проверки, ручной проход, коммит

Конституция требует, чтобы README и тесты шли в том же коммите, что и поведение, —
поэтому история не коммитится отдельно без своего раздела README; при желании
коммитить по историям T026 разбивается на куски по историям.
