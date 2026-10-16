import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { deckApi, queryKeys } from '../api/client'
import type { Deck, StatsOverview } from '../api/types'
import { plural } from '../lib/format'
import { StudyModeLinks } from '../components/StudyModeLinks'
import { ErrorBox, Spinner } from '../components/ui'

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-hairline px-6 py-5">
      <span className="text-3xl font-bold text-ink">{value}</span>
      <span className="text-sm text-muted">{label}</span>
    </div>
  )
}

const BLOCK: Record<
  Deck,
  { title: string; fresh: [string, string, string]; due: [string, string, string] }
> = {
  words: {
    title: 'Слова',
    fresh: ['новое слово', 'новых слова', 'новых слов'],
    due: ['слово готово', 'слова готовы', 'слов готово'],
  },
  phrases: {
    title: 'Фразы',
    fresh: ['новая фраза', 'новые фразы', 'новых фраз'],
    due: ['фраза готова', 'фразы готовы', 'фраз готово'],
  },
}

/** Блок колоды: плитки, кнопки занятий с подсказками и числа за сегодня. */
function DeckBlock({ deck, data }: { deck: Deck; data: StatsOverview }) {
  const text = BLOCK[deck]
  return (
    <section className="flex w-full flex-col items-center gap-6">
      <h2 className="text-2xl font-bold text-ink">{text.title}</h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="В словаре" value={data.total_words} />
        <StatTile label="Изучается" value={data.learning} />
        <StatTile label="На повторении" value={data.review} />
        <StatTile label="Знаю" value={data.known} />
      </div>

      <StudyModeLinks
        deck={deck}
        hints={{
          learn: `${data.new} ${plural(data.new, text.fresh)}`,
          review: `${data.due_now} ${plural(data.due_now, text.due)}`,
        }}
      >
        {/* Занятие по метке есть только у слов: у фраз своих групп нет */}
        {deck === 'words' ? (
          <div className="flex flex-col items-center gap-1">
            <Link
              to="/study/group"
              className="rounded-md bg-neutral-btn px-10 py-4 text-xl font-semibold text-white transition-colors hover:bg-neutral-btn-hover"
            >
              Учить группу
            </Link>
            <span className="text-sm text-muted">по метке</span>
          </div>
        ) : null}
      </StudyModeLinks>

      <dl className="flex flex-wrap justify-center gap-x-8 gap-y-2 text-sm text-muted">
        <div className="flex gap-2">
          <dt>Ответов сегодня:</dt>
          <dd className="font-semibold text-ink">{data.answers_today}</dd>
        </div>
        <div className="flex gap-2">
          <dt>Новых сегодня:</dt>
          <dd className="font-semibold text-ink">{data.new_today}</dd>
        </div>
        <div className="flex gap-2">
          <dt>Дней подряд:</dt>
          <dd className="font-semibold text-ink">{data.streak_days}</dd>
        </div>
      </dl>
    </section>
  )
}

function useOverview(deck: Deck) {
  return useQuery({ queryKey: queryKeys(deck).overview, queryFn: deckApi(deck).overview })
}

export function HomePage() {
  const words = useOverview('words')
  const phrases = useOverview('phrases')

  if (words.isLoading || phrases.isLoading) return <Spinner />
  const error = words.error ?? phrases.error
  if (error) return <ErrorBox message={(error as Error).message} />
  if (!words.data || !phrases.data) return null

  const ready = words.data.new + words.data.due_now + phrases.data.new + phrases.data.due_now

  return (
    <div className="flex flex-col items-center gap-12">
      <header className="flex flex-col items-center gap-3">
        <h1 className="text-center text-5xl font-bold text-ink">Изучение слов</h1>
        <p className="text-lg text-muted">
          {ready > 0 ? 'Выберите, чем сегодня займёмся' : 'На сегодня всё повторено'}
        </p>
      </header>

      <DeckBlock deck="words" data={words.data} />
      <DeckBlock deck="phrases" data={phrases.data} />
    </div>
  )
}
