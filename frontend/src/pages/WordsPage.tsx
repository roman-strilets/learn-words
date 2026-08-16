import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import type { WordWithProgress } from '../api/types'
import { STATUS_CLASS, STATUS_LABEL, formatDue } from '../lib/format'
import { ErrorBox, Spinner } from '../components/ui'

const PAGE_SIZE = 25

const FILTERS = [
  { value: '', label: 'Все' },
  { value: 'new', label: 'Новые' },
  { value: 'learning', label: 'Изучаются' },
  { value: 'review', label: 'На повторении' },
  { value: 'known', label: 'Знаю' },
]

function StatusBadge({ word }: { word: WordWithProgress }) {
  const status = word.progress?.status ?? 'new'
  return (
    <span className={`rounded px-2 py-1 text-xs whitespace-nowrap ${STATUS_CLASS[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}

export function WordsPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading, error } = useQuery({
    queryKey: ['words', search, status, page],
    queryFn: () =>
      api.listWords({
        search: search || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['words'] })
    queryClient.invalidateQueries({ queryKey: ['overview'] })
  }

  const resetMutation = useMutation({ mutationFn: api.resetWord, onSuccess: invalidate })
  const deleteMutation = useMutation({ mutationFn: api.deleteWord, onSuccess: invalidate })

  const total = data?.total ?? 0
  const pages = Math.ceil(total / PAGE_SIZE)

  const applyFilter = (value: string) => {
    setStatus(value)
    setPage(0)
  }

  return (
    <div className="flex w-full max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-4xl font-bold text-ink">Словарь</h1>
        <Link
          to="/words/new"
          className="rounded-md bg-accent px-6 py-3 font-semibold text-white transition-colors hover:bg-accent-hover"
        >
          Добавить слово
        </Link>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPage(0)
          }}
          placeholder="Поиск по слову или переводу"
          className="min-w-64 flex-1 rounded border border-hairline px-4 py-2 outline-none focus:border-accent"
        />
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              onClick={() => applyFilter(filter.value)}
              className={`rounded px-3 py-2 text-sm transition-colors ${
                status === filter.value
                  ? 'bg-accent text-white'
                  : 'bg-panel text-ink-soft hover:bg-hairline'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {error ? <ErrorBox message={(error as Error).message} /> : null}
      {isLoading ? <Spinner /> : null}

      {data ? (
        <>
          <p className="text-sm text-muted">Найдено: {total}</p>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-hairline text-sm text-muted">
                  <th className="py-2 pr-4 font-normal">Слово</th>
                  <th className="py-2 pr-4 font-normal">Перевод</th>
                  <th className="py-2 pr-4 font-normal">Статус</th>
                  <th className="py-2 pr-4 font-normal">Повтор</th>
                  <th className="py-2 font-normal"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((word) => (
                  <tr key={word.id} className="border-b border-hairline/60">
                    <td className="py-3 pr-4 font-semibold text-ink">{word.word}</td>
                    <td className="py-3 pr-4 text-ink-soft">{word.translation}</td>
                    <td className="py-3 pr-4">
                      <StatusBadge word={word} />
                    </td>
                    <td className="py-3 pr-4 text-sm text-muted">
                      {word.progress ? formatDue(word.progress.due_at) : '—'}
                    </td>
                    <td className="py-3 text-right text-sm whitespace-nowrap">
                      {word.progress ? (
                        <button
                          type="button"
                          onClick={() => resetMutation.mutate(word.id)}
                          className="mr-3 text-accent underline underline-offset-4"
                        >
                          Сбросить
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Удалить «${word.word}» из словаря?`)) {
                            deleteMutation.mutate(word.id)
                          }
                        }}
                        className="text-wrong underline underline-offset-4"
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.items.length === 0 ? (
            <p className="py-8 text-center text-muted">Ничего не найдено</p>
          ) : null}

          {pages > 1 ? (
            <div className="flex items-center justify-center gap-4">
              <button
                type="button"
                disabled={page === 0}
                onClick={() => setPage((value) => value - 1)}
                className="rounded bg-panel px-4 py-2 text-sm disabled:opacity-40"
              >
                Назад
              </button>
              <span className="text-sm text-muted">
                {page + 1} из {pages}
              </span>
              <button
                type="button"
                disabled={page + 1 >= pages}
                onClick={() => setPage((value) => value + 1)}
                className="rounded bg-panel px-4 py-2 text-sm disabled:opacity-40"
              >
                Вперёд
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
