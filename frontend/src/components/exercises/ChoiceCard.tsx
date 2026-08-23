import type { ChoiceExercise } from '../../api/types'
import { isTypingTarget, useHotkeys } from '../../hooks/useHotkeys'
import { useSpeakOnce, useSpeech } from '../../speech/SpeechProvider'
import { Caption, Prompt, SpeakButton } from '../ui'
import type { ExerciseCardProps } from './types'

export function ChoiceCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<ChoiceExercise>) {
  const { speak, autoplay, supported } = useSpeech()
  const isEnToRu = exercise.type === 'choice_en_ru'

  useSpeakOnce(exercise.prompt, isEnToRu && autoplay)

  // Подсказки здесь нет: варианты уже на экране, поэтому usedHint всегда false
  useHotkeys(
    Object.fromEntries(
      exercise.options.map((option, index) => [
        String(index + 1),
        (event: KeyboardEvent) => {
          if (isTypingTarget(event.target)) return
          event.preventDefault()
          onAnswer({ answer: option, usedHint: false })
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
        <Prompt>{exercise.prompt}</Prompt>
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
            onClick={() => onAnswer({ answer: option, usedHint: false })}
            className="group relative flex cursor-pointer items-center justify-center rounded-2xl border border-hairline bg-white px-12 py-7 text-center text-2xl font-medium text-ink shadow-sm transition duration-200 ease-out hover:-translate-y-0.5 hover:border-accent hover:bg-accent/5 hover:text-accent hover:shadow-lg focus-visible:border-accent focus-visible:ring-4 focus-visible:ring-accent/20 focus-visible:outline-none active:translate-y-0 active:scale-[0.99] disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none"
          >
            <span className="absolute top-3 left-3 flex size-7 items-center justify-center rounded-lg bg-hairline/60 text-sm font-semibold text-muted transition-colors duration-200 group-hover:bg-accent group-hover:text-white">
              {index + 1}
            </span>
            {option}
          </button>
        ))}
      </div>
    </div>
  )
}
