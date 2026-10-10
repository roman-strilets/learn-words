import type { Exercise } from '../../api/types'
import { ChoiceCard } from './ChoiceCard'
import { DictationCard } from './DictationCard'
import { LettersCard } from './LettersCard'
import { WritingCard } from './WritingCard'
import type { AnswerSubmit } from './types'

interface Props {
  exercise: Exercise
  onAnswer: (submit: AnswerSubmit) => void
  /** Ответ уже отправлен — блокируем повторные нажатия */
  locked: boolean
}

/** Переключатель карточек по типу упражнения — общий для обоих режимов занятия. */
export function ExerciseView({ exercise, onAnswer, locked }: Props) {
  switch (exercise.type) {
    case 'choice_ru_en':
    case 'choice_en_ru':
      return (
        <ChoiceCard
          key={`${exercise.word_id}-${exercise.type}`}
          exercise={exercise}
          onAnswer={onAnswer}
          locked={locked}
        />
      )
    case 'letters':
      return (
        <LettersCard
          key={`${exercise.word_id}-letters`}
          exercise={exercise}
          onAnswer={onAnswer}
          locked={locked}
        />
      )
    case 'writing_ru_en':
      return (
        <WritingCard
          key={`${exercise.word_id}-writing_ru_en`}
          exercise={exercise}
          onAnswer={onAnswer}
          locked={locked}
        />
      )
    case 'dictation':
      return (
        <DictationCard
          key={`${exercise.word_id}-dictation`}
          exercise={exercise}
          onAnswer={onAnswer}
          locked={locked}
        />
      )
  }
}
