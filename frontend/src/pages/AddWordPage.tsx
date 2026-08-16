import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import { Button, ErrorBox } from '../components/ui'

const EMPTY = { word: '', translation: '', example: '', example_translation: '' }

export function AddWordPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY)
  const [added, setAdded] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: api.createWord,
    onSuccess: (word) => {
      setAdded(word.word)
      setForm(EMPTY)
      queryClient.invalidateQueries({ queryKey: ['words'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  const update = (field: keyof typeof EMPTY) => (value: string) =>
    setForm((current) => ({ ...current, [field]: value }))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setAdded(null)
    mutation.mutate({
      word: form.word,
      translation: form.translation,
      example: form.example || null,
      example_translation: form.example_translation || null,
    })
  }

  const disabled = !form.word.trim() || !form.translation.trim() || mutation.isPending

  return (
    <form onSubmit={submit} className="flex w-full max-w-xl flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-4xl font-bold text-ink">Новое слово</h1>
        <Link to="/words" className="text-accent underline underline-offset-4">
          К словарю
        </Link>
      </header>

      <Field label="Слово на английском" required>
        <input
          value={form.word}
          onChange={(event) => update('word')(event.target.value)}
          autoFocus
          autoComplete="off"
          className="w-full rounded border border-hairline px-4 py-3 text-lg outline-none focus:border-accent"
        />
      </Field>

      <Field label="Перевод" required>
        <input
          value={form.translation}
          onChange={(event) => update('translation')(event.target.value)}
          autoComplete="off"
          className="w-full rounded border border-hairline px-4 py-3 text-lg outline-none focus:border-accent"
        />
      </Field>

      <Field label="Пример употребления">
        <input
          value={form.example}
          onChange={(event) => update('example')(event.target.value)}
          autoComplete="off"
          className="w-full rounded border border-hairline px-4 py-3 outline-none focus:border-accent"
        />
      </Field>

      <Field label="Перевод примера">
        <input
          value={form.example_translation}
          onChange={(event) => update('example_translation')(event.target.value)}
          autoComplete="off"
          className="w-full rounded border border-hairline px-4 py-3 outline-none focus:border-accent"
        />
      </Field>

      {mutation.error ? <ErrorBox message={(mutation.error as Error).message} /> : null}
      {added ? (
        <p className="rounded border border-correct bg-correct-soft px-4 py-3 text-correct">
          «{added}» добавлено — слово попадёт в ближайшую сессию
        </p>
      ) : null}

      <Button type="submit" disabled={disabled} className="self-start">
        {mutation.isPending ? 'Сохраняем…' : 'Добавить'}
      </Button>
    </form>
  )
}

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm text-muted">
        {label}
        {required ? <span className="text-wrong"> *</span> : null}
      </span>
      {children}
    </label>
  )
}
