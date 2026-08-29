import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import type { WordStatusValue, WordWithProgress } from '../api/types'
import { STATUS_CLASS, STATUS_LABEL, formatDue } from '../lib/format'
import { ErrorBox, Spinner } from '../components/ui'
import { SpeakerIcon } from '../components/icons'
import { WordForm } from '../components/WordForm'
import { useSpeech } from '../speech/SpeechProvider'

const PAGE_SIZE = 25

const FILTERS = [
  { value: '', label: 'Все' },
  { value: 'new', label: 'Новые' },
  { value: 'learning', label: 'Изучаются' },
  { value: 'review', label: 'На повторении' },
  { value: 'known', label: 'Знаю' },
]

const STATUSES: WordStatusValue[] = ['new', 'learning', 'review', 'known', 'suspended']

function statusOf(word: WordWithProgress): WordStatusValue {
  return word.progress?.status ?? 'new'
}

/** Статус словарной строки: та же плашка, но её можно переключить. */
function StatusSelect({
  value,
  disabled,
  onChange,
}: {
  value: WordStatusValue
  disabled?: boolean
  onChange: (status: WordStatusValue) => void
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as WordStatusValue)}
      title="Сменить статус"
      className={`cursor-pointer rounded px-2 py-1 text-xs outline-none disabled:opacity-50 ${STATUS_CLASS[value]}`}
    >
      {STATUSES.map((status) => (
        <option key={status} value={status}>
          {STATUS_LABEL[status]}
        </option>
      ))}
    </select>
  )
}

export function WordsPage() {
  const queryClient = useQueryClient()
  const { speak, supported } = useSpeech()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const [editingId, setEditingId] = useState<number | null>(null)

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

  const statusMutation = useMutation({ mutationFn: api.setWordStatus, onSuccess: invalidate })
  const deleteMutation = useMutation({ mutationFn: api.deleteWord, onSuccess: invalidate })
  const updateMutation = useMutation({
    mutationFn: api.updateWord,
    onSuccess: () => {
      setEditingId(null)
      invalidate()
    },
  })

  const total = data?.total ?? 0
  const pages = Math.ceil(total / PAGE_SIZE)

  const applyFilter = (value: string) => {
    setStatus(value)
    setPage(0)
  }

  const startEditing = (wordId: number) => {
    updateMutation.reset()
    setEditingId(wordId)
  }

  const changeStatus = (word: WordWithProgress, next: WordStatusValue) => {
    // Возврат в новые стирает накопленное расписание — спрашиваем, как на удалении
    if (next === 'new' && word.progress) {
      if (!window.confirm(`Сбросить прогресс по «${word.word}»?`)) return
    }
    statusMutation.mutate({ id: word.id, status: next })
  }

  // Ошибка правки живёт в самой форме, остальные показываем над таблицей
  const rowError = (statusMutation.error ?? deleteMutation.error) as Error | null

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
      {rowError ? <ErrorBox message={rowError.message} /> : null}
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
                    {editingId === word.id ? (
                      <td colSpan={5} className="py-4">
                        <WordForm
                          word={word}
                          submitLabel="Сохранить"
                          columns={2}
                          pending={updateMutation.isPending}
                          error={updateMutation.error as Error | null}
                          onCancel={() => setEditingId(null)}
                          onSubmit={(payload) =>
                            updateMutation.mutate({ id: word.id, ...payload })
                          }
                        />
                      </td>
                    ) : (
                      <>
                        <td className="py-3 pr-4">
                          <span className="flex items-center gap-2">
                            <span className="font-semibold text-ink">{word.word}</span>
                            <button
                              type="button"
                              onClick={() => speak(word.word)}
                              disabled={!supported}
                              title="Прослушать"
                              aria-label={`Прослушать «${word.word}»`}
                              className="text-muted transition-colors hover:text-correct disabled:opacity-30"
                            >
                              <SpeakerIcon className="size-5" />
                            </button>
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-ink-soft">{word.translation}</td>
                        <td className="py-3 pr-4">
                          <StatusSelect
                            value={statusOf(word)}
                            disabled={
                              statusMutation.isPending &&
                              statusMutation.variables?.id === word.id
                            }
                            onChange={(next) => changeStatus(word, next)}
                          />
                        </td>
                        <td className="py-3 pr-4 text-sm text-muted">
                          {word.progress ? formatDue(word.progress.due_at) : '—'}
                        </td>
                        <td className="py-3 text-right text-sm whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => startEditing(word.id)}
                            className="mr-3 text-accent underline underline-offset-4"
                          >
                            Изменить
                          </button>
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
                      </>
                    )}
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
