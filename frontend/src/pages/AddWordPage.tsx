import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import { WordForm } from '../components/WordForm'

export function AddWordPage() {
  const queryClient = useQueryClient()
  const [added, setAdded] = useState<string | null>(null)
  // Смена ключа очищает форму — но только после удачного добавления:
  // на 409 введённое остаётся на месте и его можно поправить
  const [formKey, setFormKey] = useState(0)

  const mutation = useMutation({
    mutationFn: api.createWord,
    onSuccess: (word) => {
      setAdded(word.word)
      setFormKey((value) => value + 1)
      queryClient.invalidateQueries({ queryKey: ['words'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  return (
    <div className="flex w-full max-w-xl flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-4xl font-bold text-ink">Новое слово</h1>
        <Link to="/words" className="text-accent underline underline-offset-4">
          К словарю
        </Link>
      </header>

      <WordForm
        key={formKey}
        submitLabel="Добавить"
        pending={mutation.isPending}
        error={mutation.error as Error | null}
        onSubmit={(payload) => {
          setAdded(null)
          mutation.mutate(payload)
        }}
        footer={
          added ? (
            <p className="rounded border border-correct bg-correct-soft px-4 py-3 text-correct">
              «{added}» добавлено — слово попадёт в ближайшую сессию
            </p>
          ) : null
        }
      />
    </div>
  )
}
