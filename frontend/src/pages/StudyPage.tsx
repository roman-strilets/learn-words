import { useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import { StudySession } from '../components/StudySession'
import { plural } from '../lib/format'
import { Button, ErrorBox, Spinner } from '../components/ui'

interface Summary {
  answered: number
  correct: number
}

export function StudyPage() {
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<Summary | null>(null)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['session'],
    queryFn: api.getSession,
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

  if (isLoading) return <Spinner label="Собираем сессию…" />
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
    return (
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-center text-4xl font-bold text-ink">На сегодня всё</h1>
        <p className="max-w-md text-center text-muted">
          Слова к повторению появятся, когда подойдёт их срок. Можно добавить новые
          слова в словарь или подождать.
        </p>
        <div className="flex gap-4">
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

  return <StudySession session={data} onFinished={handleFinished} />
}
