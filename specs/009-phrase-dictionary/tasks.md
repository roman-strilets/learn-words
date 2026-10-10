---

description: "Task list for the phrase dictionary"
---

# Tasks: Словарь фраз

**Input**: Design documents from `/specs/009-phrase-dictionary/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Обязательны по конституции (принцип III): новая схема, генерация упражнений,
проверка ответов и контракт API сопровождаются тестами в `backend/tests/`. Тесты
каждой истории пишутся первыми и должны падать до реализации. Существующие тесты
слов не правятся — они доказывают SC-003.

**Organization**: Phase 2 переводит общий код на описание колоды (`Deck`) и заводит
таблицы фраз. Дальше — по истории на фазу: US1 словарь и метки фраз, US2 «Учить
фразы», US3 «Повторить фразы», US4 особенности упражнений, US5 статистика.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (разные файлы, нет зависимостей)
- **[Story]**: история из spec.md (US1–US5)

## Path Conventions

- Бэкенд: `backend/app/`, `backend/tests/`, `backend/alembic/versions/`
- Фронтенд: `frontend/src/`

---

## Phase 1: Setup

**Purpose**: параметры колоды фраз в конфиге (принцип II — никаких магических чисел).

- [X] T001 Add `new_phrases_per_session: int = 5`, `review_phrases_per_session: int = 5`, `daily_new_phrases_limit: int = 20` to `Settings` in `backend/app/config.py`, next to the word session settings, with a Russian comment explaining that phrases count their own limits (FR-016). Add the three variables, commented out with defaults, to `backend/.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: таблицы фраз и общий код, параметризованный колодой. Пока ни одного
маршрута фраз нет, поведение слов не должно измениться ни в одном тесте.

**⚠️ CRITICAL**: ни одна история не начинается до конца этой фазы.

### Модели и миграция

- [X] T002 Add phrase models to `backend/app/models.py` per data-model.md: `phrase_label_links` table (`phrase_id` FK → `phrases.id` CASCADE, `label_id` FK → `phrase_labels.id` CASCADE, composite PK, index `ix_phrase_label_links_label_id`); `PhraseLabel` (`phrase_labels`: id, name String(50), name_key String(50), description String(200) NULL, created_at; unique index `ux_phrase_labels_name_key`); `Phrase` (`phrases`: id, text String(200), text_key String(200) indexed, translation Text, example, example_translation, created_at, priority Boolean server_default false; unique index `ux_phrases_text_key_translation`; relationships `progress` one-to-one `cascade="all, delete-orphan"` `lazy="selectin"` and `labels` via `phrase_label_links` ordered like `Word.labels`); `PhraseProgress` (`phrase_progress`, same columns as `Progress` with PK/FK `phrase_id` → `phrases.id` CASCADE, index `ix_phrase_progress_status_due_at`); `PhraseReviewLog` (`phrase_review_log`, same columns as `ReviewLog` with `phrase_id` FK CASCADE indexed). Add `sqlalchemy.orm.synonym` attributes so shared code and schemas work: `Phrase.word → text`, `Phrase.word_key → text_key`, `PhraseProgress.word_id → phrase_id`, `PhraseReviewLog.word_id → phrase_id`. Docstrings in Russian explain why phrases have their own tables (research R1) and why synonyms exist (R2)
- [X] T003 Create Alembic migration `backend/alembic/versions/<rev>_phrases.py` (`down_revision` = current head, check with `uv run --directory backend alembic heads`) that creates the five phrase tables with all indexes and FKs from T002 and touches no existing table. Docstring: what is added and why. `downgrade` drops only the phrase tables in reverse FK order
- [X] T004 [P] Add test `backend/tests/test_migrations.py`: run `alembic upgrade head` against a temp SQLite file (override the database URL the way `backend/alembic/env.py` reads it), insert a word with progress and a review_log row, run `downgrade -1` and `upgrade head` again, and assert the word, its progress and its log row are intact and the phrase tables exist. If `env.py` cannot take a temp URL, make the smallest change in `env.py` that allows it and explain it in a comment

### Описание колоды

- [X] T005 Create `backend/app/decks.py` with a frozen dataclass `Deck` (fields from data-model.md «Deck»: `name`, `item`, `progress`, `log`, `label`, `links`, `new_per_session`, `review_per_session`, `daily_new_limit` as callables or properties reading `app.config.settings` at call time, `uses_order_setting: bool`, `drop_apostrophes: bool`, `not_found: str`, `label_not_found: str`, `duplicate_detail` formatter) and constants `WORDS` and `PHRASES`. Module docstring explains R2: one study algorithm for two decks
- [X] T006 Add `drop_apostrophes: bool = False` keyword to `normalize_answer` in `backend/app/exercises.py`: when true, remove `'` after apostrophe unification instead of keeping it (research R4). Make `pick_distractor_words`, `build_exercise`, `check_answer` take `deck: Deck = WORDS`: distractor queries use `deck.item` instead of `Word`, `check_answer` passes `deck.drop_apostrophes` to both sides of the comparison. Word behaviour must stay byte-for-byte the same
- [X] T007 Parametrize `backend/app/study_service.py` by `deck: Deck = WORDS` in every public function (`new_words_query`, `fetch_new_words`, `new_words_allowance`, `_started_today`, `_due_words`, `build_session`, `_rounds_for`, `build_rounds`, `_log`, `select_word`, `answer_exercise`, `finish_session`, `reset_word`, `set_word_status`, `set_word_priority`, `due_counts`): replace `Word`/`Progress`/`ReviewLog` with `deck.item`/`deck.progress`/`deck.log`, session sizes and daily limit with deck values, and read `get_new_words_order` only when `deck.uses_order_setting` (otherwise ascending `id`, research R7). Constructors of progress rows use the synonym `word_id=` so they work for both decks. `srs.py` stays untouched
- [X] T008 [P] Parametrize `backend/app/labels_service.py` (`list_labels`, `resolve_labels`, `find_by_key`, `word_count`) and `backend/app/word_filters.py` (`filtered_words`) by `deck: Deck = WORDS`, using `deck.label`, `deck.links` and `deck.item`. `classify_batch` stays words-only
- [X] T009 [P] Add `get_item(deck)` dependency factory to `backend/app/routers/deps.py` returning the deck item or 404 with `deck.not_found`; keep `get_word = get_item(WORDS)` for the existing routers
- [X] T010 Run `yarn test:api` and `uv run --directory backend ruff check app tests`: all existing tests pass unchanged after T005–T009

### Фронтенд: колода в клиенте

- [X] T011 [P] Add `export type Deck = 'words' | 'phrases'` to `frontend/src/api/types.ts` with a comment that phrase responses reuse word schemas (`word` = phrase text, `word_id` = phrase id, contracts/api.md)
- [X] T012 Refactor `frontend/src/api/client.ts`: add `deckApi(deck: Deck)` that returns dictionary (`listWords`, `createWord`, `updateWord`, `setWordStatus`, `setWordPriority`, `deleteWord`), label (`listLabels`, `createLabel`, `updateLabel`, `deleteLabel`), study (`getSession`, `buildRounds`, `select`, `answer`, `finishSession`) and stats (`overview`, `daily`) methods with prefixes `/words|/phrases`, `/labels|/phrase-labels`, `/study|/phrase-study`, `/stats|/phrase-stats`. Keep `api` exporting the same methods as before (built from `deckApi('words')`) plus the words-only ones (`classifyBatch`, settings, classifier), so existing callers compile unchanged. Add `queryKeys(deck)` helper: words keep their current keys (`['words']`, `['labels']`, `['overview']`, `['daily', n]`), phrases get `['phrases']`, `['phrase-labels']`, `['overview', 'phrases']`, `['daily', 'phrases', n]`
- [X] T013 Run `yarn typecheck` and `yarn build`: green, no behaviour change

**Checkpoint**: таблицы фраз есть, общий код знает про колоды, слова работают как раньше.

---

## Phase 3: User Story 1 — Завести фразу в отдельный словарь (Priority: P1) 🎯 MVP

**Goal**: раздел «Фразы»: список с поиском, фильтрами статуса, «Учить первой» и метки,
добавление, правка, смена статуса, удаление, озвучка. Свои метки фраз со своей
вкладкой настроек (FR-022).

**Independent Test**: quickstart.md, сценарии 2 и 3.

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T014 [P] [US1] Create `backend/tests/test_phrases_api.py` with a `phrases` fixture (5–6 phrases with translations, e.g. «break the ice» — «растопить лёд», «It's up to you.» — «Решать тебе.») and dictionary tests per contracts/api.md: `POST /api/phrases` → 201 and the phrase listed with no progress; duplicate `Break  the ice` + same translation → 409 with «Фраза» in `detail`; same text with another translation → 201; text of 201 chars → 422; `PATCH` into an existing pair → 409; `GET /api/phrases?search=ice`, `status=new`, `priority=true`, `label=none`; `PUT /status` to each status and back to `new` writes nothing to `phrase_review_log`; `PUT /priority` on a phrase with progress → 409; `DELETE` → 204 and 404 after
- [X] T015 [P] [US1] In `backend/tests/test_phrases_api.py` add isolation tests: a phrase is absent from `GET /api/words?search=…` and a word with the same text («look after») can exist in both dictionaries; a phrase can be created with the exact text of an existing word
- [X] T016 [P] [US1] In `backend/tests/test_phrases_api.py` add phrase label tests: `POST /api/phrases` with `labels: ["идиомы"]` creates a phrase label and not a word label; `GET /api/phrase-labels` returns it with `word_count: 1`; a phrase label may have the name of an existing word label (no 409); `PATCH`/`DELETE /api/phrase-labels/{id}` follow `/api/labels` rules and delete unlinks phrases only; `GET /api/phrases?label=<id>` filters; `POST /api/phrase-labels/classify` → 404/405

### Implementation for User Story 1

- [X] T017 [US1] Add `PhraseCreate(WordCreate)` and `PhraseUpdate(WordUpdate)` to `backend/app/schemas.py` overriding `word` length to 1–200 (data-model.md); no other new schemas
- [X] T018 [US1] Turn `backend/app/routers/words.py` into `make_words_router(deck, prefix, create_schema, update_schema)`; `_same_meaning`, `_duplicate`, `create_word`, `update_word` work through `deck.item`, synonyms and `deck.duplicate_detail`, `resolve_labels(…, deck=deck)`, `filtered_words(…, deck=deck)`, `set_word_status`/`set_word_priority` with the deck. Phrases router omits `from_id`. Export `router = make_words_router(WORDS, "/words", WordCreate, WordUpdate)` and `phrases_router = make_words_router(PHRASES, "/phrases", PhraseCreate, PhraseUpdate)`
- [X] T019 [US1] Turn `backend/app/routers/labels.py` into `make_labels_router(deck, prefix, with_classify: bool)`; words keep `/labels` with `classify`, phrases get `/phrase-labels` without it
- [X] T020 [US1] Include `phrases_router` and the phrase labels router in `backend/app/main.py` under `/api`
- [X] T021 [P] [US1] Extract the dictionary table, row, `StatusSelect`, filters and pagination from `frontend/src/pages/WordsPage.tsx` into `frontend/src/components/DictionaryList.tsx` with props `deck: Deck` and optional `toolbar` slot; all calls go through `deckApi(deck)` and `queryKeys(deck)`; confirmations for delete and «Новое» stay; texts use deck nouns («слово»/«фраза», «Учить первым»/«Учить первой»). `WordsPage` renders `<DictionaryList deck="words" toolbar={auto-label button}>` with `AutoLabelPanel` exactly as before
- [X] T022 [P] [US1] Add `deck` prop to `frontend/src/components/WordForm.tsx` (labels «Фраза»/«Слово», `maxLength` 200/128) and `frontend/src/components/LabelPicker.tsx` (suggestions from `deckApi(deck).listLabels`, `queryKeys(deck)`)
- [X] T023 [P] [US1] Add `deck` prop to `frontend/src/components/LabelsSection.tsx`: list, create, rename, describe and delete via `deckApi(deck)`; invalidation via `queryKeys(deck)`; delete confirmation counts «фраз» for phrases
- [X] T024 [US1] Create `frontend/src/pages/PhrasesPage.tsx` (title «Фразы», button «Добавить» → `/phrases/new`, `<DictionaryList deck="phrases" />`) and `frontend/src/pages/AddPhrasePage.tsx` (mirror of `AddWordPage` with `deck="phrases"`, 409 keeps the form filled)
- [X] T025 [US1] In `frontend/src/App.tsx` add nav item «Фразы» after «Словарь» and routes `/phrases`, `/phrases/new`. In `frontend/src/pages/SettingsPage.tsx` add tab `phrase-labels` «Метки фраз» rendering `<LabelsSection deck="phrases" />`; existing tab «Метки» renders `deck="words"`
- [X] T026 [US1] Run tests T014–T016, `yarn typecheck`, `yarn build`; walk quickstart.md scenarios 2–3

**Checkpoint**: словарь и метки фраз работают; слова не изменились.

---

## Phase 4: User Story 2 — Учить новые фразы (Priority: P1)

**Goal**: «Учить фразы» — знакомство с 5 новыми фразами, «Уже знаю» с добором, пять
раундов, выпуск в повторения.

**Independent Test**: quickstart.md, сценарий 4.

### Tests for User Story 2 ⚠️ (write first, must fail)

- [X] T027 [P] [US2] In `backend/tests/test_phrases_api.py` add learn tests: with new words and 6 new phrases, `GET /api/phrase-study/session?mode=learn` gives 5 phrases (priority first, then ascending `id`, even when `new_words_order=newest_first`) and `/api/study/session?mode=learn` gives no phrase; `select` with `know` returns the 6th phrase as replacement and respects `exclude_ids`; `rounds` returns 5 rounds of phrases whose choice options are phrase texts/translations only; answers + `finish` with `mode=learn` graduate every phrase to `review` with interval 1; `DAILY_NEW_PHRASES_LIMIT` (monkeypatched to 2) limits phrases but not words and vice versa; empty phrase dictionary → `new_words: []`, `session_id: null`
- [X] T028 [P] [US2] In `backend/tests/test_phrases_api.py` add log isolation tests: phrase answers land in `phrase_review_log` and not in `review_log`; a words `session_id` passed to `/api/phrase-study/finish` returns `[]` and vice versa

### Implementation for User Story 2

- [X] T029 [US2] Turn `backend/app/routers/study.py` into `make_study_router(deck, prefix)` using `get_item(deck)` and passing `deck` to every service call; words keep `/study`, phrases get `/phrase-study`. Include the phrase study router in `backend/app/main.py`
- [X] T030 [US2] Add `deck` prop to `frontend/src/components/StudySession.tsx` and `frontend/src/components/RoundsRunner.tsx`: all API calls via `deckApi(deck)`, invalidations via `queryKeys(deck)`; intro card and exercise cards unchanged
- [X] T031 [US2] In `frontend/src/pages/StudyPage.tsx` read `deck` from search params (`phrases` or default `words`), include it in the session query key, pass it down, and use deck texts for loading, empty states (`Новых фраз нет` …) and the finish summary. In `frontend/src/components/StudyModeLinks.tsx` make `MODE_LABEL`, `studyPath` and `StudyModeLinks` take `deck` («Учить фразы», «Повторить фразы»; path `/study?deck=phrases&mode=…`); links without `deck` keep working
- [X] T032 [US2] In `frontend/src/pages/HomePage.tsx` show two blocks — «Слова» and «Фразы» — each with its overview tiles and `StudyModeLinks` with hints; the phrase block uses `deckApi('phrases').overview` (endpoint lands in US5 — until then build the hint from `GET /api/phrases?status=new&limit=1` `total`, or land T044 first)
- [X] T033 [US2] Run tests T027–T028, `yarn typecheck`, `yarn build`; walk quickstart.md scenario 4

**Checkpoint**: фразы учатся; занятия слов не затронуты.

---

## Phase 5: User Story 3 — Повторять фразы по расписанию (Priority: P1)

**Goal**: «Повторить фразы» берёт до 5 просроченных фраз и пересчитывает их расписание
по SM-2 один раз в `finish`.

**Independent Test**: quickstart.md, сценарий 5.

### Tests for User Story 3 ⚠️ (write first, must fail)

- [X] T034 [P] [US3] In `backend/tests/test_phrases_api.py` add review tests: with 3 due phrases and 3 due words, `GET /api/phrase-study/session?mode=review` returns rounds of the 3 phrases ordered most overdue first and nothing from words; a flawless session + `finish` grows the interval exactly as for a word with the same history (compare with `srs.apply_answer` on the same state and seeded rng — SC-004); one mistake → status `learning`, `lapses + 1`, due today; repeated `finish` is a no-op; an unfinished session changes nothing; word due dates are untouched throughout

### Implementation for User Story 3

- [X] T035 [US3] Make sure `_due_words`, `finish_session` and `due_counts` in `backend/app/study_service.py` use `deck.progress`/`deck.log` everywhere (T007) — fix any spot the tests T034 expose; no new code paths expected
- [X] T036 [US3] Run tests T034, walk quickstart.md scenario 5

**Checkpoint**: полный цикл «учить → повторять» для фраз.

---

## Phase 6: User Story 4 — Упражнения, подходящие фразам (Priority: P2)

**Goal**: сравнение без апострофа и пунктуации, сборка из букв для фраз, решаемые
карточки выбора при маленьком словаре фраз.

**Independent Test**: quickstart.md, сценарии 6–7.

### Tests for User Story 4 ⚠️ (write first, must fail)

- [X] T037 [P] [US4] In `backend/tests/test_exercises.py` add parametrized tests: `normalize_answer(x, drop_apostrophes=True)` maps «It's up to you.», «Its up to you», «IT’S  up-to you!» to `its up to you`; without the flag `o'clock` keeps its apostrophe (word behaviour unchanged); `check_answer(phrase, WRITING_RU_EN / DICTATION / LETTERS, …, deck=PHRASES)` accepts those variants and rejects «it is up to you», «up to you it's», «It's up to»
- [X] T038 [P] [US4] In `backend/tests/test_exercises.py` add letters tests for phrases: `build_mask("It's up to you!") == "__'_ __ __ ___!"`, the letter bank has 10 letters, the exercise built with `deck=PHRASES` has `solution` equal to the phrase text
- [X] T039 [P] [US4] In `backend/tests/test_exercises.py` add distractor tests with `deck=PHRASES` for dictionaries of 1, 2, 3 and 6 phrases (plus many words in the DB): options are only phrase texts/translations, include the correct answer, contain no duplicate translation, and number `min(4, phrases)`; words never appear

### Implementation for User Story 4

- [X] T040 [US4] Fix whatever T037–T039 expose in `backend/app/exercises.py` (expected: filler query and `notin_(seen or {0})` work on `deck.item`; empty shortlist for a single phrase returns a one-option card)
- [X] T041 [P] [US4] Check `frontend/src/components/exercises/ChoiceCard.tsx` renders and binds hotkeys correctly with 1–3 options, and the letters card lays out a long mask with spaces and punctuation without overflow (wrap the mask cells); fix in place if not
- [X] T042 [US4] Run tests T037–T039, `yarn typecheck`, `yarn build`; walk quickstart.md scenarios 6–7

**Checkpoint**: упражнения честны для фраз любой длины и словаря любого размера.

---

## Phase 7: User Story 5 — Фразы в статистике (Priority: P3)

**Goal**: статистика фраз отдельно от слов.

**Independent Test**: quickstart.md, сценарий 8.

### Tests for User Story 5 ⚠️ (write first, must fail)

- [X] T043 [P] [US5] In `backend/tests/test_phrases_api.py` add stats tests: after phrase and word answers on the same day, `GET /api/phrase-stats/overview` counts only phrases (`total_words` = phrases, statuses, `due_now`, `answers_today`, `new_today`, `streak_days` from `phrase_review_log`) and `GET /api/stats/overview` returns exactly what it returned before the phrase answers; same for `/daily`

### Implementation for User Story 5

- [X] T044 [US5] Turn `backend/app/routers/stats.py` into `make_stats_router(deck, prefix)` (`_count_by_status`, `_streak`, `overview`, `daily` over `deck.item`/`deck.progress`/`deck.log`, `due_counts(…, deck=deck)`); words keep `/stats`, phrases get `/phrase-stats`; include it in `backend/app/main.py`. If T032 used the temporary hint, switch the home phrase block to `deckApi('phrases').overview` now
- [X] T045 [US5] In `frontend/src/pages/StatsPage.tsx` render the overview and the daily chart for each deck in its own section («Слова», «Фразы») using `deckApi(deck)` and `queryKeys(deck)`
- [X] T046 [US5] Run tests T043, `yarn typecheck`, `yarn build`; walk quickstart.md scenario 8

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T047 Update `README.md` in the same commit as the code: new section «Фразы» (separate dictionary, labels, sessions, differences from words — 200 chars, apostrophe ignored, order always by addition, no auto-labelling), the four route groups in «API» with the note that responses reuse word schemas, the three new parameters in «Настройки», `phrase_review_log` mention, tables in «Структура» (`decks.py`), and «Что не сделано»: импорт фраз из CSV, автоматическая разметка фраз, порядок новых фраз, сборка фразы из слов
- [X] T048 Walk all quickstart.md scenarios, including scenario 1 (word numbers before/after migration on a copy of the real DB — SC-003)
- [X] T049 Run all gates: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests`
- [X] T050 Commit to `main` (feature commit: code + tests + README + types). Then propose to the user — do not commit without approval — a separate constitution amendment (`docs: amend constitution to v1.1.0 (...)`) replacing «`review_log`» in principles I and IV with «журнал колоды (`review_log`, `phrase_review_log`)», per plan.md Complexity Tracking

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)** → **Foundational (T002–T013)** → истории.
- Внутри Foundational: T002 → T003; T005 зависит от T002 (модели) и T001 (конфиг);
  T006, T007, T008, T009 зависят от T005; T010 — после T006–T009. Фронт T011 → T012 →
  T013 не зависит от бэкенда.
- **US1 (Phase 3)** — после Foundational. Самостоятельный MVP.
- **US2 (Phase 4)** — после Foundational; фразы для занятий удобно заводить через API
  US1, но тесты US2 создают фразы фикстурой, так что бэкенд US2 от US1 не зависит.
  Фронт US2 (T032) использует overview фраз — либо временная подсказка, либо T044
  раньше.
- **US3 (Phase 5)** — после US2 (общий роутер занятий T029).
- **US4 (Phase 6)** — после Foundational; тесты `test_exercises.py` от роутеров не
  зависят. Ручная проверка — после US2.
- **US5 (Phase 7)** — после Foundational; ручная проверка — после US2.
- **Polish** — после всех историй.

### Within Each User Story

- Тесты пишутся первыми и падают.
- Схемы → роутеры → `main.py` → фронтенд → прогон.

### Parallel Opportunities

- Foundational: T004 параллельно T005–T009; T008 ‖ T009; фронт T011–T013 ‖ весь бэкенд.
- US1: тесты T014 ‖ T015 ‖ T016 (один файл — писать по очереди, но независимо от
  реализации); фронт T021 ‖ T022 ‖ T023 после T012.
- US4 целиком (T037–T041) ‖ US2/US3 после Foundational.
- US5 бэкенд T043–T044 ‖ US2 бэкенд.

---

## Parallel Example: User Story 1

```text
# После Foundational, параллельно:
Task: "T021 Extract DictionaryList from WordsPage in frontend/src/components/DictionaryList.tsx"
Task: "T022 Add deck prop to WordForm.tsx and LabelPicker.tsx"
Task: "T023 Add deck prop to LabelsSection.tsx"
# Пока фронт идёт — бэкенд:
Task: "T017–T020 Phrase schemas, routers factories, main.py"
```

## Parallel Example: User Story 4

```text
Task: "T037 Apostrophe normalization tests in backend/tests/test_exercises.py"
Task: "T041 Check ChoiceCard with 1–3 options in frontend/src/components/exercises/ChoiceCard.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 + Phase 2: колоды и таблицы, слова зелёные (T010, T013).
2. Phase 3: словарь и метки фраз.
3. **STOP and VALIDATE**: quickstart 2–3; слова не изменились.

### Incremental Delivery

1. MVP (US1) — фразы можно копить.
2. US2 + US3 — полный цикл учёбы; это то, ради чего фича затевалась.
3. US4 — честная проверка и маленький словарь.
4. US5 — статистика.
5. Polish — README и коммит; поправка конституции отдельно, с согласия пользователя.

Коммит один на законченное изменение (конституция): если делать по частям, каждая
часть — с тестами, README и синхронными `types.ts`.

---

## Notes

- Все комментарии и докстринги — на русском, идентификаторы и коммиты — на английском.
- Не трогать `backend/app/srs.py`.
- Существующие тесты слов не правятся; если какой-то падает — сломано поведение слов.
- `[P]` — разные файлы и нет зависимостей от незавершённых задач.
