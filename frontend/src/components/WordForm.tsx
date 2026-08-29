import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import type { Word, WordInput } from '../api/types'
import { ErrorBox, TextField } from './ui'

const EMPTY = { word: '', translation: '', example: '', example_translation: '' }

type Values = typeof EMPTY

function valuesOf(word: Word | undefined): Values {
  if (!word) return EMPTY
  return {
    word: word.word,
    translation: word.translation,
    example: word.example ?? '',
    example_translation: word.example_translation ?? '',
  }
}

/**
 * Форма слова: одна и та же и на странице добавления, и в строке словаря
 * при правке. `columns` задаёт раскладку — в таблице поля идут парами,
 * на отдельной странице в столбик.
 *
 * Значения держит форма, поэтому очистка после удачного добавления делается
 * сменой `key` у самой формы: так не нужен обратный канал из родителя.
 */
export function WordForm({
  word,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
  columns = 1,
  footer,
}: {
  /** Слово для правки; без него форма заводит новое */
  word?: Word
  submitLabel: string
  pending?: boolean
  error?: Error | null
  onSubmit: (payload: WordInput) => void
  onCancel?: () => void
  columns?: 1 | 2
  /** Плашка под полями — например, сообщение об удачном добавлении */
  footer?: ReactNode
}) {
  const [form, setForm] = useState(() => valuesOf(word))

  const update = (field: keyof Values) => (value: string) =>
    setForm((current) => ({ ...current, [field]: value }))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit({
      word: form.word,
      translation: form.translation,
      example: form.example || null,
      example_translation: form.example_translation || null,
    })
  }

  const disabled = !form.word.trim() || !form.translation.trim() || pending
  const wide = columns === 2 ? 'sm:col-span-2' : ''

  return (
    <form
      onSubmit={submit}
      className={columns === 2 ? 'grid gap-4 sm:grid-cols-2' : 'flex flex-col gap-5'}
    >
      <TextField
        label="Слово на английском"
        value={form.word}
        onChange={update('word')}
        required
        autoFocus
        className="text-lg"
      />
      <TextField
        label="Перевод"
        value={form.translation}
        onChange={update('translation')}
        required
        className="text-lg"
      />
      <TextField
        label="Пример употребления"
        value={form.example}
        onChange={update('example')}
      />
      <TextField
        label="Перевод примера"
        value={form.example_translation}
        onChange={update('example_translation')}
      />

      {error ? (
        <div className={wide}>
          <ErrorBox message={error.message} />
        </div>
      ) : null}
      {footer ? <div className={wide}>{footer}</div> : null}

      <div className={`flex items-center gap-4 ${wide}`}>
        <button
          type="submit"
          disabled={disabled}
          className="rounded-md bg-accent px-6 py-3 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? 'Сохраняем…' : submitLabel}
        </button>
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="text-muted underline underline-offset-4 hover:text-ink"
          >
            Отмена
          </button>
        ) : null}
      </div>
    </form>
  )
}
