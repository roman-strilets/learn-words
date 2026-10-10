import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { ApiError, api } from '../api/client'
import type {
  AnswerResponse,
  Exercise,
  ExerciseRound,
  ExerciseType,
  StudyMode,
} from '../api/types'
import { arrangeRound } from '../lib/roundOrder'
import { ExerciseView } from './exercises/ExerciseView'
import { Feedback } from './exercises/Feedback'
import type { AnswerSubmit } from './exercises/types'
import { Button, ErrorBox, Spinner } from './ui'

/** Названия раундов: пользователь должен понимать, чем занят прямо сейчас. */
const EXERCISE_LABEL: Record<ExerciseType, string> = {
  intro: 'Знакомство',
  choice_ru_en: 'Выбор перевода: рус → англ',
  choice_en_ru: 'Выбор перевода: англ → рус',
  letters: 'Сборка из букв',
  writing_ru_en: 'Написание: рус → англ',
  dictation: 'Аудирование',
}

interface Props {
  rounds: ExerciseRound[]
  sessionId: string
  mode: StudyMode
  onFinished: (summary: { answered: number; correct: number }) => void
}

/** Слово выбыло из занятия: его вывели из оборота или удалили из словаря. */
function isGone(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 409)
}

/**
 * Раннер раундов: раунды по типам упражнений — один на оба режима.
 *
 * Ошибка возвращает слово в конец текущего раунда с пересобранной карточкой,
 * и следующий раунд не начинается, пока в текущем осталась хоть одна карточка.
 * Расписание внутри занятия не двигается — его пересчитывает `finishSession`
 * один раз, в конце, по журналу занятия. Изучение и повторение расходятся
 * только в том, как сервер выводит итог, — очередь у них общая.
 *
 * Порядок слов в раундах перемешивает сервер, но он знает только план.
 * На границе раунда порядок поправляется под то, что показано на самом деле:
 * выбывшее слово может сделать два разных серверных порядка одинаковыми
 * (`[a, b, c]` и `[a, c, b]` без `c`).
 */
export function RoundsRunner({ rounds, sessionId, mode, onFinished }: Props) {
  const [roundIndex, setRoundIndex] = useState(0)
  const [queue, setQueue] = useState<Exercise[]>(() => rounds[0]?.exercises ?? [])
  // Порядок первых показов текущего раунда — так, как он показан.
  // Повторы после ошибки сюда не попадают: они не меняют порядок раунда.
  const [roundOrder, setRoundOrder] = useState<number[]>(
    () => rounds[0]?.exercises.map((e) => e.word_id) ?? [],
  )
  // Слово последней отвеченной карточки. Сервер знает только запланированный
  // конец раунда, а последним мог оказаться повтор после ошибки (FR-004).
  // Выбывшее слово здесь может остаться: в следующем раунде его всё равно нет.
  const [lastWordId, setLastWordId] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<AnswerResponse | null>(null)
  const [tally, setTally] = useState({ answered: 0, correct: 0 })
  // Номер показа слова в текущем раунде: 1 на первом показе, +1 на каждый
  // повтор после ошибки. На границе раунда счёт начинается заново (FR-012a).
  const [shows, setShows] = useState<Record<number, number>>({})
  // Слова, выбывшие из занятия по ходу дела: их не показываем в новых раундах
  const [dropped, setDropped] = useState<number[]>([])
  // Счётчик показов: входит в key карточки, чтобы состояние ввода сбрасывалось
  // даже когда одно и то же слово показано дважды подряд
  const [cardId, setCardId] = useState(0)
  const [finished, setFinished] = useState(false)

  // Защита от повторной отправки: setState асинхронный, а автосабмит
  // в упражнении с буквами может сработать дважды за один рендер-цикл.
  const submitting = useRef(false)
  const startedAt = useRef(Date.now())

  const current = queue[0] ?? null

  useEffect(() => {
    startedAt.current = Date.now()
  }, [current])

  // Итог занятия показываем только после ответа сервера: если пересчёт не
  // прошёл, вся работа занятия пропала бы молча — лучше дать повторить.
  const finishMutation = useMutation({
    mutationFn: (id: string) => api.finishSession(id, mode),
    onSuccess: () => onFinished(tally),
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
    onError: (error, variables) => {
      // Слово вывели из оборота прямо во время занятия: убираем его из
      // оставшихся раундов, а очередь идёт дальше как ни в чём не бывало
      if (isGone(error)) {
        setDropped((items) => [...items, variables.word_id])
        setQueue((items) => items.filter((item) => item.word_id !== variables.word_id))
        setCardId((id) => id + 1)
      }
      submitting.current = false
    },
  })

  const advance = useCallback(() => {
    const repeat = feedback?.next_exercise ?? null
    if (current) setLastWordId(current.word_id)
    setQueue((items) => {
      const rest = items.slice(1)
      // Повтор встаёт после остальных карточек раунда, а не сразу (FR-009)
      return repeat ? [...rest, repeat] : rest
    })
    if (repeat) {
      setShows((counts) => ({
        ...counts,
        [repeat.word_id]: (counts[repeat.word_id] ?? 1) + 1,
      }))
    }
    setFeedback(null)
    setCardId((id) => id + 1)
    submitting.current = false
  }, [feedback, current])

  // Раунд закончился — берём следующий и начинаем счёт показов заново (FR-010)
  useEffect(() => {
    if (feedback || queue.length > 0 || finished) return

    const next = roundIndex + 1
    if (next < rounds.length) {
      const gone = new Set(dropped)
      setRoundIndex(next)
      setShows({})
      const arranged = arrangeRound(
        rounds[next].exercises.filter((item) => !gone.has(item.word_id)),
        roundOrder.filter((id) => !gone.has(id)),
        lastWordId,
      )
      setQueue(arranged)
      setRoundOrder(arranged.map((item) => item.word_id))
      return
    }
    setFinished(true)
  }, [feedback, queue.length, finished, roundIndex, rounds, dropped, roundOrder, lastWordId])

  // Все раунды пройдены: расписание пересчитывается один раз, на сервере
  const finish = finishMutation.mutate
  useEffect(() => {
    if (!finished) return
    finish(sessionId)
  }, [finished, sessionId, finish])

  const handleAnswer = useCallback(
    ({ answer, usedHint, attempt }: AnswerSubmit) => {
      if (!current || submitting.current) return
      submitting.current = true
      answerMutation.mutate({
        word_id: current.word_id,
        exercise: current.type,
        answer,
        used_hint: usedHint,
        // Номер показа и промахи внутри карточки значат одно и то же —
        // «взято не с первой попытки», поэтому берём большее из двух
        attempt: Math.max(shows[current.word_id] ?? 1, attempt ?? 1),
        duration_ms: Date.now() - startedAt.current,
        mode,
        session_id: sessionId,
      })
    },
    [current, answerMutation, shows, mode, sessionId],
  )

  // Объём работы: остаток текущего раунда плюс раунды впереди. Повтор после
  // ошибки удлиняет очередь, и счётчик честно растёт (FR-018).
  const remaining = useMemo(() => {
    const active = rounds[roundIndex]
      ? rounds[roundIndex].exercises.length - dropped.length
      : 0
    return queue.length + Math.max(0, active) * (rounds.length - roundIndex - 1)
  }, [queue.length, rounds, roundIndex, dropped.length])

  const error = answerMutation.error
  const locked = Boolean(feedback) || submitting.current

  if (finished) {
    if (finishMutation.isError) {
      return (
        <div className="flex flex-col items-center gap-6">
          <ErrorBox message={(finishMutation.error as Error).message} />
          <p className="max-w-md text-center text-muted">
            Ответы занятия сохранены, но расписание слов ещё не пересчитано.
          </p>
          <Button onClick={() => finish(sessionId)}>Повторить</Button>
        </div>
      )
    }
    return <Spinner label="Подводим итог занятия…" />
  }

  if (!current) return null

  return (
    <div className="flex flex-col items-center gap-8">
      <div className="flex flex-col items-center gap-1">
        <p className="text-sm font-semibold text-ink">
          Раунд {roundIndex + 1} из {rounds.length} · {EXERCISE_LABEL[rounds[roundIndex].exercise]}
        </p>
        <p className="text-sm text-muted">Осталось карточек: {remaining}</p>
      </div>

      {error && !isGone(error) ? <ErrorBox message={(error as Error).message} /> : null}

      <ExerciseView
        key={cardId}
        exercise={current}
        onAnswer={handleAnswer}
        locked={locked}
      />

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
