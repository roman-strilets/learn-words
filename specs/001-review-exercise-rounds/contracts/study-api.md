# Contract — `/api/study` после переделки режима «Повторение»

**Feature**: [../spec.md](../spec.md) | **Date**: 2026-08-29

Все маршруты под префиксом `/api`, ошибки — с человекочитаемым `detail`.
Изменения контракта обязаны в одном коммите затронуть `schemas.py`, роутер,
`backend/tests/test_api.py`, `frontend/src/api/types.ts` и раздел «API» в README.

---

## `GET /api/study/session?mode=review`

Возвращает полный план занятия: идентификатор занятия и четыре раунда с готовыми
упражнениями.

**Response 200** — `SessionOut`:

```jsonc
{
  "mode": "review",
  "session_id": "0f4b…-…-…",        // null в режиме learn
  "new_words": [],                   // заполняется только в режиме learn
  "rounds": [                        // заполняется только в режиме review
    {
      "exercise": "choice_ru_en",
      "exercises": [ /* по одному Exercise на каждое слово занятия */ ]
    },
    { "exercise": "choice_en_ru", "exercises": [ /* … */ ] },
    { "exercise": "letters",      "exercises": [ /* … */ ] },
    { "exercise": "dictation",    "exercises": [ /* … */ ] }
  ],
  "counts": { "new": 0, "learning": 2, "review_due": 3, "in_study": 120 }
}
```

Правила:
- Порядок раундов фиксирован: `choice_ru_en`, `choice_en_ru`, `letters`, `dictation`.
- Внутри раунда порядок упражнений совпадает с порядком отбора слов (по `due_at`);
  во всех раундах он одинаков — перемешивание делает клиент, если захочет.
- Слов к повторению нет → `rounds: []`, `session_id: null`.
- `mode=learn` не меняется: `new_words` заполнены, `rounds` пуст, `session_id` — `null`.

**Ломающее изменение**: поле `exercises` на верхнем уровне `SessionOut` удалено —
его заменили `rounds`.

---

## `POST /api/study/answer`

**Request** — `AnswerRequest`:

```jsonc
{
  "word_id": 42,
  "exercise": "letters",
  "answer": "budge",
  "used_hint": false,
  "attempt": 1,               // номер показа слова в текущем раунде
  "duration_ms": 4210,
  "mode": "review",           // новое поле, по умолчанию "learn"
  "session_id": "0f4b…"       // новое поле, обязательно при mode = "review"
}
```

**Response 200** — `AnswerResponse` (структура прежняя, меняется наполнение при `mode = review`):

| Поле | Поведение при `mode = "review"` |
|---|---|
| `correct`, `correct_answer`, `word`, `translation`, `example`, `example_translation` | Как раньше |
| `quality` | Оценка этой попытки — в журнал; на расписание сейчас не влияет |
| `repeat_in_session` | `true`, если ответ неверный: слово останется в текущем раунде |
| `next_exercise` | При неверном ответе — карточка того же типа, собранная заново (`attempt + 1`); при верном — `null` |
| `progress` | Прогресс слова **без изменений**: расписание в занятии не трогается |

Ошибки:
- `404` — слова нет.
- `409` — слово не взято в изучение (`WordNotInStudyError`), как раньше.
- `422` — `mode = "review"` без `session_id`.

При `mode = "learn"` поведение полностью прежнее: расписание пересчитывается сразу,
`next_exercise` отдаёт следующий шаг знакомства.

---

## `POST /api/study/review/finish`

Завершение занятия-повторения: сервер сам разбирает журнал занятия и один раз
пересчитывает расписание каждого слова, прошедшего все четыре раунда.

**Request** — `ReviewFinishRequest`:

```jsonc
{ "session_id": "0f4b…" }
```

**Response 200** — `list[ReviewFinishResult]`:

```jsonc
[
  {
    "word_id": 42,
    "mistakes": 0,
    "quality": 5,
    "progress": { "status": "review", "step": 4, "repetitions": 3,
                  "ease": 2.6, "interval_days": 7.8,
                  "due_at": "2026-09-06T10:12:00", "lapses": 0 }
  },
  {
    "word_id": 77,
    "mistakes": 1,
    "quality": 2,
    "progress": { "status": "learning", "step": 1, "repetitions": 0,
                  "ease": 2.3, "interval_days": 0.0,
                  "due_at": "2026-08-29T10:12:00", "lapses": 3 }
  }
]
```

Правила:
- В ответ попадают только слова, у которых в этом занятии есть верный ответ по
  **каждому** из четырёх типов упражнений. Незавершённые слова не упоминаются и
  не меняются.
- Оценка выводится сервером из `review_log` по `session_id`; клиент не присылает
  ни `quality`, ни признак ошибки.
- Идемпотентность: повторный вызов с тем же `session_id` не должен пересчитывать
  расписание второй раз — слова, чей прогресс уже обновлён после последней попытки
  занятия (`progress.updated_at >= максимальный created_at попыток занятия`),
  пропускаются.
- Неизвестный `session_id` — `200` с пустым списком, а не `404`: занятие, в котором
  не было ни одного ответа, — не ошибка.

---

## Что не меняется

`GET /api/study/new`, `POST /api/study/select`, `POST /api/study/reset/{word_id}`,
все маршруты `/api/words` и `/api/stats` остаются прежними. Режим «Изучение»
проходит по тем же путям, что и до доработки (FR-018).
