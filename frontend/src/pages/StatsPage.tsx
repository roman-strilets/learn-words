import { useQuery } from '@tanstack/react-query'

import { deckApi, queryKeys } from '../api/client'
import type { DailyStat, Deck } from '../api/types'
import { ErrorBox, Spinner } from '../components/ui'

const DAYS = 30

function DailyChart({ data }: { data: DailyStat[] }) {
  const peak = Math.max(1, ...data.map((day) => day.answers))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex h-48 items-end gap-1 overflow-x-auto">
        {data.map((day) => {
          const height = (day.answers / peak) * 100
          const wrong = day.answers - day.correct
          return (
            <div
              key={day.date}
              className="flex min-w-3 flex-1 flex-col justify-end"
              title={`${day.date}: ${day.answers} отв., верно ${day.correct}`}
            >
              {day.answers > 0 ? (
                <div
                  className="flex w-full flex-col justify-end"
                  style={{ height: `${Math.max(height, 3)}%` }}
                >
                  {wrong > 0 ? (
                    <div
                      className="w-full bg-wrong/60"
                      style={{ height: `${(wrong / day.answers) * 100}%` }}
                    />
                  ) : null}
                  <div
                    className="w-full bg-correct"
                    style={{ height: `${(day.correct / day.answers) * 100}%` }}
                  />
                </div>
              ) : (
                <div className="h-px w-full bg-hairline" />
              )}
            </div>
          )
        })}
      </div>
      <div className="flex justify-between text-xs text-muted">
        <span>{data[0]?.date}</span>
        <span>{data[data.length - 1]?.date}</span>
      </div>
      <div className="flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1">
          <span className="inline-block size-3 bg-correct" /> верно
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block size-3 bg-wrong/60" /> ошибки
        </span>
      </div>
    </div>
  )
}

const DECK_TITLE: Record<Deck, { title: string; total: string }> = {
  words: { title: 'Слова', total: 'Слов в словаре' },
  phrases: { title: 'Фразы', total: 'Фраз в словаре' },
}

/** Статистика одной колоды: числа слов и фраз не суммируются — у них свои журналы. */
function DeckStats({ deck }: { deck: Deck }) {
  const client = deckApi(deck)
  const keys = queryKeys(deck)
  const overview = useQuery({ queryKey: keys.overview, queryFn: client.overview })
  const daily = useQuery({ queryKey: keys.daily(DAYS), queryFn: () => client.daily(DAYS) })

  if (overview.isLoading || daily.isLoading) return <Spinner />
  const error = overview.error ?? daily.error
  if (error) return <ErrorBox message={(error as Error).message} />
  if (!overview.data || !daily.data) return null

  const totalAnswers = daily.data.reduce((sum, day) => sum + day.answers, 0)
  const totalCorrect = daily.data.reduce((sum, day) => sum + day.correct, 0)
  const accuracy = totalAnswers ? Math.round((totalCorrect / totalAnswers) * 100) : 0

  const rows: Array<[string, number | string]> = [
    [DECK_TITLE[deck].total, overview.data.total_words],
    ['Ещё не начато', overview.data.new],
    ['Изучается', overview.data.learning],
    ['На повторении', overview.data.review],
    ['Помечено «знаю»', overview.data.known],
    ['Готово к повторению сейчас', overview.data.due_now],
    ['Подойдёт сегодня', overview.data.due_today],
    ['Дней подряд', overview.data.streak_days],
    [`Точность за ${DAYS} дней`, `${accuracy}%`],
  ]

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-2xl font-bold text-ink">{DECK_TITLE[deck].title}</h2>

      <div className="flex flex-col gap-3">
        <h3 className="text-lg font-semibold text-ink-soft">Ответы за {DAYS} дней</h3>
        <DailyChart data={daily.data} />
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-lg font-semibold text-ink-soft">Сводка</h3>
        <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex justify-between border-b border-hairline py-2"
            >
              <dt className="text-muted">{label}</dt>
              <dd className="font-semibold text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

export function StatsPage() {
  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <h1 className="text-4xl font-bold text-ink">Статистика</h1>
      <DeckStats deck="words" />
      <DeckStats deck="phrases" />
    </div>
  )
}
