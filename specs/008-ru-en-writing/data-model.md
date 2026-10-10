# Data Model: Упражнение «Напишите слово по-английски»

Таблицы и миграции не меняются (research R2). Меняются перечисление и схема карточки.

## ExerciseType (перечисление)

`backend/app/models.py`, `frontend/src/api/types.ts`

| Значение | Было | Стало |
|---|---|---|
| `intro` | ✓ | ✓ |
| `choice_ru_en` | ✓ | ✓ |
| `choice_en_ru` | ✓ | ✓ |
| `letters` | ✓ | ✓ |
| `writing_ru_en` | — | **новое** |
| `dictation` | ✓ | ✓ |

В базе значение хранится строкой в `review_log.exercise` (`String(24)`).

## EXERCISE_ROUNDS (порядок раундов)

`backend/app/srs.py`

```text
choice_ru_en → choice_en_ru → letters → writing_ru_en → dictation
```

Используется для плана занятия и для правила «расписание двигается, только если слово
ответило в каждом раунде» (FR-008).

## WritingRuEnExercise (карточка)

| Поле | Тип | Значение |
|---|---|---|
| `type` | `"writing_ru_en"` | дискриминатор объединения `Exercise` |
| `word_id` | int | слово карточки |
| `prompt` | str | `Word.translation` целиком, включая слитые значения |

Правила:
- В карточке нет ни ответа, ни подсказки (FR-003, research R4).
- Повтор после ошибки строит ту же карточку (research R7).

## ReviewLog (запись попытки) — без изменений схемы

Для `exercise = writing_ru_en`:
- `correct` = `normalize_answer(answer) == normalize_answer(word.word)`;
- `used_hint` всегда `false` (research R6);
- `quality` = `derive_quality(correct, used_hint=False, attempt)`: 5 с первой попытки,
  3 со второй и дальше, 2 при ошибке.
