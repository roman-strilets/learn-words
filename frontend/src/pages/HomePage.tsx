import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
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

export function HomePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['overview'],
    queryFn: api.overview,
  })

  if (isLoading) return <Spinner />
  if (error) return <ErrorBox message={(error as Error).message} />
  if (!data) return null

  const ready = data.new + data.due_now

  return (
    <div className="flex flex-col items-center gap-10">
      <header className="flex flex-col items-center gap-3">
        <h1 className="text-center text-5xl font-bold text-ink">Изучение слов</h1>
        <p className="text-lg text-muted">
          {ready > 0 ? 'Выберите, чем сегодня займёмся' : 'На сегодня всё повторено'}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="В словаре" value={data.total_words} />
        <StatTile label="Изучается" value={data.learning} />
        <StatTile label="На повторении" value={data.review} />
        <StatTile label="Знаю" value={data.known} />
      </div>

      <StudyModeLinks
        hints={{
          learn: `${data.new} ${plural(data.new, ['новое слово', 'новых слова', 'новых слов'])}`,
          review: `${data.due_now} ${plural(data.due_now, ['слово готово', 'слова готовы', 'слов готово'])}`,
        }}
      />

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
    </div>
  )
}
