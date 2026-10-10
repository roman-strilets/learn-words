import { Link } from 'react-router'

import { DictionaryList } from '../components/DictionaryList'

/** Словарь фраз: тот же список, что у слов, но свои записи, метки и фильтры. */
export function PhrasesPage() {
  return (
    <div className="flex w-full max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-4xl font-bold text-ink">Фразы</h1>
        <Link
          to="/phrases/new"
          className="rounded-md bg-accent px-6 py-3 font-semibold text-white transition-colors hover:bg-accent-hover"
        >
          Добавить фразу
        </Link>
      </header>

      <DictionaryList deck="phrases" />
    </div>
  )
}
