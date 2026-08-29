import type { Exercise } from '../../api/types'
import { ChoiceCard } from './ChoiceCard'
import { DictationCard } from './DictationCard'
import { IntroCard } from './IntroCard'
import { LettersCard } from './LettersCard'
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
    case 'intro':
      return (
        <IntroCard
          content={{
            wordId: exercise.word_id,
            word: exercise.word,
            translation: exercise.translation,
            example: exercise.example,
            example_translation: exercise.example_translation,
          }}
          variant="repeat"
          onLearn={() => onAnswer({ answer: 'learn', usedHint: false })}
          locked={locked}
        />
      )
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
