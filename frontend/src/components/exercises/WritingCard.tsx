import { useEffect, useRef, useState } from 'react'

import type { WritingRuEnExercise } from '../../api/types'
import { Caption, Prompt } from '../ui'
import type { ExerciseCardProps } from './types'

export function WritingCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<WritingRuEnExercise>) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setValue('')
    inputRef.current?.focus()
  }, [exercise.word_id])

  // Подсказки нет: вспомнить слово по переводу без опоры — и есть задание
  const submit = () => {
    if (locked) return
    onAnswer({ answer: value, usedHint: false })
  }

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-8">
      <Caption>Напишите слово по-английски</Caption>

      <Prompt>{exercise.prompt}</Prompt>

      <input
        ref={inputRef}
        value={value}
        disabled={locked}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="Напишите слово"
        // Браузерная автоподстановка — тоже подсказка
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        className="w-full max-w-xl rounded bg-panel px-6 py-5 text-center text-3xl text-ink outline-none placeholder:text-muted focus:ring-2 focus:ring-accent"
      />
      <p className="-mt-4 text-sm text-muted">Введите слово и нажмите Enter</p>
    </div>
  )
}
