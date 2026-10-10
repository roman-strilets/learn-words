import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { deckApi, queryKeys } from '../api/client'
import type { Deck, Label } from '../api/types'
import { DECK_TEXT } from '../lib/deck'
import { plural } from '../lib/format'
import { ErrorBox, Spinner } from './ui'

/** Совпадает с `LABEL_NAME_MAX` на сервере: длиннее он ответит 422. */
const LABEL_NAME_MAX = 50
/** Совпадает с `LABEL_DESCRIPTION_MAX` на сервере. */
const LABEL_DESCRIPTION_MAX = 200


const INPUT =
  'min-w-0 flex-1 rounded border border-hairline px-4 py-2 outline-none focus:border-accent'
const PRIMARY =
  'rounded-md bg-accent px-4 py-2 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50'

/**
 * Метка и счётчик записей под ней — меняют и строки словаря, и фильтр по метке.
 * После любой правки перечитываем оба.
 */
function useInvalidate(deck: Deck) {
  const queryClient = useQueryClient()
  const keys = queryKeys(deck)
  return () => {
    queryClient.invalidateQueries({ queryKey: keys.labels })
    queryClient.invalidateQueries({ queryKey: keys.list })
  }
}

/** Строка списка: название, описание и число записей, либо форма правки на её месте. */
function LabelRow({ deck, label }: { deck: Deck; label: Label }) {
  const client = deckApi(deck)
  const text = DECK_TEXT[deck]
  const invalidate = useInvalidate(deck)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(label.name)
  const [description, setDescription] = useState(label.description ?? '')

  const rename = useMutation({
    mutationFn: client.updateLabel,
    onSuccess: () => {
      setEditing(false)
      invalidate()
    },
  })
  const remove = useMutation({ mutationFn: client.deleteLabel, onSuccess: invalidate })

  const confirmDelete = () => {
    const where = label.word_count
      ? `Она будет снята с ${label.word_count} ${plural(label.word_count, text.genitive)}.`
      : deck === 'words'
        ? 'Она не стоит ни на одном слове.'
        : 'Она не стоит ни на одной фразе.'
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
            placeholder={deck === 'words' ? 'Описание для разметки' : 'Описание'}
            aria-label={`Описание метки «${label.name}»`}
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
            <span className="text-sm text-muted">
              {label.word_count} {plural(label.word_count, text.forms)}
            </span>
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
 * Вкладки «Метки» и «Метки фраз»: общий список меток колоды. Ставятся метки
 * в форме записи, а здесь их заводят заранее, переименовывают и удаляют.
 */
export function LabelsSection({ deck = 'words' }: { deck?: Deck }) {
  const client = deckApi(deck)
  const invalidate = useInvalidate(deck)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys(deck).labels,
    queryFn: client.listLabels,
  })

  // На 409 введённое остаётся в поле: очищаем только после удачного создания
  const create = useMutation({
    mutationFn: client.createLabel,
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
      {deck === 'words' ? (
        <>
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
        </>
      ) : (
        <>
          <h2 className="text-lg font-semibold text-ink-soft">Метки фраз</h2>
          <p className="text-muted">
            Свои метки у фраз: с метками слов они не пересекаются, даже если названия
            совпадают. Ставятся они в форме фразы, а здесь общий список: его можно
            пополнить, переименовать метку или удалить её со всех фраз сразу. На
            занятия метки не влияют.
          </p>
        </>
      )}

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
          placeholder={
            deck === 'words' ? 'Описание для разметки — необязательно' : 'Описание — необязательно'
          }
          aria-label="Описание новой метки"
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
              <LabelRow key={label.id} deck={deck} label={label} />
            ))}
          </ul>
        ) : (
          <p className="text-muted">Меток пока нет</p>
        )
      ) : null}
    </section>
  )
}
