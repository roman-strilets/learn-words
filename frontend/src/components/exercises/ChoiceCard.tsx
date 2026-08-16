import { useEffect, useState } from 'react'

import type { ChoiceExercise } from '../../api/types'
import { isTypingTarget, useHotkeys } from '../../hooks/useHotkeys'
import { useSpeech } from '../../speech/SpeechProvider'
import { Caption, Prompt, SpeakButton } from '../ui'
import type { ExerciseCardProps } from './types'

export function ChoiceCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<ChoiceExercise>) {
  const { speak, autoplay, supported } = useSpeech()
  const [usedHint, setUsedHint] = useState(false)
  const isEnToRu = exercise.type === 'choice_en_ru'

  useEffect(() => {
    setUsedHint(false)
    if (isEnToRu && autoplay) speak(exercise.prompt)
  }, [exercise.word_id, exercise.prompt, isEnToRu, autoplay, speak])

  useHotkeys(
    Object.fromEntries(
      exercise.options.map((option, index) => [
        String(index + 1),
        (event: KeyboardEvent) => {
          if (isTypingTarget(event.target)) return
          event.preventDefault()
          onAnswer({ answer: option, usedHint })
        },
      ]),
    ),
    !locked,
  )

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-8">
      <Caption>
        {isEnToRu ? 'Выберите перевод слова' : 'Выберите правильный вариант слова'}
      </Caption>

      <div className="flex items-center gap-4">
        <Prompt
          hint={exercise.hint}
          hintShown={usedHint}
          onHint={() => setUsedHint(true)}
        >
          {exercise.prompt}
        </Prompt>
        {isEnToRu ? (
          <SpeakButton onClick={() => speak(exercise.prompt)} disabled={!supported} />
        ) : null}
      </div>

      <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
        {exercise.options.map((option, index) => (
          <button
            key={option}
            type="button"
            disabled={locked}
            onClick={() => onAnswer({ answer: option, usedHint })}
            className="relative rounded-md border border-hairline px-6 py-6 text-center text-2xl text-ink transition-colors hover:border-accent hover:bg-accent/5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className="absolute top-2 left-3 text-sm text-muted">{index + 1}</span>
            {option}
          </button>
        ))}
      </div>
    </div>
  )
}
