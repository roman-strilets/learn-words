import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { deckApi, queryKeys } from '../api/client'
import type { Deck } from '../api/types'
import { DECK_TEXT } from '../lib/deck'
import { WordForm } from './WordForm'

/** Страница добавления записи колоды: форма, сообщение об успехе, ссылка к словарю. */
export function AddEntry({ deck, title, back }: { deck: Deck; title: string; back: string }) {
  const keys = queryKeys(deck)
  const queryClient = useQueryClient()
  const [added, setAdded] = useState<string | null>(null)
  // Смена ключа очищает форму — но только после удачного добавления:
  // на 409 введённое остаётся на месте и его можно поправить
  const [formKey, setFormKey] = useState(0)

  const mutation = useMutation({
    mutationFn: deckApi(deck).createWord,
    onSuccess: (word) => {
      setAdded(word.word)
      setFormKey((value) => value + 1)
      queryClient.invalidateQueries({ queryKey: keys.list })
      queryClient.invalidateQueries({ queryKey: keys.overview })
      // Запись могла прийти с новыми метками, и у старых сменился счётчик
      queryClient.invalidateQueries({ queryKey: keys.labels })
    },
  })

  return (
    <div className="flex w-full max-w-xl flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-4xl font-bold text-ink">{title}</h1>
        <Link to={DECK_TEXT[deck].path} className="text-accent underline underline-offset-4">
          {back}
        </Link>
      </header>

      <WordForm
        key={formKey}
        deck={deck}
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
              «{added}» {DECK_TEXT[deck].added}
            </p>
          ) : null
        }
      />
    </div>
  )
}
