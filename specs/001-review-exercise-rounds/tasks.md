---

description: "Task list for feature implementation"
---

# Tasks: Повторение раундами по типам упражнений

**Input**: Design documents from `/specs/001-review-exercise-rounds/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/study-api.md](./contracts/study-api.md)

**Tests**: включены и обязательны. Принцип III конституции требует теста на каждое
изменение SRS, генерации упражнений, проверки ответов и контракта API — тест идёт
в том же коммите, что и поведение.

**Organization**: задачи сгруппированы по пользовательским историям, чтобы каждую
можно было довести и проверить отдельно.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно делать параллельно (разные файлы, нет зависимостей)
- **[Story]**: к какой истории относится задача (US1, US2, US3)
- В описании указан точный путь к файлу

## Path Conventions

Веб-приложение из двух частей в одном репозитории: `backend/app/`, `backend/tests/`,
`backend/alembic/versions/`, `frontend/src/`. Пути даны от корня репозитория.

---

## Phase 1: Setup

**Purpose**: убедиться, что стенд поднимается и текущие ворота качества зелёные — иначе
непонятно, что сломала доработка

- [X] T001 Прогнать базовые ворота на чистом дереве: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests` — зафиксировать, что всё проходит до правок
- [ ] T002 Поднять стенд `yarn dev` и пройти одно занятие «Повторение» в текущем виде, чтобы было с чем сравнивать поведение после переделки

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: схема, контракт и чистое ядро, без которых ни одна история не собирается

**⚠️ CRITICAL**: ни одна пользовательская история не начинается, пока эта фаза не закрыта

- [X] T003 Добавить колонку `session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)` в модель `ReviewLog` в `backend/app/models.py` с комментарием «почему»: ключ занятия-повторения, по нему считается итог
- [X] T004 Создать миграцию Alembic в `backend/alembic/versions/` (`op.add_column` + `op.create_index("ix_review_log_session_id", ...)`, downgrade — `op.drop_index` + `op.drop_column` напрямую, без `batch_alter_table`), докстринг объясняет: что меняется и почему таблица не пересоздаётся (внешний ключ `review_log.word_id` ушёл бы на временную таблицу). Проверить `yarn db:upgrade` и `alembic downgrade -1`
- [X] T005 [P] Заменить в `backend/app/srs.py` взвешенный выбор упражнения на фиксированный порядок раундов: добавить `REVIEW_ROUNDS: tuple[ExerciseType, ...] = (CHOICE_RU_EN, CHOICE_EN_RU, LETTERS, DICTATION)`, удалить `REVIEW_EXERCISES`, `_REVIEW_WEIGHTS`, `_REVIEW_WEIGHTS_LATE`, `pick_review_exercise`; упростить `exercise_for` до шагов знакомства (после доработки её зовут только для `learning`)
- [X] T006 [P] Добавить в `backend/app/srs.py` чистую функцию `session_quality(...) -> int` — минимум из `derive_quality` по всем попыткам слова за занятие; без импортов SQLAlchemy и без обращения к времени (Принцип II)
- [X] T007 Обновить контракт в `backend/app/schemas.py` по [contracts/study-api.md](./contracts/study-api.md): добавить `ReviewRound`, `ReviewFinishRequest`, `ReviewFinishResult`; в `SessionOut` убрать `exercises`, добавить `session_id: str | None` и `rounds: list[ReviewRound]`; в `AnswerRequest` добавить `mode: SessionMode = SessionMode.LEARN` и `session_id: str | None` с валидатором «`review` без `session_id` — 422»
- [X] T008 Синхронизировать `frontend/src/api/types.ts` со `schemas.py`: `ReviewRound`, изменённый `SessionPayload` (`session_id`, `rounds`, без `exercises`), `AnswerPayload` с `mode` и `session_id`, `ReviewFinishResult`

**Checkpoint**: схема, чистое ядро и типы готовы — можно браться за истории

---

## Phase 3: User Story 1 — Раунд одного типа упражнения по всем словам (Priority: P1) 🎯 MVP

**Goal**: занятие «Повторение» идёт раундами: сервер отдаёт план из четырёх раундов,
клиент проходит их по очереди, в конце расписание пересчитывается один раз на слово

**Independent Test**: запустить повторение при 5 словах со сроком, отвечать только верно —
карточки идут группами по 5 одного типа; после финального экрана у каждого слова срок
сдвинулся в будущее ровно один раз

### Tests for User Story 1 ⚠️

> Тесты пишутся первыми и должны падать до реализации

- [X] T009 [P] [US1] Тест `session_quality` в `backend/tests/test_srs.py`: без ошибок и подсказок → 5; с подсказкой → 4; с повторной попыткой → 3; хотя бы одна ошибка → 2 (табличный `parametrize`)
- [X] T010 [P] [US1] Тест плана занятия в `backend/tests/test_api.py`: `GET /api/study/session?mode=review` отдаёт `session_id` и четыре раунда, в каждом по одному упражнению на каждое слово со сроком; при отсутствии слов — `rounds: []` и `session_id: null`
- [X] T011 [P] [US1] Тест в `backend/tests/test_api.py`: ответ с `mode=review` и `session_id` не меняет `progress` слова (`due_at`, `status`, `ease`, `lapses` те же), но добавляет строку в `review_log` с этим `session_id`
- [X] T012 [P] [US1] Тест в `backend/tests/test_api.py`: `POST /api/study/review/finish` после безошибочного прохождения всех четырёх раундов сдвигает срок слова в будущее ровно один раз (интервал совпадает с одним верным ответом до доработки — SC-005)
- [X] T013 [P] [US1] Тест в `backend/tests/test_api.py`: `finish` не трогает слово, не прошедшее все четыре раунда (FR-017a), а повторный вызов с тем же `session_id` не пересчитывает расписание второй раз
- [X] T014 [P] [US1] Тест в `backend/tests/test_api.py`: `mode=review` без `session_id` → 422; неизвестный `session_id` в `finish` → 200 с пустым списком

### Implementation for User Story 1

- [X] T015 [US1] Переписать `build_session` для режима `review` в `backend/app/study_service.py`: выдать `session_id` (`uuid4`), собрать по раунду на каждый тип из `REVIEW_ROUNDS` (`build_exercise(..., show_letters=True, rng=rng)` на каждое слово), вернуть `rounds` вместо `exercises`; режим `learn` не трогать
- [X] T016 [US1] Развести режимы в `answer_exercise` в `backend/app/study_service.py`: при `mode=review` проверить ответ, посчитать `quality`, записать `ReviewLog` с `session_id` — и не вызывать `apply_answer`/`write_state`; в ответе вернуть прежний `progress` без изменений (FR-013a)
- [X] T017 [US1] Реализовать `finish_review_session(session, session_id, now, rng)` в `backend/app/study_service.py`: сгруппировать `review_log` по `word_id` в пределах `session_id`, отобрать слова с верным ответом по каждому из `REVIEW_ROUNDS`, посчитать `session_quality`, один раз применить `apply_answer` и `write_state`, пропустить уже пересчитанные (`progress.updated_at >= max(created_at)` попыток занятия)
- [X] T018 [US1] Добавить маршрут `POST /study/review/finish` в `backend/app/routers/study.py` (тонкий: валидация, вызов сервиса, `utcnow()`), пробросить `mode` и `session_id` из `AnswerRequest` в `answer_exercise`
- [X] T019 [P] [US1] Добавить `finishReview(sessionId)` в `frontend/src/api/client.ts` и передачу `mode`/`session_id` в `api.answer`
- [X] T020 [P] [US1] Вынести переключатель карточек из `frontend/src/components/StudySession.tsx` в новый `frontend/src/components/exercises/ExerciseView.tsx` (без изменения поведения) и подключить его обратно в `StudySession.tsx`
- [X] T021 [US1] Создать `frontend/src/components/ReviewSession.tsx`: очередь текущего раунда, переход к следующему раунду после его опустошения, отправка ответов с `mode: 'review'` и `session_id`, вызов `finishReview` при завершении, отчёт `onFinished`
- [X] T022 [US1] Убрать инициализацию очереди из `session.exercises` в `frontend/src/components/StudySession.tsx` (поле удалено из контракта) — стартовая очередь режима «Изучение» становится пустой, поведение прежнее
- [X] T023 [US1] Развести раннеры по режиму в `frontend/src/pages/StudyPage.tsx`: `review` → `ReviewSession`, `learn` → `StudySession`; экраны «нечего повторять» и итог занятия оставить прежними

**Checkpoint**: занятие-повторение проходится раундами от начала до конца, расписание обновляется один раз на слово

---

## Phase 4: User Story 2 — Ошибка возвращает слово в тот же раунд (Priority: P1)

**Goal**: неверный ответ оставляет слово в текущем раунде до верного ответа, повторная
карточка собирается заново, следующий раунд не начинается раньше времени

**Independent Test**: ошибиться на одном слове в первом раунде — слово возвращается после
остальных карточек с тем же типом, но другими вариантами; второй раунд не стартует, пока
на него не ответят верно

### Tests for User Story 2 ⚠️

- [X] T024 [P] [US2] Тест в `backend/tests/test_exercises.py`: `build_exercise(..., attempt=2)` для `letters` даёт другой порядок банка букв, чем `attempt=1`, при той же маске и решении (FR-006a)
- [X] T025 [P] [US2] Тест в `backend/tests/test_api.py`: неверный ответ при `mode=review` возвращает `repeat_in_session=true` и `next_exercise` того же типа для того же слова; верный ответ возвращает `next_exercise: null`
- [X] T026 [P] [US2] Тест в `backend/tests/test_api.py`: после ошибки и последующего верного ответа в том же раунде `finish` засчитывает слово как забытое — статус `learning`, `lapses` +1, `due_at` не позже «сейчас» (FR-014, SC-006)

### Implementation for User Story 2

- [X] T027 [US2] Добавить сборку повторной карточки в `backend/app/study_service.py`: при `mode=review` и неверном ответе вернуть в `next_exercise` упражнение того же типа через `build_exercise(..., attempt=request.attempt + 1, rng=rng)`; при верном — `None`
- [X] T028 [US2] Реализовать в `frontend/src/components/ReviewSession.tsx` возврат слова в конец текущего раунда по `next_exercise` (FR-007) и запрет перехода к следующему раунду, пока очередь раунда не пуста (FR-008); повторов не ограничивать (FR-009)
- [X] T029 [US2] Вести в `frontend/src/components/ReviewSession.tsx` номер показа слова в раунде и отправлять `attempt = max(номер показа, промахи в буквах ? 2 : 1)` (решение D-6), со сбросом счётчика на границе раунда (FR-012a)
- [X] T030 [US2] Показать в `frontend/src/components/ReviewSession.tsx` счётчик оставшихся карточек, растущий при появлении повторов (FR-015)

**Checkpoint**: ошибка закрывается внутри своего раунда, повторная карточка каждый раз новая

---

## Phase 5: User Story 3 — Четыре типа упражнений в предсказуемом порядке (Priority: P2)

**Goal**: раунды идут строго `выбор рус→англ → выбор англ→рус → буквы → аудирование`,
карточка знакомства в повторении не встречается, пользователь видит номер раунда

**Independent Test**: пройти занятие целиком — типы идут в заданном порядке, каждое слово
встретилось в каждом из четырёх типов, всего карточек «слов × 4»

### Tests for User Story 3 ⚠️

- [X] T031 [P] [US3] Тест в `backend/tests/test_srs.py`: `REVIEW_ROUNDS` равен `(choice_ru_en, choice_en_ru, letters, dictation)` и не содержит `intro` (FR-004, FR-005)
- [X] T032 [P] [US3] Тест в `backend/tests/test_api.py`: порядок `exercise` в `rounds` ответа занятия совпадает с `REVIEW_ROUNDS`, а суммарное число упражнений равно «слов × 4» (SC-001, SC-002)

### Implementation for User Story 3

- [X] T033 [US3] Показать индикатор «Раунд N из 4» с названием текущего типа упражнения в `frontend/src/components/ReviewSession.tsx` (FR-016, SC-007)
- [X] T034 [P] [US3] Добавить подписи типов упражнений для индикатора (в `frontend/src/components/ReviewSession.tsx` или рядом с `frontend/src/components/StudyModeLinks.tsx`, если там уже живут ярлыки режимов) — тексты на русском

**Checkpoint**: состав и порядок раундов зафиксированы и видны пользователю

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T035 Обработать слово, выведенное из оборота во время занятия (FR-017): в `frontend/src/components/ReviewSession.tsx` убирать слово из оставшихся раундов по ответу `409`/`404`, не роняя очередь; в `backend/app/study_service.py` проверить, что `finish` пропускает слово без прогресса
- [X] T036 [P] Обновить в `README.md` раздел «Повторения (SM-2)»: раунды по типам упражнений, повтор после ошибки, одно обновление расписания за занятие, откат при любой ошибке
- [X] T037 [P] Обновить в `README.md` раздел «API»: новый `POST /api/study/review/finish`, изменившийся ответ `GET /api/study/session?mode=review`, поля `mode` и `session_id` в `POST /api/study/answer`
- [X] T038 Прогнать ворота качества: `yarn test:api`, `yarn typecheck`, `yarn build`, `uv run --directory backend ruff check app tests`
- [X] T039 Пройти четыре сценария ручной проверки из [quickstart.md](./quickstart.md), включая сценарий 4 — режим «Изучение» не задет (FR-018)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: без зависимостей
- **Foundational (Phase 2)**: после Setup; БЛОКИРУЕТ все истории
- **US1 (Phase 3)**: после Phase 2
- **US2 (Phase 4)**: после Phase 3 — повтор внутри раунда работает только там, где раунды уже есть
- **US3 (Phase 5)**: после Phase 3; с US2 не пересекается (можно параллельно с Phase 4)
- **Polish (Phase 6)**: после нужных историй

### User Story Dependencies

- **US1 (P1)**: самостоятельна после Phase 2 — это MVP
- **US2 (P1)**: опирается на раннер раундов из US1 (T021); тесты T024 и реализация T027 на бэкенде от US2-фронта не зависят
- **US3 (P2)**: опирается на раннер раундов из US1 (T021); проверка порядка (T031, T032) не зависит вообще ни от чего, кроме T005

### Within Each User Story

- Тесты пишутся первыми и должны падать
- Чистое ядро (`srs.py`) → сервис (`study_service.py`) → роутер (`routers/study.py`) → клиент (`api/`) → компоненты
- История доводится до чекпоинта прежде, чем начинается следующая

### Parallel Opportunities

- **Phase 2**: T005 и T006 — разные функции одного файла, делаются подряд; T003+T004 (схема) параллельны T005/T006
- **US1**: тесты T009–T014 пишутся параллельно; T019 и T020 (фронт) параллельны серверным T015–T018
- **US2**: тесты T024–T026 параллельны; T027 (сервер) параллелен T028–T030 (фронт)
- **US3**: T031 и T032 параллельны; можно вести целиком параллельно с Phase 4
- **Polish**: T036 и T037 — разные разделы README, но один файл: делать подряд, чтобы не ловить конфликт

---

## Parallel Example: User Story 1

```bash
# Тесты US1 пишутся вместе:
Task: "Тест session_quality в backend/tests/test_srs.py"
Task: "Тест плана занятия в backend/tests/test_api.py"
Task: "Тест «ответ review не меняет progress» в backend/tests/test_api.py"
Task: "Тест finish: одно обновление расписания в backend/tests/test_api.py"

# Фронтовые заготовки параллельно серверу:
Task: "finishReview в frontend/src/api/client.ts"
Task: "Вынести ExerciseView в frontend/src/components/exercises/ExerciseView.tsx"
```

---

## Implementation Strategy

### MVP (только US1)

1. Phase 1 → Phase 2 → Phase 3
2. **Остановиться и проверить**: занятие идёт раундами, расписание обновляется один раз
3. Уже в этом виде режим работоспособен: ошибка просто не возвращает слово в раунд

### Инкрементальная доводка

1. Setup + Foundational → фундамент готов
2. US1 → проверить сценарий 1 из quickstart → MVP
3. US2 → проверить сценарий 2 (ошибка и повтор)
4. US3 → проверить сценарий 1 на порядок типов и индикатор
5. Polish → README, ворота, сценарии 3 и 4

### Порядок коммитов

Один коммит — одно законченное изменение. Изменение контракта API (T007, T008, T018)
идёт одним коммитом со своими тестами и разделом README, как требует конституция.

---

## Notes

- `[P]` — разные файлы, нет зависимостей
- Правило конституции: тест на новое поведение пишется в том же коммите
- `srs.py` обязан остаться без SQLAlchemy и без обращения к системному времени
- Комментарии, докстринги и тексты интерфейса — на русском; идентификаторы и сообщения коммитов — на английском
- Перед каждым коммитом: `yarn test:api`, `yarn typecheck`, `yarn build`, `ruff check`
