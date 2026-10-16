# API Contract: занятие по группе

Маршруты слов, фраз, меток, обычных занятий и статистики не меняются. Новые
маршруты — под `/api/group-study`, схемы — в `backend/app/schemas.py` и синхронно в
`frontend/src/api/types.ts`. Ошибки — человекочитаемый `detail`: 404 «Метка не
найдена» / «Слово не найдено», 409 «Слова больше нет в группе», 422 неверное значение.

```
GET    /api/group-study/groups                      → GroupOut[]
POST   /api/group-study/session                     {label_id} → GroupSessionOut (404)
POST   /api/group-study/answer                      GroupAnswerRequest → GroupAnswerResponse (404, 409, 422)
POST   /api/group-study/finish                      {session_id} → GroupFinishResult[]
POST   /api/group-study/groups/{label_id}/restart   → 204 (404)
```

## `GET /groups` — выбор группы

Все метки слов по алфавиту (тот же порядок, что `GET /api/labels`), включая метки
без слов. Только чтение: строк круга не создаёт.

```ts
GroupOut {
  label_id: number
  name: string
  word_count: number   // члены группы в любом статусе
  done: number         // пройдено в текущем круге, 0..word_count
  cycle: number        // номер текущего круга; 0 — круга ещё не было
}
```

- `done == word_count` при `word_count > 0` — круг пройден целиком, следующее
  занятие начнёт новый.
- Метки фраз здесь не появляются (FR-020).

## `POST /session` — порция группы

```ts
GroupSessionRequest { label_id: number }

GroupSessionOut {
  label_id: number
  name: string
  session_id: string | null   // null — в группе нет слов, занятия нет
  rounds: ExerciseRound[]     // те же пять раундов, что у повторения; [] при session_id = null
  word_count: number          // размер группы после сборки
  done: number                // пройдено в текущем круге до этого занятия
  cycle: number               // текущий круг после сборки
}
```

- Порция — до `GROUP_WORDS_PER_SESSION` слов по правилам data-model.md
  («Переходы при сборке порции»), без дневного лимита (FR-007). Порядок слов в
  раундах — `_rounds_for`, как у повторения: каждый раунд перемешан и не
  повторяет предыдущий.
- Знакомства нет: `new_words` в ответе нет, первый раунд — `choice_ru_en`.
- Варианты ответа — из всего словаря слов (FR-004a).
- Запрос создаёт строки круга, но повтор без `finish` между ними даёт ту же
  порцию (набор слов; порядок в раундах — новый).
- 404, если метки нет.

## `POST /answer` — ответ на карточку

```ts
GroupAnswerRequest {
  word_id: number
  label_id: number
  session_id: string
  exercise: ExerciseType      // кроме intro — 422
  answer: string | null
  used_hint: boolean
  attempt: number             // ≥ 1
  duration_ms: number | null  // ≥ 0
}

GroupAnswerResponse {
  correct: boolean
  correct_answer: string
  word: string
  translation: string
  example: string | null
  example_translation: string | null
  quality: number
  repeat_in_session: boolean
  next_exercise: Exercise | null   // пересобранная карточка того же типа после ошибки
}
```

- Проверяет сервер (`check_answer`), попытка пишется в `group_review_log`.
- `progress`, `review_log`, статус, расписание и отметка «Учить первым» не
  читаются и не меняются (FR-006). Слово без прогресса (новое) — обычный случай.
- 404 — нет слова или метки; 409 — слово больше не в группе (метку сняли посреди
  занятия): фронт убирает слово из оставшихся раундов, как в обычном занятии.

## `POST /finish` — итог порции

```ts
GroupFinishRequest { session_id: string }

GroupFinishResult {
  word_id: number
  mistakes: number   // неверных ответов за занятие
}
```

- Слова, верно ответившие во всех пяти раундах, отмечаются пройденными в своём
  круге (data-model.md, «Переход при `finish`»). Список — только такие слова.
- Идемпотентен: повтор с тем же ключом возвращает те же слова и ничего не меняет.
- Неизвестный ключ — пустой список, не ошибка.

## `POST /groups/{label_id}/restart` — начать круг заново

- Начинает новый круг в новом порядке; `done` у группы становится 0.
- Прогресс слов и журнал не трогает (FR-018). 404, если метки нет; группа без слов —
  204 без изменений.

## Что не меняется

`GET /api/stats/*`, `GET /api/study/session`, `POST /api/study/finish` ведут себя как
раньше: `group_review_log` они не читают (FR-008, FR-010, SC-002).
