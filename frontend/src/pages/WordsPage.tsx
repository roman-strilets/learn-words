import { useState } from 'react'
import { Link } from 'react-router'

import { AutoLabelPanel } from '../components/AutoLabelPanel'
import { DictionaryList } from '../components/DictionaryList'

export function WordsPage() {
  const [autoLabelOpen, setAutoLabelOpen] = useState(false)

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

      <DictionaryList
        deck="words"
        tools={
          <button
            type="button"
            onClick={() => setAutoLabelOpen((value) => !value)}
            aria-expanded={autoLabelOpen}
            className={`rounded px-3 py-2 text-sm transition-colors ${
              autoLabelOpen ? 'bg-accent text-white' : 'bg-panel text-ink-soft hover:bg-hairline'
            }`}
          >
            Разметить автоматически
          </button>
        }
        // Панель берёт фильтры «Словаря»: разметка идёт ровно по тем словам,
        // что видны в списке
        panel={(filters) =>
          autoLabelOpen ? (
            <AutoLabelPanel filters={filters} onClose={() => setAutoLabelOpen(false)} />
          ) : null
        }
      />
    </div>
  )
}
