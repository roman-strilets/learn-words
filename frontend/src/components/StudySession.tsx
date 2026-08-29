import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api } from '../api/client'
import type { AnswerResponse, Exercise, SessionPayload, Word } from '../api/types'
import { ExerciseView } from './exercises/ExerciseView'
import { Feedback } from './exercises/Feedback'
import { IntroCard } from './exercises/IntroCard'
import type { AnswerSubmit } from './exercises/types'
import { ErrorBox } from './ui'

/** Через сколько карточек слово вернётся в очередь после ответа. */
const REPEAT_GAP = 3

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
  // Список знакомства пополняется на ходу: «Уже знаю» добирает слово взамен
  const [introWords, setIntroWords] = useState<Word[]>(session.new_words)
  // Пусто на старте: упражнения приходят ответом на карточку знакомства,
  // отдельного поля под них в ответе занятия больше нет
  const [queue, setQueue] = useState<Exercise[]>([])
  const [feedback, setFeedback] = useState<AnswerResponse | null>(null)
  const [tally, setTally] = useState({ answered: 0, correct: 0 })
  // Счётчик показов: входит в key карточки, чтобы состояние ввода
  // гарантированно сбрасывалось даже при двух одинаковых карточках подряд
  const [cardId, setCardId] = useState(0)

  // Защита от повторной отправки: setState асинхронный, а автосабмит
  // в упражнении с буквами может сработать дважды за один рендер-цикл.
  const submitting = useRef(false)
  const startedAt = useRef(Date.now())

  const introDone = introIndex >= introWords.length
  const current = introDone ? (queue[0] ?? null) : null

  useEffect(() => {
    startedAt.current = Date.now()
  }, [current, introIndex])

  const selectMutation = useMutation({
    mutationFn: ({
      wordId,
      action,
      excludeIds,
    }: {
      wordId: number
      action: 'learn' | 'know'
      excludeIds: number[]
    }) => api.select(wordId, action, excludeIds),
    onSuccess: (data) => {
      // Упражнения новых слов идут в конец: сначала знакомимся со всеми
      if (data.next_exercise) setQueue((items) => [...items, data.next_exercise!])
      // «Уже знаю» вывело слово из оборота — на его место встаёт следующее новое,
      // чтобы в занятии осталось столько же слов на изучение
      if (data.replacement) setIntroWords((words) => [...words, data.replacement!])
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
      setFeedback(data)
    },
    onError: () => {
      submitting.current = false
    },
  })

  const advance = useCallback(() => {
    setQueue((items) => {
      const rest = items.slice(1)
      return feedback?.next_exercise ? insertWithGap(rest, feedback.next_exercise) : rest
    })
    setFeedback(null)
    setCardId((id) => id + 1)
    submitting.current = false
  }, [feedback])

  const handleAnswer = useCallback(
    ({ answer, usedHint, attempt }: AnswerSubmit) => {
      if (!current || submitting.current) return
      submitting.current = true
      answerMutation.mutate({
        word_id: current.word_id,
        exercise: current.type,
        answer,
        used_hint: usedHint,
        attempt,
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
      selectMutation.mutate({
        wordId: word.id,
        action,
        // Показанные слова не должны вернуться заменой
        excludeIds: introWords.map((item) => item.id),
      })
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

  // Занятие — это N слов, взятых в изучение. Замена за «Уже знаю» удлиняет
  // список знакомства, поэтому в счётчике карточка со знакомым словом не занимает
  // места: считаем позицию по словам, оставшимся к изучению, а не по показам.
  const introTotal = session.new_words.length
  const introPosition = introIndex - (introWords.length - introTotal)

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
          index={introPosition}
          total={introTotal}
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
          word={feedback.word}
          translation={feedback.translation}
          example={feedback.example}
          exampleTranslation={feedback.example_translation}
          onContinue={advance}
        />
      ) : null}
    </div>
  )
}
