---

description: "Task list for importing words from a CSV file"
---

# Tasks: Импорт слов из CSV

**Input**: Design documents from `/specs/011-csv-word-import/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: обязательны по конституции (принцип III): изменение импорта и контракта
API сопровождается тестами в `backend/tests/`. Тесты каждой истории пишутся первыми
и до реализации должны падать. Существующий `backend/tests/test_import.py` не
правится: он доказывает, что консольный импорт после переноса функций ведёт себя как
раньше.

**Organization**: Phase 2 переносит общие правила слияния, заводит пределы, схемы и
типы. Дальше по истории на фазу:
- US1 — разбор файла и заведение новых слов с метками, от маршрута до панели;
- US2 — слияние с существующими словами и идемпотентность;
- US3 — пропуски с причинами, ошибки уровня файла и полный отчёт.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (разные файлы, нет зависимостей)
- **[Story]**: история из spec.md (US1–US3)

## Path Conventions

- Бэкенд: `backend/app/`, `backend/app/routers/`, `backend/tests/`
- Фронтенд: `frontend/src/`
- Тексты интерфейса, докстринги и комментарии — на русском; идентификаторы и
  сообщения коммитов — на английском (конституция, «Стиль»)

---

## Phase 1: Setup

**Purpose**: поправка принципа IV под оба импорта и именованные пределы импорта
(конституция II: никаких «магических чисел»).

- [X] T000 Amend `.specify/memory/constitution.md` in a separate commit `docs: amend constitution to v1.2.0 (imports only add to manual records)` that changes nothing else (approved by the user on 2026-10-16, plan.md «Поправка IV»). In principle IV replace the bullet «Импорт словаря (`app/cli.py`) ДОЛЖЕН быть идемпотентным и НЕ ДОЛЖЕН трогать записи, заведённые вручную.» with: «Импорт словаря — консольный (`app/cli.py`) и из интерфейса (`app/word_import.py`) — ДОЛЖЕН быть идемпотентным. Записи, заведённые вручную, импорт НЕ ДОЛЖЕН удалять, дробить или перезаписывать: он только дописывает значение перевода, которого в записи ещё нет, подставляет пример в пустое поле и добавляет метки. Прогресс и журналы ответов импорт не трогает.» Bump the version in the footer to 1.2.0, keep `Last Amended` at 2026-10-16, and rewrite the Sync Impact Report at the top (1.1.0 → 1.2.0, modified principle IV, templates need no edits)
- [X] T001 Add `import_max_bytes: int = 5_000_000` and `import_skipped_report_max: int = 200` to `Settings` in `backend/app/config.py` after the classifier settings. Give each a Russian comment explaining why: 5 МБ is five times `dictionary.csv`, so an accidentally chosen huge file is not read into memory; 200 because a report listing thousands of skipped rows from a wrong file explains nothing. Add `# IMPORT_MAX_BYTES=5000000` and `# IMPORT_SKIPPED_REPORT_MAX=200` to `backend/.env.example` next to the other settings (if the file exists)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: общий модуль импорта с перенесёнными правилами слияния, схемы ответа
и типы фронтенда. После этой фазы поведение приложения не меняется, а
`yarn test:api` проходит без правок существующих тестов.

**⚠️ CRITICAL**: ни одна история не начинается до конца этой фазы.

- [X] T002 Create `backend/app/word_import.py` with a Russian module docstring: import of words from a CSV file sent from the interface. The module holds pure parsing (`parse_import`), applying to the dictionary in one transaction (`apply_import`), and the merge rules shared with the console import (research R5, R6). Move `_row_for_translation` and `_merge_translation` from `backend/app/cli.py` here as public `row_for_translation(rows, translation)` and `merge_translation(existing, incoming)`, unchanged in logic, with their docstrings. Add `class ImportFileError(ValueError)` with an `__init__(self, detail: str, status_code: int = 422)` that stores `detail` and `status_code`; its docstring says it is a file-level error: the import does not start and the dictionary is untouched
- [X] T003 Update `backend/app/cli.py` to import `row_for_translation` and `merge_translation` from `app.word_import` and call them instead of the removed private functions; change nothing else (its column set, report and messages stay as they are). Run `uv run --directory backend pytest tests/test_import.py` — it must pass unchanged
- [X] T004 [P] Add schemas to `backend/app/schemas.py` per data-model.md and contracts/api.md: `ImportSkippedRow` (`line: int`, `reason: str`) and `ImportReport` (`rows`, `created`, `merged`, `unchanged`, `skipped: int`; `skipped_rows: list[ImportSkippedRow]`; `labels_created: list[str]`; `ignored_columns: list[str]`). Russian docstrings: `ImportReport` is the result of one import run, not stored anywhere, with the invariant `rows == created + merged + unchanged + skipped`; `skipped_rows` holds at most `import_skipped_report_max` items while `skipped` is the full count
- [X] T005 [P] Add `ImportSkippedRow` and `ImportReport` interfaces to `frontend/src/api/types.ts`, matching T004 field for field (contracts/api.md, «Фронтенд»)

**Checkpoint**: `yarn test:api`, `yarn typecheck` и `ruff check` зелёные, поведение
не изменилось.

---

## Phase 3: User Story 1 — Загрузить слова из файла (Priority: P1) 🎯 MVP

**Goal**: пользователь выбирает на «Словаре» CSV-файл. Новые слова появляются со
статусом «Новое» и метками из файла, недостающие метки создаются.

**Independent Test**: импорт файла из трёх новых слов, у двух метка «Кухня»,
которой ещё нет: три слова «Новое», у двух метка «Кухня», метка видна в
«Настройки → Метки» (quickstart §2).

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T006 [P] [US1] Create `backend/tests/test_word_import.py` with table tests (`pytest.mark.parametrize`) for `parse_import(content: bytes)`, no database:
  - delimiter `;` and `,` chosen from the header (research R3); a tie or a single column picks `,`;
  - UTF-8 with and without BOM give the same result, and BOM never leaks into the first column name;
  - Russian headers (`слово`, `перевод`, `пример`, `пример использования`, `перевод примера`, `метка`, `метки`) and English ones (`word`, `translation`, `example`, `example_translation`, `label`, `labels`) map to the same fields regardless of case, surrounding spaces and `ё`, in any column order (research R4);
  - quoted values with the delimiter and a newline inside are read as one cell;
  - the label cell is split on `;` with `strip` and empty items dropped (`"Кухня; посуда;;"` → `["Кухня", "посуда"]`);
  - `example_translation` without `example` becomes `None`, and an empty `example` becomes `None`;
  - `ImportRow.line` is the spreadsheet row number (header 1, first record 2), even after a record with a newline inside quotes;
  - a row with all cells empty is neither a row nor a skip, and `total_rows` does not count it;
  - a row without a word or without a translation becomes a `SkippedRow` «нет слова» / «нет перевода» with its line number and is counted in `total_rows`;
  - a file without `слово` or without `перевод` raises `ImportFileError` with status 422, and its `detail` names the missing columns and lists the expected ones;
  - `dictionary.csv`'s exact header line `"word","translation","example","example_translation"` with BOM is accepted
- [X] T007 [P] [US1] Add `POST /api/words/import` tests to `backend/tests/test_api.py` using the `client` and `db_session` fixtures and a helper that posts bytes with `Content-Type: text/csv`:
  - a file of three new words returns 200 with `created == 3`;
  - each word has `progress is None` (status «Новое») with the translation, example and example translation from the file;
  - `labels_created == ["Кухня"]`, and a second row with `кухня` reuses that label instead of creating another one;
  - an existing label `Кухня` is reused with its spelling and description intact;
  - words of one import get increasing `id` in file order, so `GET /api/study/session?mode=learn` with the default order offers them in file order (FR-019);
  - no row is added to `review_log`, `phrase_review_log` or `group_review_log`, and `phrases` stays empty (FR-011, FR-020);
  - a file with one row without a translation returns `skipped == 1` with that line in `skipped_rows`, and the invariant `rows == created + merged + unchanged + skipped` holds;
  - a file without the translation column returns 422 with a string `detail`, and the dictionary is unchanged

### Implementation for User Story 1

- [X] T008 [US1] Implement `parse_import(content: bytes) -> ParsedImport` in `backend/app/word_import.py` with frozen dataclasses `ImportRow(line, word, translation, example, example_translation, labels)`, `SkippedRow(line, reason)` and `ParsedImport(rows, skipped, ignored_columns, total_rows)` per data-model.md:
  - decode as `utf-8-sig`;
  - choose the delimiter by counting `;` and `,` outside quotes in the header line (research R3);
  - read with `csv.reader` over `io.StringIO(text, newline="")`;
  - normalize header names (`strip`, `casefold`, `_` → space, `ё` → `е`) and map them through a module-level synonym table `COLUMN_ALIASES` (research R4), keeping unrecognized original names in `ignored_columns`;
  - raise `ImportFileError` when `слово` or `перевод` is missing, with the detail from data-model.md;
  - number rows by record index (`index + 2`) and skip all-empty rows silently;
  - strip values, and split labels on `;`.

  A row without a word becomes `SkippedRow(line, "нет слова")` and a row without a translation becomes `SkippedRow(line, "нет перевода")`; length limits and file-level checks other than missing columns come in US3. Russian comments must explain why columns are matched by name (a shifted column would silently corrupt values) and why the delimiter is taken from the header (translations contain commas, so sniffing the data guesses wrong)
- [X] T009 [US1] Implement `apply_import(session: Session, parsed: ParsedImport, now: datetime) -> ImportReport` in `backend/app/word_import.py`:
  - load all `Word` with `selectinload(Word.labels)` into `index: dict[str, list[Word]]` by `word_key` (research R8);
  - load all `Label` into a dict by `name_key` before the pass. The file's label names whose `label_key` is not in that dict are the new ones: create them with one `resolve_labels` call from `app/labels_service.py`, add them to the dict, and put their names in `labels_created` sorted by `label_sort_key`. Do not detect new labels by `id is None`: that depends on the session's autoflush;
  - for each row whose `word_key_for(word)` has no records yet, create a `Word(word, word_key, translation, example, example_translation, created_at=now, labels=...)`, `session.add` it, append it to `index` and count it as `created`;
  - for this story a row whose word already exists counts as `unchanged` with no change (merging comes in US2);
  - set `rows = parsed.total_rows`, `skipped = len(parsed.skipped)`, `skipped_rows` from `parsed.skipped` (truncation comes in US3);
  - call `session.flush()` at the end.

  Russian docstring: progress and the answer logs are never touched, since an import edits the dictionary and is not an answer to an exercise (constitution I, IV); the whole file runs in the caller's transaction, so any exception leaves the dictionary as it was (FR-015)
- [X] T010 [US1] Create `backend/app/routers/word_import.py` with `router = APIRouter(prefix="/words", tags=["words"])` and `POST /import` → `ImportReport`:
  - parameter `content: bytes = Body(default=b"", media_type="text/csv")` and `session: Session = Depends(get_session)`;
  - call `parse_import(content)`, then `apply_import(session, parsed, utcnow())`;
  - catch `ImportFileError` and raise `HTTPException(err.status_code, detail=err.detail)`.

  Russian module docstring: why the raw body and not multipart (no new dependency, the server decodes and can explain an encoding error — research R1), why `default=b""` (an empty body would give an unreadable 422 list), and why the router is separate from `make_words_router` (that factory is shared with phrases, and only words have an import). Register it in `backend/app/main.py` with `app.include_router(word_import.router, prefix="/api")` **before** `words.router`
- [X] T011 [P] [US1] Add `importWords: (file: File) => Promise<ImportReport>` to `api` in `frontend/src/api/client.ts`: `request<ImportReport>('/words/import', { method: 'POST', body: file, headers: { 'Content-Type': 'text/csv' } })`. Since `request` spreads `init` after its own `headers`, the passed headers replace the JSON header; add a Russian comment that the file goes as is so the server decodes it itself (research R1)
- [X] T012 [US1] Create `frontend/src/components/ImportPanel.tsx` (`{ onClose }`), styled like `AutoLabelPanel`:
  - a file input with `accept=".csv,text/csv"` and an «Импортировать» button, disabled until a file is chosen and while the request runs;
  - before sending, compare `file.size` with a module constant `IMPORT_MAX_BYTES = 5_000_000` and, if it is larger, show «Файл больше 5 МБ» without a request. A Russian comment says the constant mirrors `import_max_bytes` in `backend/app/config.py`, only spares a pointless upload, and the server check decides (research R9);
  - a `useMutation` calling `api.importWords`;
  - on success, invalidate `['words']`, `['labels']` and `['overview']` (the home page counters of new words) like `AutoLabelPanel` does (FR-017) and show the counters `rows`, `created`, `merged`, `unchanged` and the `labels_created` list in Russian (`прочитано строк`, `добавлено слов`, `дополнено`, `без изменений`, `создано меток`);
  - on error, show `ErrorBox` with the `ApiError` message;
  - a «Закрыть» button calling `onClose`
- [X] T013 [US1] Update `frontend/src/pages/WordsPage.tsx`:
  - replace `autoLabelOpen` with `const [panel, setPanel] = useState<'autoLabel' | 'import' | null>(null)`, so only one panel is open at a time;
  - add an «Импорт из CSV» button before «Разметить автоматически» in `tools`, with the same toggle styling and `aria-expanded`;
  - render `<ImportPanel onClose={() => setPanel(null)} />` from the `panel` slot when `panel === 'import'`;
  - keep `AutoLabelPanel` behaviour unchanged

**Checkpoint**: T006 и T007 зелёные; quickstart §2 проходит в браузере.

---

## Phase 4: User Story 2 — Повторный импорт не плодит дублей (Priority: P1)

**Goal**: у существующих слов дописывается перевод через «;», пример подставляется
только в пустое поле, метки добавляются. Прогресс не меняется. Тот же файл
дважды ничего не меняет.

**Independent Test**: quickstart §3 — после повторного импорта записей ровно на одну
больше, перевод «старый; новый», обе метки на месте, срок выученного слова прежний.

### Tests for User Story 2 ⚠️ (write first, must fail)

- [X] T014 [US2] Add merge tests to `backend/tests/test_api.py`:
  - the same pair with different case and spaces → no new record, counted in `unchanged`;
  - `saucepan — сотейник` over `saucepan — кастрюля` → `translation == "кастрюля; сотейник"`, `merged == 1`, still one record;
  - a word with two manual records (`roll out — вылезать`, `roll out — внедрить`) and a row `roll out — внедрить` with a label → the label goes to the `внедрить` record, not the first one (FR-008);
  - an existing example is kept while an empty one is filled together with its translation (FR-009);
  - a new label is added and an existing one is not removed (FR-010);
  - a word in review with progress (use `study_service`/fixtures to give it `status`, `due_at`, `interval_days`, `lapses` and `priority`) is re-imported with a new translation and label → every progress field and `priority` are identical, and no log rows appear (FR-011);
  - two rows of the same new word in one file with different translations and labels → one record with both translations and both labels, counted `created` then `merged`;
  - posting the same file twice → the second report has `created == merged == 0`, `labels_created == []`, `unchanged == rows`, and the words and labels tables are identical (FR-012, SC-003);
  - a generated file of 1 000 rows (unique words, some with labels, examples and repeated words) imported twice → the second run reports `created == merged == 0`. Build it in the test instead of reading the repository `dictionary.csv`, so tests stay fast and independent of project data; the real file is checked by hand in T022 (SC-002, SC-003)

### Implementation for User Story 2

- [X] T015 [US2] Extend `apply_import` in `backend/app/word_import.py` for rows whose word already has records (including records created earlier in the same file):
  - pick the target with `row_for_translation(index[key], row.translation)`;
  - set `translation = merge_translation(...)` when it changes;
  - fill `example` and `example_translation` only when `example` is empty and the row has one;
  - append the row's labels missing from `target.labels`, compared by `label_key`.

  Count the row as `merged` if anything changed, otherwise `unchanged`; never touch `progress` or `priority`. Add a Russian comment that the merge rules are the console import's on purpose, so both ways build the same dictionary (Clarifications in spec), and that existing translations, examples and labels are only added to, never replaced

**Checkpoint**: T014 зелёный; quickstart §3 и §4 проходят.

---

## Phase 5: User Story 3 — Понятный отчёт и ошибки в файле (Priority: P2)

**Goal**: в отчёте пропущенные строки с номером и причиной и игнорированные колонки.
Непригодный файл отклоняется целиком с понятным сообщением. Окно импорта
подсказывает формат.

**Independent Test**: файл из пяти строк (три правильные, одна без перевода, одна со
словом длиннее 128 символов) → прочитано 5, добавлено 3, пропущено 2, с номерами
строк и причинами. Файл без колонки перевода → словарь не изменился, сообщение
называет колонку (quickstart §5).

### Tests for User Story 3 ⚠️ (write first, must fail)

- [X] T016 [P] [US3] Extend `backend/tests/test_word_import.py` with table tests:
  - skip reasons and line numbers for «слово длиннее 128 символов» and «метка «…» длиннее 50 символов» (research R7), counted in `total_rows`;
  - a too-long label skips the whole row;
  - an unrecognized column (`источник`) lands in `ignored_columns` with its original spelling;
  - the same field named twice (`перевод` and `translation`) raises `ImportFileError` 422 «Колонка «перевод» встречается дважды»;
  - an empty or whitespace-only body raises 422 «Файл пустой»;
  - Windows-1251 bytes raise 422 with the UTF-8 hint;
  - a header-only file gives zero rows with no error
- [X] T017 [P] [US3] Extend `backend/tests/test_api.py`:
  - a body larger than `settings.import_max_bytes` (monkeypatch the setting to a small value) returns 413 «Файл больше … МБ» and the dictionary is unchanged;
  - an empty body returns 422 with a string `detail`;
  - a file with two bad rows imports the rest, `skipped == 2` and `skipped_rows` carries the line numbers and reasons;
  - with `import_skipped_report_max` monkeypatched to 1, `skipped_rows` has one item while `skipped` is the full count;
  - the report invariant `rows == created + merged + unchanged + skipped` holds;
  - rollback (FR-015): monkeypatch `app.word_import.word_key_for` with a wrapper that delegates to the real function and raises `RuntimeError` on its third call. Post a file of three new words with a new label inside `pytest.raises(RuntimeError)`, since `TestClient` re-raises server exceptions. Then `words` is empty and the label does not exist. `word_key_for` runs once per row, so the test works right after US1 and does not depend on US2

### Implementation for User Story 3

- [X] T018 [US3] Extend `parse_import` in `backend/app/word_import.py`:
  - check `len(content) > settings.import_max_bytes` first → `ImportFileError(..., 413)`, with the limit shown in megabytes;
  - an empty or whitespace-only text → 422 «Файл пустой»;
  - catch `UnicodeDecodeError` → 422 «Файл не в UTF-8 — сохраните его как «CSV UTF-8»»;
  - a duplicate field → 422 naming the column;
  - add `SkippedRow` entries for the length reasons from research R7, using the limit constants from `app/schemas.py`: `LABEL_NAME_MAX`, and a `WORD_MAX_LENGTH = 128` constant extracted from `max_length` and reused in both `WordBase.word` and `WordUpdate.word`, so the form and the import share one limit;
  - in `apply_import`, truncate `skipped_rows` to `settings.import_skipped_report_max` (`skipped` stays the full count) and fill `ignored_columns`
- [X] T019 [US3] Extend `frontend/src/components/ImportPanel.tsx`:
  - before a file is chosen, show a hint (FR-018) listing the columns `слово`, `перевод` (обязательные), `пример`, `перевод примера`, `метка`; that English names from `dictionary.csv` work too; that the delimiter `,` or `;` is detected automatically; that the file must be saved as «CSV UTF-8»; and that several labels go in one cell separated by `;`, in quotes when `;` is also the column delimiter;
  - in the report, show `skipped` and the list `строка N — причина` from `skipped_rows`, with «и ещё K» when `skipped > skipped_rows.length`;
  - show `ignored_columns` as «Колонки не распознаны и пропущены: …»;
  - keep the error box for 413/422

**Checkpoint**: T016 и T017 зелёные; quickstart §5 проходит.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Update `README.md` in the same commit as the code (FR-021, constitution V):
  - add a subsection on importing from the interface (where the button is, the columns and their English synonyms, delimiter and encoding, several labels via `;`, merge rules identical to `yarn db:import`, idempotence, untouched progress, the report and the 5 МБ limit);
  - change «Импорт CSV меток не трогает» in the labels section to say that the console `yarn db:import` does not touch labels while import from the interface sets them;
  - add the `POST /api/words/import` line to «API» exactly as in contracts/api.md;
  - add `word_import.py` and `routers/word_import.py` to the project tree near `cli.py`;
  - keep «Импорт фраз из CSV» and «Разметка при добавлении слова и при импорте CSV» in «Что не сделано»
- [X] T021 Run the gates and fix every failure: `yarn test:api`, `uv run --directory backend ruff check app tests`, `yarn typecheck`, `yarn build`
- [X] T022 Walk through `specs/011-csv-word-import/quickstart.md` §2–§5 against `yarn dev` (back up `backend/data/app.db` first). Put the test CSV files in the session scratchpad, not in the repository. Confirm that the `dictionary.csv` re-import finishes in under 10 s (SC-002)
- [X] T023 Commit straight to `main` (project memory), one commit for the whole feature including `specs/011-csv-word-import/`, after the separate constitution commit from T000. Use the title `Import words from a CSV file on the dictionary page` and a body explaining the observation (words came in one by one or through a console import that ignored labels), the cause and the decision (raw `text/csv` body with no new dependency, shared merge rules with `yarn db:import`, one transaction). Do not add `backend/data/app.db.bak-before-phrases`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T000 first, as its own commit; then T001
- **Foundational (Phase 2)**: after T001; blocks all stories
- **US1 (Phase 3)**: after Phase 2 — MVP
- **US2 (Phase 4)**: after US1 (extends `apply_import` from T009, and its tests post through the T010 route)
- **US3 (Phase 5)**: after US1; independent of US2, but T017 and T014 both append to `backend/tests/test_api.py`, so write them in separate sections or one after the other
- **Polish (Phase 6)**: after all stories

### Within Phase 2

- T002 → T003 (cli imports from the new module)
- T004 and T005 are independent of T002–T003 and of each other

### Within each story

- Tests first, failing, then implementation
- US1: T008 → T009 → T010 (backend), T011 → T012 → T013 (frontend); the two tracks are independent
- US2: T014 → T015
- US3: T016, T017 → T018 (backend); T019 (frontend) is independent of the backend tasks

### Parallel Opportunities

- Phase 2: T004 and T005 run alongside T002–T003
- US1: T006, T007 and T011 at once; then backend T008–T010 and frontend T012–T013 as separate tracks
- US3: T016 and T017 at once; T019 alongside T018
- US2 and US3 backend work can overlap after US1 if `test_api.py` sections are kept apart; both T015 and T018 edit `word_import.py`, so do them one after the other

---

## Parallel Example: User Story 1

```bash
# Tests and the client together:
Task: "T006 [US1] parse_import table tests in backend/tests/test_word_import.py"
Task: "T007 [US1] POST /api/words/import tests in backend/tests/test_api.py"
Task: "T011 [US1] api.importWords in frontend/src/api/client.ts"

# Then two tracks:
Task: "T008 → T009 → T010 parse, apply, router (backend)"
Task: "T012 → T013 ImportPanel and WordsPage (frontend)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 — T000 (constitution commit), T001
2. Phase 2 — shared merge rules moved, schemas and types
3. Phase 3 — US1: import of new words with labels from the dictionary page
4. **STOP and VALIDATE**: quickstart §2

### Incremental Delivery

1. US1 → новые слова и метки из файла
2. US2 → повторный импорт безопасен: слияние, неизменный прогресс
3. US3 → отчёт с пропусками, ошибки файла, подсказка формата
4. Polish → README, проверки, quickstart, один коммит

US1 alone is safe: an existing word is counted as `unchanged` and not touched, so
nothing is duplicated. US2 only turns that into a merge.

### Notes

- Схема базы не меняется: миграции и `test_migrations.py` не нужны
- Консольный импорт меняется только в одном месте — откуда берутся две функции
  (T003); `test_import.py` — его страховка
- По конституции все четыре проверки (T021) обязательны перед коммитом (T023)
