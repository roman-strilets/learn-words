import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api } from '../api/client'
import type { Exercise, SessionPayload } from '../api/types'
import { ChoiceCard } from './exercises/ChoiceCard'
import { DictationCard } from './exercises/DictationCard'
import { Feedback } from './exercises/Feedback'
import { IntroCard } from './exercises/IntroCard'
import { LettersCard } from './exercises/LettersCard'
import type { AnswerSubmit } from './exercises/types'
import { ErrorBox } from './ui'

/** Через сколько карточек слово вернётся в очередь после ответа. */
const REPEAT_GAP = 3
const CORRECT_FLASH_MS = 900

interface PendingFeedback {
  correct: boolean
  correctAnswer: string
  next: Exercise | null
}

function insertWithGap(queue: Exercise[], item: Exercise): Exercise[] {
  const next = queue.slice()
  next.splice(Math.min(REPEAT_GAP, next.length), 0, item)
  return next
}

interface Props {
  session: SessionPayload
  onFinished: (summary: { answered: number; correct: number }) => void
}

export function StudySession({ session, onFinished }: Props) {
  const [introIndex, setIntroIndex] = useState(0)
  const [queue, setQueue] = useState<Exercise[]>(session.exercises)
  const [feedback, setFeedback] = useState<PendingFeedback | null>(null)
  const [tally, setTally] = useState({ answered: 0, correct: 0 })
  // Счётчик показов: входит в key карточки, чтобы состояние ввода
  // гарантированно сбрасывалось даже при двух одинаковых карточках подряд
  const [cardId, setCardId] = useState(0)

  // Защита от повторной отправки: setState асинхронный, а автосабмит
  // в упражнении с буквами может сработать дважды за один рендер-цикл.
  const submitting = useRef(false)
  const startedAt = useRef(Date.now())

  const introWords = session.new_words
  const introDone = introIndex >= introWords.length
  const current = introDone ? (queue[0] ?? null) : null

  useEffect(() => {
    startedAt.current = Date.now()
  }, [current, introIndex])

  const selectMutation = useMutation({
    mutationFn: ({ wordId, action }: { wordId: number; action: 'learn' | 'know' }) =>
      api.select(wordId, action),
    onSuccess: (data) => {
      // Упражнения новых слов идут в конец: сначала знакомимся со всеми
      if (data.next_exercise) setQueue((items) => [...items, data.next_exercise!])
      setIntroIndex((index) => index + 1)
      submitting.current = false
    },
    onError: () => {
      submitting.current = false
    },
  })

  const answerMutation = useMutation({
    mutationFn: api.answer,
    onSuccess: (data) => {
      setTally((value) => ({
        answered: value.answered + 1,
        correct: value.correct + (data.correct ? 1 : 0),
      }))
      setFeedback({
        correct: data.correct,
        correctAnswer: data.correct_answer,
        next: data.next_exercise,
      })
    },
    onError: () => {
      submitting.current = false
    },
  })

  const advance = useCallback(() => {
    setQueue((items) => {
      const rest = items.slice(1)
      return feedback?.next ? insertWithGap(rest, feedback.next) : rest
    })
    setFeedback(null)
    setCardId((id) => id + 1)
    submitting.current = false
  }, [feedback])

  // Верный ответ не требует подтверждения — гасим плашку сами
  useEffect(() => {
    if (!feedback?.correct) return
    const timer = window.setTimeout(advance, CORRECT_FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [feedback, advance])

  const handleAnswer = useCallback(
    ({ answer, usedHint }: AnswerSubmit) => {
      if (!current || submitting.current) return
      submitting.current = true
      answerMutation.mutate({
        word_id: current.word_id,
        exercise: current.type,
        answer,
        used_hint: usedHint,
        duration_ms: Date.now() - startedAt.current,
      })
    },
    [current, answerMutation],
  )

  const handleSelect = useCallback(
    (action: 'learn' | 'know') => {
      const word = introWords[introIndex]
      if (!word || submitting.current) return
      submitting.current = true
      selectMutation.mutate({ wordId: word.id, action })
    },
    [introWords, introIndex, selectMutation],
  )

  const finished = introDone && queue.length === 0
  useEffect(() => {
    if (finished) onFinished(tally)
  }, [finished, onFinished, tally])

  const remaining = useMemo(
    () => introWords.length - introIndex + queue.length,
    [introWords.length, introIndex, queue.length],
  )

  const error = selectMutation.error ?? answerMutation.error
  const locked = Boolean(feedback) || submitting.current

  if (finished) return null

  return (
    <div className="flex flex-col items-center gap-8">
      <p className="text-sm text-muted">Осталось карточек: {remaining}</p>

      {error ? <ErrorBox message={(error as Error).message} /> : null}

      {!introDone ? (
        <IntroCard
          content={{
            wordId: introWords[introIndex].id,
            word: introWords[introIndex].word,
            translation: introWords[introIndex].translation,
            example: introWords[introIndex].example,
            example_translation: introWords[introIndex].example_translation,
          }}
          variant="select"
          index={introIndex}
          total={introWords.length}
          onLearn={() => handleSelect('learn')}
          onKnow={() => handleSelect('know')}
          locked={submitting.current}
        />
      ) : current ? (
        <ExerciseView
          key={cardId}
          exercise={current}
          onAnswer={handleAnswer}
          locked={locked}
        />
      ) : null}

      {feedback ? (
        <Feedback
          correct={feedback.correct}
          correctAnswer={feedback.correctAnswer}
          onContinue={advance}
        />
      ) : null}
    </div>
  )
}

function ExerciseView({
  exercise,
  onAnswer,
  locked,
}: {
  exercise: Exercise
  onAnswer: (submit: AnswerSubmit) => void
  locked: boolean
}) {
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
