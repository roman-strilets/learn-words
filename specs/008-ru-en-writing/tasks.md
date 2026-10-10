---

description: "Task list for the writing_ru_en exercise"
---

# Tasks: Упражнение «Напишите слово по-английски»

**Input**: Design documents from `/specs/008-ru-en-writing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Обязательны по конституции (принцип III): изменение генерации упражнений,
проверки ответов и контракта API сопровождается тестом в `backend/tests/`. Тесты пишутся
первыми и должны падать до реализации.

**Organization**: Задачи сгруппированы по историям из spec.md. US1 — новый раунд
работает. US2 — гарантии «без подсказок».

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (разные файлы, нет зависимостей)
- **[Story]**: история из spec.md (US1, US2)

## Path Conventions

- Бэкенд: `backend/app/`, `backend/tests/`
- Фронтенд: `frontend/src/`

---

## Phase 1: Setup

Инфраструктура уже есть: зависимости, тест-раннер и линтер не меняются. Миграция не нужна
(research R2). Задач нет.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: новое значение перечисления, без которого не собрать ни карточку, ни тесты.

- [X] T001 Add `WRITING_RU_EN = "writing_ru_en"` to `ExerciseType` in `backend/app/models.py`, between `LETTERS` and `DICTATION`. Keep the order the same as the rounds order
- [X] T002 [P] Add `'writing_ru_en'` to the `ExerciseType` union in `frontend/src/api/types.ts`, between `'letters'` and `'dictation'`

**Checkpoint**: тип существует в обоих слоях; до T003+ поведение занятия не меняется.

---

## Phase 3: User Story 1 — Написать английское слово по русскому переводу (Priority: P1) 🎯 MVP

**Goal**: Занятие из пяти раундов. Четвёртый раунд — `writing_ru_en`: карточка с русским
переводом, ответ — английское слово, проверка на сервере. Расписание пересчитывается
только после всех пяти раундов.

**Independent Test**: занятие из 3 слов. После «Сборки из букв» идёт «Написание:
рус → англ». `knife` на «нож» засчитан, `knif` не засчитан, и карточка вернулась в конец
раунда. Последним идёт «Аудирование» (quickstart.md, шаги 1–5).

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T003 [P] [US1] In `backend/tests/test_srs.py::test_exercise_rounds_are_fixed_and_skip_the_intro_card`, change the expected `EXERCISE_ROUNDS` to `(CHOICE_RU_EN, CHOICE_EN_RU, LETTERS, WRITING_RU_EN, DICTATION)`. Update the comment to the new spec's FR-002
- [X] T004 [P] [US1] In `backend/tests/test_exercises.py`, add `test_writing_exercise_shows_translation_only`. Build the card with `build_exercise(db_session, target, ExerciseType.WRITING_RU_EN, rng=random.Random(0))` for the word `budge`. Assert `exercise.type == ExerciseType.WRITING_RU_EN`, `exercise.prompt == "сдвинуть с места"` and `exercise.model_dump().keys() == {"type", "word_id", "prompt"}` (no `hint`/`solution`/`mask`/`audio_text`, FR-003)
- [X] T005 [P] [US1] In `backend/tests/test_exercises.py::test_check_answer`, add parametrized rows for `ExerciseType.WRITING_RU_EN`: `"budge"` → True, `" BUDGE "` → True, `"to budge"` → True, `"bulge"` → False, `""` → False, `None` → False (FR-004, FR-005)
- [X] T006 [P] [US1] In `backend/tests/test_exercises.py`, add `test_writing_rejects_a_synonym_with_the_same_translation`. Create two words with the same `translation` (e.g. `big` and `large`, both «большой»). Check that `check_answer(big, WRITING_RU_EN, "large")` is False and that `correct_answer_for(big, WRITING_RU_EN) == "big"` (Edge Cases of the spec)
- [X] T007 [US1] In `backend/tests/test_api.py`, rename `test_review_session_is_a_plan_of_four_rounds` → `..._of_five_rounds`, `test_review_plan_holds_four_exercises_per_word` → `..._holds_an_exercise_per_round_per_word` and `test_a_clean_learn_session_is_four_rounds_of_five` → `..._is_five_rounds_of_five`. In the last one, change `== 20` to `== 25` and its comment. Add `assert body["rounds"][3]["exercise"] == ExerciseType.WRITING_RU_EN` to the five-rounds test. Change all comments «четыре раунда» to «пять раундов» / «все раунды». `_answers_of` needs no change: for `writing_ru_en` the answer is `word.word`
- [X] T008 [US1] In `backend/tests/test_api.py`, add `test_wrong_writing_answer_repeats_the_same_card`: in a review session, answering `WRITING_RU_EN` with a typo returns `correct: false`, `correct_answer == word.word`, and `next_exercise == {"type": "writing_ru_en", "word_id": ..., "prompt": word.translation}` (FR-006, research R7)
- [X] T009 [US1] In `backend/tests/test_api.py`, add `test_finish_skips_a_word_that_missed_the_writing_round`. Pattern: the test around «Первое слово проходит все четыре раунда». The first word answers every round. The second word answers every round except `writing_ru_en`. After `_finish` only the first word is in the results, and the second word's `Progress` is unchanged (FR-008, SC-005)

### Implementation for User Story 1

- [X] T010 [US1] In `backend/app/srs.py`, insert `ExerciseType.WRITING_RU_EN` into `EXERCISE_ROUNDS` before `DICTATION`. Change the comment above it from «четырьмя раундами» to «пятью раундами». Docstring of `session_quality`: «четыре раунда» → «все раунды»
- [X] T011 [P] [US1] In `backend/app/schemas.py`, add `class WritingRuEnExercise(BaseModel)` with the docstring «Показан русский перевод, надо написать английское слово. Подсказки и ответа в карточке нет: вспомнить слово без опоры — и есть задание» and the fields `type: Literal[ExerciseType.WRITING_RU_EN] = ExerciseType.WRITING_RU_EN`, `word_id: int`, `prompt: str`. Place it between `LettersExercise` and `DictationExercise`, and add it to the `Exercise` union in the same order
- [X] T012 [US1] In `backend/app/exercises.py`, import `WritingRuEnExercise`. In `build_exercise`, add the branch `if exercise_type == ExerciseType.WRITING_RU_EN: return WritingRuEnExercise(word_id=word.id, prompt=word.translation)` after the `DICTATION` branch and before `pick_distractor_words`, so no distractors are picked. `check_answer` and `correct_answer_for` stay as they are: the default branch compares with `word.word` (research R5)
- [X] T013 [US1] In `backend/app/study_service.py`, change the docstrings and comments that say «четыре раунда» / «все четыре» (e.g. in `answer_exercise`) to «все раунды». Do not change the logic: `_rounds_for` and `finish` already read `EXERCISE_ROUNDS`
- [X] T014 [P] [US1] In `frontend/src/api/types.ts`, add `export interface WritingRuEnExercise { type: 'writing_ru_en'; word_id: number; prompt: string }` with the JSDoc «Ответа и подсказки в карточке нет — их не во что подсмотреть». Add it to `Exercise` = `ChoiceExercise | LettersExercise | WritingRuEnExercise | DictationExercise`
- [X] T015 [US1] Create `frontend/src/components/exercises/WritingCard.tsx` with `export function WritingCard({ exercise, onAnswer, locked }: ExerciseCardProps<WritingRuEnExercise>)`, modelled on `DictationCard.tsx`. Use `Caption` «Напишите слово по-английски» and show `exercise.prompt` in large text. The input has autofocus and is reset on a `word_id` change. Enter calls `onAnswer({ answer: value, usedHint: false })`. Set `autoComplete="off" autoCorrect="off" spellCheck={false}`, the placeholder «Напишите слово» and the caption under it «Введите слово и нажмите Enter». Do not add `HintButton`, `useSpeech`/`useSpeakOnce`, cells, a letter count or a first letter
- [X] T016 [US1] In `frontend/src/components/exercises/ExerciseView.tsx`, import `WritingCard` and add `case 'writing_ru_en'` returning `<WritingCard key={`${exercise.word_id}-writing_ru_en`} … />`
- [X] T017 [US1] In `frontend/src/components/RoundsRunner.tsx`, add `writing_ru_en: 'Написание: рус → англ'` to `EXERCISE_LABEL` between `letters` and `dictation`. Change the comment «четыре раунда по типам упражнений» to «раунды по типам упражнений»
- [X] T018 [P] [US1] In `frontend/src/api/client.ts`, change the comment «прошедшего все четыре раунда» to «прошедшего все раунды»

**Checkpoint**: `yarn test:api` green, `yarn typecheck` green. In a live session the new round is fourth and accepts the answer.

---

## Phase 4: User Story 2 — Без подсказок (Priority: P1)

**Goal**: The server does not lower the grade for a hint that does not exist, and the card shows nothing that reveals the answer.

**Independent Test**: `POST /api/study/answer` with `exercise: "writing_ru_en"` and `used_hint: true` writes `used_hint = false` and `quality = 5` to the log. The card has no lamp, cells or sound (quickstart.md, step 2 and step 6).

### Tests for User Story 2 ⚠️ (write first, must fail)

- [X] T019 [US2] In `backend/tests/test_api.py`, add `test_writing_ignores_a_claimed_hint`. In a review session, send a correct `WRITING_RU_EN` answer with `used_hint: True`, `attempt: 1`. The `ReviewLog` entry has `used_hint is False` and `quality == 5` (FR-007, research R6). A control check in the same test: `LETTERS` with `used_hint: True` still gets `quality == 4`
- [X] T020 [P] [US2] In `backend/tests/test_api.py`, add `test_session_plan_does_not_leak_the_writing_answer`. In the review session plan (`_session(client, "review")`) and the learn plan (`_rounds(client, word_ids)`), every exercise with `type == "writing_ru_en"` has exactly the keys `{"type", "word_id", "prompt"}`, and `word.word` is not among the values (contracts/api.md)

### Implementation for User Story 2

- [X] T021 [US2] In `backend/app/srs.py`, next to `EXERCISE_ROUNDS`, add `EXERCISES_WITHOUT_HINT: frozenset[ExerciseType] = frozenset({ExerciseType.WRITING_RU_EN})` with the comment «why»: the card shows no hint, so a `used_hint` sent by the client must not lower the grade. The server assigns the grade
- [X] T022 [US2] In `backend/app/study_service.py::answer_exercise`, import `EXERCISES_WITHOUT_HINT`. Compute `used_hint = request.used_hint and request.exercise not in EXERCISES_WITHOUT_HINT` once, and pass it to both `derive_quality(...)` and `_log(..., used_hint=used_hint, ...)` instead of `request.used_hint`
- [X] T023 [US2] Check `frontend/src/components/exercises/WritingCard.tsx` against FR-003. No `HintButton`, no hint hotkey handler (`useHotkeys` is not used), no `useSpeakOnce`, no `audio_text`/`solution`. The placeholder does not depend on the word length

**Checkpoint**: tests T019–T020 green. Pressing the hint hotkey on the card does nothing.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T024 Update `README.md` (принцип V, контракт API):
  - in the «Занятие идёт раундами» table, add the row `| 4 | \`writing_ru_en\` | Пишет английское слово по русскому переводу, без подсказок |` and renumber `dictation` to 5;
  - change «четыре раунда» to «пять раундов» throughout the file (the mode table near «Учить слова» / «Повторить слова», «прошедшего все четыре раунда», «из четырёх типов упражнений» in the «API» section);
  - in the «API» section, add a sentence: the `writing_ru_en` card holds only `word_id` and `prompt` and has no answer, and `used_hint` for it is ignored
- [X] T025 Run every gate from quickstart.md: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests`. Fix whatever fails
- [ ] T026 Go through the manual check in quickstart.md (`yarn dev`, steps 1–6), including the DevTools check that the plan has no English word in `writing_ru_en` cards
- [X] T027 Commit to `main` in one commit (schemas, tests, types.ts and README together, as the constitution requires for API contract changes). Use an imperative English subject such as `Ask for the English word with no hints before dictation`, and a body covering the observation, the reason and the decision

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: T001 → everything else on the backend. T002 → T014–T017
- **US1 (Phase 3)**: after Phase 2. Tests T003–T009 come before T010–T013
- **US2 (Phase 4)**: after T010–T012 (the card and the round exist). T019–T020 come before T021–T022. T023 comes after T015
- **Polish (Phase 5)**: after US1 and US2

### Within User Story 1

- T003–T006 can run in parallel (two files: test_srs.py, test_exercises.py; inside test_exercises.py the changes are independent but edit the same file — do them in sequence if one agent works on it)
- T007 → T008 → T009 run in sequence (one file test_api.py)
- T010 → T011 → T012 (the schema is imported in exercises.py) → T013
- Frontend T014 → T015 → T016 → T017. T018 is independent

### Parallel Opportunities

- The backend (T003–T013) and the frontend (T014–T018) of US1 are independent once T001/T002 are done
- T019 and T020 are in one file — in sequence. T021 → T022 in sequence

---

## Parallel Example: User Story 1

```bash
# Tests in different files at once:
Task: "T003 EXERCISE_ROUNDS order in backend/tests/test_srs.py"
Task: "T004–T006 card and check in backend/tests/test_exercises.py"

# Backend and frontend at once after the tests:
Task: "T010–T013 backend: srs.py, schemas.py, exercises.py, study_service.py"
Task: "T014–T018 frontend: types.ts, WritingCard.tsx, ExerciseView.tsx, RoundsRunner.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 2 (T001–T002)
2. Phase 3 (T003–T018). After this the new round works, and the card has no hint by construction
3. **STOP and VALIDATE**: `yarn test:api`, `yarn typecheck`, a manual walk through the session

### Incremental Delivery

US2 adds the server-side guarantee (`used_hint` is ignored) and the no-leak check. Per the constitution the whole feature goes into **one** commit (T027), because the API contract (`schemas.py` + `types.ts` + README + tests) must change together. Do not commit US1 separately.

---

## Notes

- [P] = different files, no dependencies on unfinished tasks
- There are no migrations. If `review_log.exercise` turns out to have a CHECK constraint, stop and add a migration per principle IV (research R2 says there is none)
- Do not add any setting to switch the exercise off (spec, Assumptions)
