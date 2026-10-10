# API Contract: Упражнение «Напишите слово по-английски»

Новых маршрутов нет. Меняются состав объединения `Exercise` и число раундов в плане
занятия.

## Объединение `Exercise` — новый вариант

```json
{
  "type": "writing_ru_en",
  "word_id": 42,
  "prompt": "нож"
}
```

Других полей нет. В частности, нет `hint`, `solution`, `mask` и `audio_text`:
ответ в браузер до проверки не уходит.

## Планы занятия — пять раундов

`POST /api/study/session` (режим `review`) и `POST /api/study/rounds` (режим `learn`)
возвращают `rounds` в порядке:

| # | `exercise` |
|---|---|
| 1 | `choice_ru_en` |
| 2 | `choice_en_ru` |
| 3 | `letters` |
| 4 | `writing_ru_en` |
| 5 | `dictation` |

Гарантии порядка слов внутри раунда — прежние (README, раздел «API»), и действуют
они на всех пяти стыках.

## `POST /api/study/answer`

- `exercise: "writing_ru_en"` принимается. Неизвестный тип по-прежнему даёт 422.
- `correct` — сравнение `answer` с английским словом по общим правилам нормализации.
  Пустой или отсутствующий `answer` даёт `false`.
- `correct_answer` — английское слово.
- `used_hint` для этого типа игнорируется: в журнал пишется `false`, оценка
  не снижается.
- При `correct: false` `next_exercise` — карточка `writing_ru_en` того же слова.

## `POST /api/study/finish`

Расписание пересчитывается только для слов, у которых в журнале занятия есть ответы во
всех пяти раундах. Слово, ответившее только на четыре прежних раунда, расписание
не сдвигает.

## TypeScript (`frontend/src/api/types.ts`)

```ts
export type ExerciseType = ... | 'writing_ru_en' | 'dictation'

export interface WritingRuEnExercise {
  type: 'writing_ru_en'
  word_id: number
  prompt: string
}

export type Exercise = ChoiceExercise | LettersExercise | WritingRuEnExercise | DictationExercise
```
