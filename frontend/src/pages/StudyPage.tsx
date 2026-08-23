import { useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { api } from '../api/client'
import type { StudyMode } from '../api/types'
import { StudySession } from '../components/StudySession'
import { MODE_LABEL, StudyModeLinks, studyPath } from '../components/StudyModeLinks'
import { plural } from '../lib/format'
import { Button, ErrorBox, Spinner } from '../components/ui'

interface Summary {
  answered: number
  correct: number
}

const LOADING_LABEL: Record<StudyMode, string> = {
  learn: 'Подбираем новые слова…',
  review: 'Собираем слова к повторению…',
}

const EMPTY: Record<StudyMode, { title: string; text: string }> = {
  learn: {
    title: 'Новых слов нет',
    text: 'Все слова из словаря уже в изучении — или на сегодня исчерпан дневной лимит новых. Можно повторить изученное или добавить свои слова.',
  },
  review: {
    title: 'На сегодня всё',
    text: 'Слова к повторению появятся, когда подойдёт их срок. Пока можно взять в работу новые слова.',
  },
}

function parseMode(value: string | null): StudyMode | null {
  return value === 'learn' || value === 'review' ? value : null
}

export function StudyPage() {
  const [params] = useSearchParams()
  const mode = parseMode(params.get('mode'))
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<Summary | null>(null)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['session', mode],
    queryFn: () => api.getSession(mode as StudyMode),
    enabled: mode !== null,
    // Сессия — снимок на момент запроса; фоновые перезапросы сбили бы очередь
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
  })

  const handleFinished = useCallback(
    (result: Summary) => {
      setSummary(result)
      queryClient.invalidateQueries({ queryKey: ['overview'] })
      queryClient.invalidateQueries({ queryKey: ['words'] })
    },
    [queryClient],
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
        <StudyModeLinks />
      </div>
    )
  }

  if (isLoading) return <Spinner label={LOADING_LABEL[mode]} />
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

  const empty = data.new_words.length === 0 && data.exercises.length === 0
  if (empty) {
    const other: StudyMode = mode === 'learn' ? 'review' : 'learn'
    return (
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-center text-4xl font-bold text-ink">{EMPTY[mode].title}</h1>
        <p className="max-w-md text-center text-muted">{EMPTY[mode].text}</p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link to={studyPath(other)} className="text-accent underline underline-offset-4">
            {MODE_LABEL[other]}
          </Link>
          <Link to="/" className="text-accent underline underline-offset-4">
            На главную
          </Link>
          <Link to="/words/new" className="text-accent underline underline-offset-4">
            Добавить слово
          </Link>
        </div>
      </div>
    )
  }

  // key: при смене режима очередь и счётчики должны собраться заново
  return <StudySession key={mode} session={data} onFinished={handleFinished} />
}
