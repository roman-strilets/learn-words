---
description: "Task list for feature implementation"
---

# Tasks: Случайный порядок слов в каждом раунде

**Input**: Design documents from `/specs/004-shuffle-round-words/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/study-api.md](./contracts/study-api.md),
[quickstart.md](./quickstart.md)

**Tests**: обязательны. По принципу III конституции любое изменение генерации упражнений
ДОЛЖНО сопровождаться тестом в `backend/tests/` в том же коммите. На фронте тест-раннера
нет, поэтому фронтовые задачи проверяются через `yarn typecheck`, `yarn build`
и ручные сценарии [quickstart.md](./quickstart.md).

**Organization**: задачи сгруппированы по пользовательским историям. Фазы задают
порядок работы. Вся доработка ложится одним коммитом вместе с README (принцип V).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (другой файл, нет зависимостей)
- **[Story]**: к какой истории относится задача (US1, US2)
- В описании указан точный путь к файлу

## Path Conventions

Веб-приложение: `backend/app/`, `backend/tests/`, `frontend/src/`. Новый файл один:
`frontend/src/lib/roundOrder.ts`.

---

## Phase 1: Setup

**Purpose**: убедиться, что стартуем с зелёных ворот

- [X] T001 Прогнать `yarn test:api`, `yarn typecheck`, `yarn build` и `uv run --directory backend ruff check app tests` из корня репозитория и зафиксировать, что всё зелёное до начала правок

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: чистая функция порядка раунда на сервере и её фронтовый двойник. На них
опираются обе истории.

**⚠️ CRITICAL**: без этой фазы истории не начать

- [X] T002 Написать табличные тесты `order_round` в `backend/tests/test_exercises.py` (импорт `from app.exercises import order_round`). Функция работает с любыми элементами; в тестах это `int`, `key` по умолчанию — тождество. Сценарии:
  - (а) `n = 0` и `n = 1` возвращают вход без изменений;
  - (б) для `n ∈ {2, 3, 5}` на семенах `random.Random(seed)`, `seed in range(200)`, при `previous = list(range(n))` и `last = previous[-1]` результат — перестановка входа, `!= previous`, а при `n ≥ 3` `result[0] != last`;
  - (в) при `n = 2` и `last = previous[-1]` результат равен `previous[::-1]`: приоритет FR-003 над FR-004 (FR-005);
  - (г) `previous=None, last=None` — первый раунд: только перестановка без ограничений;
  - (д) на 1 000 вызовах с `n = 5`, `previous=None` и одним `random.Random(0)` доля каждого элемента на первой позиции от 15 % до 25 % (SC-003).

  Тесты должны падать до T003.
- [X] T003 Реализовать `order_round(items, previous, last, rng, key=lambda x: x)` в `backend/app/exercises.py`, в секции рядом с `build_letter_bank`:
  - копия `items` в порядке `rng.shuffle`;
  - если `previous is None` или `len < MIN_WORDS_TO_REORDER` (=2), вернуть её;
  - иначе из кандидатов `[q, swap(0,1), rotate_left(1), swap(1,2)]` (последний — только при `len ≥ 3`) вернуть первый, у которого `[key(x) for x in c] != [key(x) for x in previous]` и, при `len ≥ MIN_WORDS_TO_AVOID_REPEAT` (=3) и `last is not None`, `key(c[0]) != key(last)`.

  Константы заводятся на уровне модуля с комментарием «почему» (принцип II). В комментарии сказать, что это следствие FR-003 и FR-004, а не настройка, поэтому в `app/config.py` константы не выносятся. Докстринг на русском объясняет, почему четырёх кандидатов всегда хватает (research.md R2), и что при 2 словах важнее FR-003. Если ни один кандидат не подошёл, это ошибка в логике: `raise AssertionError` с пояснением. После этого T002 зелёный.
- [X] T004 [P] Создать `frontend/src/lib/roundOrder.ts` с экспортом `arrangeRound<T extends { word_id: number }>(items: T[], previous: number[] | null, lastWordId: number | null): T[]`. Та же процедура кандидатов, что в T003, но без перемешивания:
  - кандидаты `[items, swap(0,1), rotateLeft, swap(1,2)]`;
  - сравнение по `word_id` с `previous`;
  - при `items.length ≥ 3` первый `word_id` не равен `lastWordId`;
  - при `previous === null` или `items.length < 2` — вернуть `items`;
  - если кандидат не найден — вернуть `items` (на фронте не падаем, занятие важнее).

  Константы `MIN_WORDS_TO_REORDER = 2`, `MIN_WORDS_TO_AVOID_REPEAT = 3` с русскими комментариями и ссылкой на серверную `order_round` («алгоритм общий, тесты — на сервере»). Кандидаты и порядок их перебора должны буквально совпадать с T003: гарантию «кандидатов всегда хватает» доказывают только для этого набора. Не мутировать вход.

**Checkpoint**: `yarn test:api` и `yarn typecheck` зелёные, функции пока нигде не вызываются

---

## Phase 3: User Story 1 — Каждый раунд перемешан заново (Priority: P1) 🎯 MVP

**Goal**: порядок слов в каждом раунде случайный и отличается от предыдущего раунда,
в обоих режимах, включая случай, когда слово выбыло посреди занятия.

**Independent Test**: занятие из 5 слов без ошибок. Порядок ни одного раунда не
повторяет предыдущий, а первый раунд меняется от перезагрузки к перезагрузке
(quickstart.md, сценарии 1–3, 6).

### Tests for User Story 1

- [X] T005 [US1] В `backend/tests/test_api.py` перевести на сравнение отсортированных списков два утверждения, которые после T008 упадут. Проверка «каждое слово ровно по разу» сохраняется, но порядок больше не фиксирован (FR-006):
  - в `test_learn_rounds_cover_every_word_in_every_type` (строка ~831) `assert [e["word_id"] for e in round_["exercises"]] == started` → `assert sorted(e["word_id"] for e in round_["exercises"]) == sorted(started)`;
  - в `test_learn_rounds_skip_words_that_left_the_rotation` (строка ~851) `assert [e["word_id"] for e in round_["exercises"]] == alive` → `assert sorted(e["word_id"] for e in round_["exercises"]) == sorted(alive)`.
- [X] T006 [US1] Добавить в `backend/tests/test_api.py`, в секцию «занятие-повторение раундами», тест `test_review_rounds_differ_in_order`:
  - `started = _start(client)`, затем `_session(client, "review")`. `_release` не нужен: слова на стадии изучения тоже попадают в повторение, как в `test_review_session_is_a_plan_of_four_rounds`. Фикстуры — `client` и `words`;
  - для каждой пары соседних раундов `[e["word_id"] for e in ...]` различаются;
  - в каждом раунде `sorted(ids) == sorted(started)` (FR-003, FR-006, контракт, гарантии 1 и 3).
- [X] T007 [US1] Добавить в `backend/tests/test_api.py`, в секцию «занятие-изучение раундами», тест `test_learn_rounds_differ_in_order`:
  - `_learn_session(client)`, затем `_rounds(client, started)` — соседние раунды различаются по порядку;
  - `_rounds(client, started[:2])` — у двух слов соседние раунды чередуют два порядка: `rounds[k] == rounds[k-1][::-1]` по `word_id` (FR-005, quickstart).

### Implementation for User Story 1

- [X] T008 [US1] В `backend/app/study_service.py` переписать `_rounds_for`:
  - вместо одного списочного выражения — цикл по `EXERCISE_ROUNDS`;
  - порядок слов каждого раунда: `order_round(words, previous, None, rng, key=lambda w: w.id)`, где `previous` — порядок слов предыдущего раунда (`None` для первого);
  - упражнения строятся через `build_exercise` в полученном порядке.

  Импортировать `order_round` из `app.exercises`. Обновить докстринг: порядок слов в каждом раунде свой, а план общий для `review` и `/study/rounds`. T005–T007 зелёные.
- [X] T009 [US1] В `frontend/src/components/RoundsRunner.tsx`:
  - добавить состояние `roundOrder: number[]`, инициализированное `rounds[0]?.exercises.map((e) => e.word_id) ?? []`;
  - в эффекте смены раунда отфильтровать `rounds[next].exercises` от `dropped`, вызвать `arrangeRound(filtered, roundOrder.filter((id) => !gone.has(id)), null)` из `../lib/roundOrder`, положить результат в `queue` и его `word_id` — в `roundOrder`;
  - добавить `roundOrder` в зависимости эффекта;
  - дописать в JSDoc компонента абзац о том, зачем фронту поправлять серверный порядок: выбывшее слово может сделать два разных плана одинаковыми (research.md R3).

  Повторы после ошибки в `roundOrder` не попадают: `advance` не трогать.

**Checkpoint**: `yarn test:api`, `yarn typecheck` и `yarn build` зелёные. Сценарии 1–3 и 6 из quickstart.md проходят вручную.

---

## Phase 4: User Story 2 — Одно слово не показывается дважды подряд на стыке раундов (Priority: P2)

**Goal**: первое слово раунда не совпадает со словом, показанным последним
в предыдущем раунде, даже если последним был повтор после ошибки. Правило действует
при 3 словах и больше.

**Independent Test**: в раунде из 5 слов ошибиться на одном слове и исправить его
последним. Следующий раунд начинается с другого слова (quickstart.md, сценарии 4–5).

### Tests for User Story 2

- [X] T010 [US2] Расширить `test_review_rounds_differ_in_order` и `test_learn_rounds_differ_in_order` в `backend/tests/test_api.py`: при 3 словах и больше `rounds[k]["exercises"][0]["word_id"] != rounds[k-1]["exercises"][-1]["word_id"]` для `k = 1..3` (FR-004, контракт, гарантия 4). Для надёжности собрать план 20 раз подряд (`_session` или `_rounds` в цикле) и проверить гарантию на каждом. Падает до T011.

### Implementation for User Story 2

- [X] T011 [US2] В `_rounds_for` в `backend/app/study_service.py` передавать `last=previous[-1] if previous else None` вместо `None`. T010 зелёный.
- [X] T012 [US2] В `frontend/src/components/RoundsRunner.tsx`:
  - добавить состояние `lastWordId: number | null` (начально `null`);
  - в `advance` до сдвига очереди записывать `setLastWordId(current.word_id)`: `current` взять из `queue[0]`, добавить в зависимости `useCallback`;
  - в эффекте смены раунда передавать `lastWordId` третьим аргументом `arrangeRound` вместо `null`;
  - в `onError` ветки выбывшего слова (`isGone`) `lastWordId` не трогать: выбывшего слова в следующем раунде нет, поэтому оставшееся значение ничего не ломает;
  - комментарий: сервер знает только запланированный конец раунда, а последним мог оказаться повтор после ошибки (FR-004, research.md R3).

**Checkpoint**: `yarn test:api`, `yarn typecheck` и `yarn build` зелёные. Сценарии 4–5 из quickstart.md проходят вручную.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T013 [P] Обновить `README.md`:
  - в разделе «Занятие идёт раундами» после абзаца «В раунде проходятся все слова занятия…» добавить, что порядок слов в каждом раунде случайный и не повторяет предыдущий раунд, а при 3 словах и больше раунд не начинается со слова, показанного последним;
  - в разделе API, в абзаце про `rounds`, добавить, что порядок `exercises` в раундах перемешан, клиент не должен полагаться на его стабильность, и перечислить гарантии из `specs/004-shuffle-round-words/contracts/study-api.md`.
- [ ] T014 Прогнать ворота из корня: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests`. Всё должно быть зелёным.
- [ ] T015 Пройти ручные сценарии 1–7 из `specs/004-shuffle-round-words/quickstart.md` в `yarn dev`, включая SC-005: «Осталось карточек: 20» в начале первого раунда занятия из 5 слов.
- [X] T016 Самопроверка по вопросам ревью из конституции:
  - сервер проверяет ответы, а не клиент;
  - `srs.py` не тронут;
  - тесты на новое поведение есть;
  - миграция не нужна;
  - README обновлён.

  Затем один коммит с заголовком `Shuffle the word order in every exercise round` и телом «наблюдение → причина → решение», с трейлером Co-Authored-By.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: без зависимостей
- **Foundational (T002–T004)**: после Setup; T002 → T003; T004 параллельно с T002–T003. Блокирует обе истории
- **US1 (T005–T009)**: после Foundational
- **US2 (T010–T012)**: после US1. Правит те же места (`_rounds_for`, эффект смены раунда), что US1 создаёт
- **Polish (T013–T016)**: T013 можно делать в любой момент после T003; T014–T016 — после всех историй

### Within Each Story

- Тесты (T005–T007, T010) пишутся до реализации и падают. Исключение — T005: это правка теста, который реализация иначе сломает
- T005, T006 и T007 правят один файл `backend/tests/test_api.py`, поэтому идут последовательно, без [P]
- T008 (бэкенд) и T009 (фронт) — разные файлы, но T009 проверяется вручную только на плане, который перемешивает T008, поэтому порядок T008 → T009

### Parallel Opportunities

- T004 (фронт) параллельно с T002–T003 (бэкенд)
- T013 (README) параллельно с любой задачей после T003

---

## Parallel Example: Foundational

```bash
# Бэкенд и фронтовый двойник функции порядка — независимо:
Task: "T002–T003: тесты и order_round в backend/app/exercises.py"
Task: "T004: arrangeRound в frontend/src/lib/roundOrder.ts"
```

## Parallel Example: User Story 1

```bash
# После T008 документацию можно писать параллельно с фронтом:
Task: "T009: roundOrder и arrangeRound в frontend/src/components/RoundsRunner.tsx"
Task: "T013: README — порядок слов в раундах и гарантии API"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001: ворота зелёные
2. T002–T004: функции порядка
3. T005–T009: раунды перемешаны и отличаются друг от друга
4. **STOP and VALIDATE**: quickstart.md, сценарии 1–3 и 6. Этого уже достаточно, чтобы
   жалоба «слова идут в одном и том же порядке» была закрыта

### Incremental Delivery

1. MVP (US1). После него слово на стыке раундов изредка может повториться:
   примерно в 1 из 5 стыков при 5 словах
2. US2 убирает этот случай, в том числе после повтора из-за ошибки
3. Polish: README, ворота, ручная проверка, один коммит

---

## Notes

- `srs.py`, модели, миграции, `schemas.py` и `frontend/src/api/types.ts` не меняются. Если
  по ходу понадобилось их тронуть, это сигнал, что реализация ушла от плана
- Порядок карточек знакомства (`new_words`) не меняется (FR-010)
- Повторы после ошибки остаются в конце очереди (FR-008): `advance` меняется только
  записью `lastWordId`
