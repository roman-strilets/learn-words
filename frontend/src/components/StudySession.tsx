import { useCallback, useEffect, useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api } from '../api/client'
import type { ExerciseRound, SessionPayload, Word } from '../api/types'
import { RoundsRunner } from './RoundsRunner'
import { IntroCard } from './exercises/IntroCard'
import { Button, ErrorBox, Spinner } from './ui'

interface Props {
  session: SessionPayload
  /** Ключ занятия: занятие без слов до этого компонента не доходит */
  sessionId: string
  onFinished: (summary: { answered: number; correct: number }) => void
}

/**
 * Раннер занятия-изучения: знакомство со всеми словами, затем раунды.
 *
 * Состав занятия известен только к концу знакомства — «Уже знаю» выводит
 * слово из оборота и добирает замену, — поэтому план раундов запрашивается
 * одним вызовом после последней карточки знакомства, а дальше занятие ведёт
 * тот же `RoundsRunner`, что и повторение.
 */
export function StudySession({ session, sessionId, onFinished }: Props) {
  const [introIndex, setIntroIndex] = useState(0)
  // Список знакомства пополняется на ходу: «Уже знаю» добирает слово взамен
  const [introWords, setIntroWords] = useState<Word[]>(session.new_words)
  // Слова, реально взятые в изучение: по ним и строится план раундов
  const [learnedIds, setLearnedIds] = useState<number[]>([])
  const [rounds, setRounds] = useState<ExerciseRound[] | null>(null)

  // Защита от повторной отправки: setState асинхронный, а две кнопки
  // знакомства успевают сработать дважды за один рендер-цикл.
  const submitting = useRef(false)

  const introDone = introIndex >= introWords.length

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
    onSuccess: (data, variables) => {
      if (variables.action === 'learn') {
        setLearnedIds((ids) => [...ids, variables.wordId])
      }
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

  const roundsMutation = useMutation({
    mutationFn: (wordIds: number[]) => api.buildRounds(wordIds),
    onSuccess: setRounds,
  })

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

  // Знакомство пройдено — состав занятия окончателен, просим план раундов
  const buildRounds = roundsMutation.mutate
  const { isIdle: roundsNotAsked } = roundsMutation
  useEffect(() => {
    if (!introDone || learnedIds.length === 0 || !roundsNotAsked) return
    buildRounds(learnedIds)
  }, [introDone, learnedIds, roundsNotAsked, buildRounds])

  // Занятие кончилось, не начавшись: все слова оказались знакомыми либо
  // выбыли из оборота, пока шло знакомство. Раунды строить не из чего,
  // и запрос за ними не уходит
  const nothingToDo = introDone && (learnedIds.length === 0 || rounds?.length === 0)
  useEffect(() => {
    if (nothingToDo) onFinished({ answered: 0, correct: 0 })
  }, [nothingToDo, onFinished])

  if (introDone) {
    if (rounds && rounds.length > 0) {
      return (
        <RoundsRunner
          rounds={rounds}
          sessionId={sessionId}
          mode="learn"
          onFinished={onFinished}
        />
      )
    }
    if (roundsMutation.isError) {
      return (
        <div className="flex flex-col items-center gap-6">
          <ErrorBox message={(roundsMutation.error as Error).message} />
          <p className="max-w-md text-center text-muted">
            Слова взяты в изучение, но упражнения к ним ещё не собраны.
          </p>
          <Button onClick={() => buildRounds(learnedIds)}>Повторить</Button>
        </div>
      )
    }
    // Пока раунды едут — и пока пустое занятие досматривает эффект выше
    return nothingToDo ? null : <Spinner label="Собираем упражнения…" />
  }

  // Занятие — это N слов, взятых в изучение. Замена за «Уже знаю» удлиняет
  // список знакомства, поэтому в счётчике карточка со знакомым словом не занимает
  // места: считаем позицию по словам, оставшимся к изучению, а не по показам.
  const introTotal = session.new_words.length
  const introPosition = introIndex - (introWords.length - introTotal)

  return (
    <div className="flex flex-col items-center gap-8">
      {selectMutation.error ? (
        <ErrorBox message={(selectMutation.error as Error).message} />
      ) : null}

      <IntroCard
        content={{
          wordId: introWords[introIndex].id,
          word: introWords[introIndex].word,
          translation: introWords[introIndex].translation,
          example: introWords[introIndex].example,
          example_translation: introWords[introIndex].example_translation,
        }}
        index={introPosition}
        total={introTotal}
        onLearn={() => handleSelect('learn')}
        onKnow={() => handleSelect('know')}
        locked={submitting.current}
      />
    </div>
  )
}
