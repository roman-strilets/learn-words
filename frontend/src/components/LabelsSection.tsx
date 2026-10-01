import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { Label } from '../api/types'
import { plural } from '../lib/format'
import { ErrorBox, Spinner } from './ui'

/** Совпадает с `LABEL_NAME_MAX` на сервере: длиннее он ответит 422. */
const LABEL_NAME_MAX = 50
/** Совпадает с `LABEL_DESCRIPTION_MAX` на сервере. */
const LABEL_DESCRIPTION_MAX = 200

const wordCount = (count: number) => `${count} ${plural(count, ['слово', 'слова', 'слов'])}`

const INPUT =
  'min-w-0 flex-1 rounded border border-hairline px-4 py-2 outline-none focus:border-accent'
const PRIMARY =
  'rounded-md bg-accent px-4 py-2 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50'

/**
 * Метка и счётчик слов под ней — меняют и строки словаря, и фильтр по метке.
 * После любой правки перечитываем оба.
 */
function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['labels'] })
    queryClient.invalidateQueries({ queryKey: ['words'] })
  }
}

/** Строка списка: название, описание и число слов, либо форма правки на её месте. */
function LabelRow({ label }: { label: Label }) {
  const invalidate = useInvalidate()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(label.name)
  const [description, setDescription] = useState(label.description ?? '')

  const rename = useMutation({
    mutationFn: api.updateLabel,
    onSuccess: () => {
      setEditing(false)
      invalidate()
    },
  })
  const remove = useMutation({ mutationFn: api.deleteLabel, onSuccess: invalidate })

  const confirmDelete = () => {
    const where = label.word_count
      ? `Она будет снята с ${label.word_count} ${plural(label.word_count, ['слова', 'слов', 'слов'])}.`
      : 'Она не стоит ни на одном слове.'
    if (window.confirm(`Удалить метку «${label.name}»? ${where}`)) remove.mutate(label.id)
  }

  if (editing) {
    const submit = (event: FormEvent) => {
      event.preventDefault()
      rename.mutate({ id: label.id, name, description })
    }
    // Ошибка остаётся в строке вместе с введённым — его можно поправить
    return (
      <li className="flex flex-col gap-2 border-b border-hairline/60 py-3">
        <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={LABEL_NAME_MAX}
            autoFocus
            aria-label={`Новое название метки «${label.name}»`}
            className={INPUT}
          />
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={LABEL_DESCRIPTION_MAX}
            placeholder="Описание для разметки"
            aria-label={`Описание метки «${label.name}» для разметки`}
            className={`${INPUT} basis-full`}
          />
          <button
            type="submit"
            disabled={!name.trim() || rename.isPending}
            className={PRIMARY}
          >
            {rename.isPending ? 'Сохраняем…' : 'Сохранить'}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(false)
              setName(label.name)
              setDescription(label.description ?? '')
              rename.reset()
            }}
            className="text-muted underline underline-offset-4 hover:text-ink"
          >
            Отмена
          </button>
        </form>
        {rename.error ? <ErrorBox message={rename.error.message} /> : null}
      </li>
    )
  }

  return (
    <li className="flex flex-col gap-2 border-b border-hairline/60 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex flex-col gap-1">
          <span className="flex items-baseline gap-3">
            <span className="font-semibold text-ink">{label.name}</span>
            <span className="text-sm text-muted">{wordCount(label.word_count)}</span>
          </span>
          {label.description ? (
            <span className="text-sm text-muted">{label.description}</span>
          ) : null}
        </span>
        <span className="text-sm whitespace-nowrap">
          <button
            type="button"
            onClick={() => {
              setName(label.name)
              setDescription(label.description ?? '')
              setEditing(true)
            }}
            className="mr-3 text-accent underline underline-offset-4"
          >
            Изменить
          </button>
          <button
            type="button"
            onClick={confirmDelete}
            disabled={remove.isPending}
            className="text-wrong underline underline-offset-4 disabled:opacity-50"
          >
            Удалить
          </button>
        </span>
      </div>
      {remove.error ? <ErrorBox message={remove.error.message} /> : null}
    </li>
  )
}

/**
 * Вкладка «Метки»: общий список меток. Ставятся метки в форме слова, а здесь
 * их заводят заранее, переименовывают и удаляют.
 */
export function LabelsSection() {
  const invalidate = useInvalidate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const { data, isLoading, error } = useQuery({ queryKey: ['labels'], queryFn: api.listLabels })

  // На 409 введённое остаётся в поле: очищаем только после удачного создания
  const create = useMutation({
    mutationFn: api.createLabel,
    onSuccess: () => {
      setName('')
      setDescription('')
      invalidate()
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate({ name, description })
  }

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-ink-soft">Метки</h2>
      <p className="text-muted">
        Метки группируют слова по темам. Ставятся они в форме слова — при добавлении
        или в «Изменить», а здесь общий список: его можно пополнить, переименовать
        метку или удалить её со всех слов сразу. На занятия метки не влияют.
      </p>
      <p className="text-muted">
        Описание необязательно: автоматическая разметка показывает его модели вместо
        названия. Короткое «B2» модель поймёт хуже, чем «advanced vocabulary (CEFR B2)».
      </p>

      <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={LABEL_NAME_MAX}
          placeholder="Новая метка"
          aria-label="Новая метка"
          className={INPUT}
        />
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={LABEL_DESCRIPTION_MAX}
          placeholder="Описание для разметки — необязательно"
          aria-label="Описание новой метки для разметки"
          className={INPUT}
        />
        <button type="submit" disabled={!name.trim() || create.isPending} className={PRIMARY}>
          Добавить
        </button>
      </form>
      {create.error ? <ErrorBox message={create.error.message} /> : null}

      {error ? <ErrorBox message={error.message} /> : null}
      {isLoading ? <Spinner /> : null}
      {data ? (
        data.length ? (
          <ul className="flex flex-col">
            {data.map((label) => (
              <LabelRow key={label.id} label={label} />
            ))}
          </ul>
        ) : (
          <p className="text-muted">Меток пока нет</p>
        )
      ) : null}
    </section>
  )
}
