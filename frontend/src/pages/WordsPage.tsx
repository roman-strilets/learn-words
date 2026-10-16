import { useState } from 'react'
import { Link } from 'react-router'

import { AutoLabelPanel } from '../components/AutoLabelPanel'
import { DictionaryList } from '../components/DictionaryList'
import { ImportPanel } from '../components/ImportPanel'

type Panel = 'autoLabel' | 'import'

const toggleClass = (open: boolean) =>
  `rounded px-3 py-2 text-sm transition-colors ${
    open ? 'bg-accent text-white' : 'bg-panel text-ink-soft hover:bg-hairline'
  }`

export function WordsPage() {
  // Одна панель за раз: обе занимают место над списком
  const [panel, setPanel] = useState<Panel | null>(null)
  const toggle = (next: Panel) => setPanel((value) => (value === next ? null : next))

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
          <>
            <button
              type="button"
              onClick={() => toggle('import')}
              aria-expanded={panel === 'import'}
              className={toggleClass(panel === 'import')}
            >
              Импорт из CSV
            </button>
            <button
              type="button"
              onClick={() => toggle('autoLabel')}
              aria-expanded={panel === 'autoLabel'}
              className={toggleClass(panel === 'autoLabel')}
            >
              Разметить автоматически
            </button>
          </>
        }
        // Панель разметки берёт фильтры «Словаря»: разметка идёт ровно по тем
        // словам, что видны в списке
        panel={(filters) =>
          panel === 'autoLabel' ? (
            <AutoLabelPanel filters={filters} onClose={() => setPanel(null)} />
          ) : panel === 'import' ? (
            <ImportPanel onClose={() => setPanel(null)} />
          ) : null
        }
      />
    </div>
  )
}
