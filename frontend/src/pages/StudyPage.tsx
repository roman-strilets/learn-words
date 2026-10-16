import { useCallback, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { deckApi, queryKeys } from '../api/client'
import type { Deck, StudyMode } from '../api/types'
import { RoundsRunner, type RoundsApi } from '../components/RoundsRunner'
import { StudySession } from '../components/StudySession'
import { StudyModeLinks, modeLabel, studyPath } from '../components/StudyModeLinks'
import { DECK_TEXT } from '../lib/deck'
import { plural } from '../lib/format'
import { Button, ErrorBox, Spinner } from '../components/ui'

interface Summary {
  answered: number
  correct: number
}

const LOADING_LABEL: Record<Deck, Record<StudyMode, string>> = {
  words: {
    learn: 'Подбираем новые слова…',
    review: 'Собираем слова к повторению…',
  },
  phrases: {
    learn: 'Подбираем новые фразы…',
    review: 'Собираем фразы к повторению…',
  },
}

const EMPTY: Record<Deck, Record<StudyMode, { title: string; text: string }>> = {
  words: {
    learn: {
      title: 'Новых слов нет',
      text: 'Все слова из словаря уже в изучении — или на сегодня исчерпан дневной лимит новых. Можно повторить изученное или добавить свои слова.',
    },
    review: {
      title: 'На сегодня всё',
      text: 'Слова к повторению появятся, когда подойдёт их срок. Пока можно взять в работу новые слова.',
    },
  },
  phrases: {
    learn: {
      title: 'Новых фраз нет',
      text: 'Все фразы уже в изучении — или на сегодня исчерпан дневной лимит новых фраз. Можно повторить изученное или добавить свои фразы.',
    },
    review: {
      title: 'На сегодня всё',
      text: 'Фразы к повторению появятся, когда подойдёт их срок. Пока можно взять в работу новые фразы.',
    },
  },
}

const ADD_LABEL: Record<Deck, string> = {
  words: 'Добавить слово',
  phrases: 'Добавить фразу',
}

function parseMode(value: string | null): StudyMode | null {
  return value === 'learn' || value === 'review' ? value : null
}

/** Без `deck` в адресе — слова: старые ссылки `/study?mode=…` ведут туда же. */
function parseDeck(value: string | null): Deck {
  return value === 'phrases' ? 'phrases' : 'words'
}

export function StudyPage() {
  const [params] = useSearchParams()
  const mode = parseMode(params.get('mode'))
  const deck = parseDeck(params.get('deck'))
  const keys = queryKeys(deck)
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<Summary | null>(null)
  // Маршруты повторения для раннера; один объект, пока не сменились колода и режим
  const roundsApi = useMemo<RoundsApi | null>(() => {
    if (!mode) return null
    const client = deckApi(deck)
    return {
      answer: (payload) => client.answer({ ...payload, mode }),
      finish: (id) => client.finishSession(id, mode),
    }
  }, [deck, mode])

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['session', deck, mode],
    queryFn: () => deckApi(deck).getSession(mode as StudyMode),
    enabled: mode !== null,
    // Сессия — снимок на момент запроса; фоновые перезапросы сбили бы очередь
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
  })

  const handleFinished = useCallback(
    (result: Summary) => {
      setSummary(result)
      queryClient.invalidateQueries({ queryKey: keys.overview })
      queryClient.invalidateQueries({ queryKey: keys.list })
    },
    [queryClient, keys.overview, keys.list],
  )

  const startAnother = async () => {
    setSummary(null)
    await refetch()
  }

  // Прямой заход на /study без режима: спрашиваем, чем заняться
  if (!mode) {
    return (
      <div className="flex flex-col items-center gap-8">
        <h1 className="text-center text-4xl font-bold text-ink">Чем займёмся?</h1>
        <StudyModeLinks deck="words" />
        <StudyModeLinks deck="phrases" />
      </div>
    )
  }

  if (isLoading) return <Spinner label={LOADING_LABEL[deck][mode]} />
  if (error) return <ErrorBox message={(error as Error).message} />
  if (!data) return null

  if (summary) {
    const accuracy = summary.answered
      ? Math.round((summary.correct / summary.answered) * 100)
      : 0
    return (
      <div className="flex flex-col items-center gap-8">
        <h1 className="text-5xl font-bold text-ink">Сессия завершена</h1>
        <p className="text-lg text-muted">
          {summary.answered} {plural(summary.answered, ['ответ', 'ответа', 'ответов'])} ·
          точность {accuracy}%
        </p>
        <div className="flex items-start gap-4">
          <Link
            to="/"
            className="rounded-md bg-neutral-btn px-8 py-4 text-lg font-semibold text-white transition-colors hover:bg-neutral-btn-hover"
          >
            На главную
          </Link>
          <Button onClick={startAnother} disabled={isFetching}>
            Ещё сессия
          </Button>
        </div>
      </div>
    )
  }

  // Занятию нечем заняться. Ключ занятия сервер выдаёт ровно тогда, когда
  // в занятии есть слова, поэтому его отсутствие значит то же, что пустые
  // `new_words` в изучении и пустые `rounds` в повторении, — и заодно
  // ручается раннеру, что sessionId непустой
  if (!data.session_id) {
    const other: StudyMode = mode === 'learn' ? 'review' : 'learn'
    return (
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-center text-4xl font-bold text-ink">{EMPTY[deck][mode].title}</h1>
        <p className="max-w-md text-center text-muted">{EMPTY[deck][mode].text}</p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link to={studyPath(other, deck)} className="text-accent underline underline-offset-4">
            {modeLabel(other, deck)}
          </Link>
          <Link to="/" className="text-accent underline underline-offset-4">
            На главную
          </Link>
          <Link
            to={`${DECK_TEXT[deck].path}/new`}
            className="text-accent underline underline-offset-4"
          >
            {ADD_LABEL[deck]}
          </Link>
        </div>
      </div>
    )
  }

  // Режимы расходятся только в начале: «Изучение» сперва ведёт знакомство
  // и лишь потом запрашивает раунды, «Повторение» получает их вместе
  // с занятием и идёт в раннер сразу.
  // key: при смене режима или колоды очередь и счётчики должны собраться заново
  return mode === 'review' && roundsApi ? (
    <RoundsRunner
      key={`${deck}:${mode}`}
      api={roundsApi}
      rounds={data.rounds}
      sessionId={data.session_id}
      onFinished={handleFinished}
    />
  ) : (
    <StudySession
      key={`${deck}:${mode}`}
      deck={deck}
      session={data}
      sessionId={data.session_id}
      onFinished={handleFinished}
    />
  )
}
