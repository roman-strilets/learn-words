import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { deckApi, queryKeys } from '../api/client'
import type { Deck, WordStatusValue, WordWithProgress } from '../api/types'
import { DECK_TEXT } from '../lib/deck'
import { STATUS_CLASS, STATUS_LABEL, formatDue } from '../lib/format'
import { useSpeech } from '../speech/SpeechProvider'
import { ArrowUpIcon, SpeakerIcon } from './icons'
import { ErrorBox, Spinner } from './ui'
import { WordForm } from './WordForm'

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

/** Фильтры списка — те же значения, что уходят в `listWords`. */
export type DictionaryFilters = {
  search?: string
  status?: string
  priority?: boolean
  label?: number | 'none'
}

/**
 * Список словаря колоды: поиск, фильтры, строки с озвучкой, отметкой
 * «Учить первым», статусом, правкой и удалением, пагинация.
 *
 * `tools` — кнопки в конце ряда фильтров, `panel` — блок под ним; оба знают
 * текущие фильтры. Ими «Словарь» слов добавляет автоматическую разметку.
 */
export function DictionaryList({
  deck,
  tools,
  panel,
}: {
  deck: Deck
  tools?: ReactNode
  panel?: (filters: DictionaryFilters) => ReactNode
}) {
  const client = deckApi(deck)
  const keys = queryKeys(deck)
  const text = DECK_TEXT[deck]
  const queryClient = useQueryClient()
  const { speak, supported } = useSpeech()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  // Фильтр поднятых слов не статус: он включается вместе со статусным, а не вместо него
  const [priorityOnly, setPriorityOnly] = useState(false)
  // Одно значение за раз: метка по id или «Без меток»; '' — фильтр выключен
  const [label, setLabel] = useState<number | 'none' | ''>('')
  const [page, setPage] = useState(0)
  const [editingId, setEditingId] = useState<number | null>(null)

  const { data: labels } = useQuery({ queryKey: keys.labels, queryFn: client.listLabels })

  // Выбранную метку удалили на вкладке «Метки» — фильтр по ней больше не имеет
  // смысла, возвращаемся ко всем записям. Правка состояния прямо в рендере:
  // эффект показал бы пустую страницу на один кадр
  if (typeof label === 'number' && labels && !labels.some((item) => item.id === label)) {
    setLabel('')
    setPage(0)
  }

  const { data, isLoading, error } = useQuery({
    queryKey: [...keys.list, search, status, priorityOnly, label, page],
    queryFn: () =>
      client.listWords({
        search: search || undefined,
        status: status || undefined,
        priority: priorityOnly || undefined,
        label: label === '' ? undefined : label,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: keys.list })
    queryClient.invalidateQueries({ queryKey: keys.overview })
    // Правка может завести новые метки, правка и удаление меняют счётчики
    queryClient.invalidateQueries({ queryKey: keys.labels })
  }

  const statusMutation = useMutation({ mutationFn: client.setWordStatus, onSuccess: invalidate })
  const priorityMutation = useMutation({
    mutationFn: client.setWordPriority,
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({ mutationFn: client.deleteWord, onSuccess: invalidate })
  const updateMutation = useMutation({
    mutationFn: client.updateWord,
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
  const rowError = (statusMutation.error ??
    priorityMutation.error ??
    deleteMutation.error) as Error | null

  const filters: DictionaryFilters = {
    search: search || undefined,
    status: status || undefined,
    priority: priorityOnly || undefined,
    label: label === '' ? undefined : label,
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPage(0)
          }}
          placeholder={text.search}
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
          <button
            type="button"
            onClick={() => {
              setPriorityOnly((value) => !value)
              setPage(0)
            }}
            aria-pressed={priorityOnly}
            className={`flex items-center gap-1 rounded px-3 py-2 text-sm transition-colors ${
              priorityOnly ? 'bg-accent text-white' : 'bg-panel text-ink-soft hover:bg-hairline'
            }`}
          >
            <ArrowUpIcon className="size-4" />
            {text.raiseMany}
          </button>
          <select
            value={label}
            onChange={(event) => {
              const value = event.target.value
              setLabel(value === '' || value === 'none' ? value : Number(value))
              setPage(0)
            }}
            aria-label="Фильтр по метке"
            className={`rounded px-3 py-2 text-sm outline-none ${
              label === '' ? 'bg-panel text-ink-soft' : 'bg-accent text-white'
            }`}
          >
            <option value="">Все метки</option>
            <option value="none">Без меток</option>
            {labels?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          {tools}
        </div>
      </div>

      {panel ? panel(filters) : null}

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
                  <th className="py-2 pr-4 font-normal">{text.column}</th>
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
                          deck={deck}
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
                            {/* Поднять можно только новую запись: у записи в изучении
                                кнопки нет, поэтому до ответа 409 дело не доходит */}
                            {word.progress ? null : (
                              <button
                                type="button"
                                onClick={() =>
                                  priorityMutation.mutate({
                                    id: word.id,
                                    priority: !word.priority,
                                  })
                                }
                                disabled={
                                  priorityMutation.isPending &&
                                  priorityMutation.variables?.id === word.id
                                }
                                aria-pressed={word.priority}
                                title={word.priority ? 'Не поднимать' : text.raise}
                                aria-label={
                                  word.priority
                                    ? `Не поднимать «${word.word}»`
                                    : `Учить «${word.word}» ${deck === 'words' ? 'первым' : 'первой'}`
                                }
                                className={`transition-colors disabled:opacity-30 ${
                                  word.priority ? 'text-accent' : 'text-muted hover:text-accent'
                                }`}
                              >
                                <ArrowUpIcon className="size-5" />
                              </button>
                            )}
                          </span>
                          {/* Метки только показываются: меняются они в «Изменить»,
                              вместе с остальной правкой записи */}
                          {word.labels.length ? (
                            <span className="mt-1 flex flex-wrap gap-1">
                              {word.labels.map((item) => (
                                <span
                                  key={item.id}
                                  className="rounded bg-panel px-2 py-0.5 text-sm text-ink-soft"
                                >
                                  {item.name}
                                </span>
                              ))}
                            </span>
                          ) : null}
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
    </>
  )
}
