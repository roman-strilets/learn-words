import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import type { ClassifyBatch, ClassifyFilters, Label } from '../api/types'
import { useLocalStorage } from '../hooks/useLocalStorage'
import { plural } from '../lib/format'
import { ErrorBox } from './ui'

/**
 * Слов в пачке по умолчанию. Одна пачка — один запрос к модели: 20 слов
 * локальная 9B-модель размечает с запасом до таймаута в 120 с, а прогресс
 * при этом обновляется достаточно часто.
 */
const DEFAULT_BATCH_SIZE = 20
/** Совпадает с `classifier_batch_max` на сервере: больше он ответит 422. */
const MAX_BATCH_SIZE = 100

const PRIMARY =
  'rounded-md bg-accent px-4 py-2 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50'
const SECONDARY =
  'rounded-md bg-panel px-4 py-2 text-ink-soft transition-colors hover:bg-hairline disabled:cursor-not-allowed disabled:opacity-50'
const LINK = 'text-muted underline underline-offset-4 hover:text-ink disabled:opacity-50'
const INPUT =
  'rounded border border-hairline px-3 py-2 outline-none focus:border-accent disabled:opacity-50'

const words = (count: number) => `${count} ${plural(count, ['слово', 'слова', 'слов'])}`

type Phase = 'idle' | 'running' | 'stopping' | 'stopped' | 'done' | 'failed'
type StartMode = 'beginning' | 'resume' | 'word'

/** Место, с которого продолжить: курсор и слово, которое там стоит. */
interface Cursor {
  from_id: number
  word: string
}

/** Сводка этапа: копится из ответов пачек. */
interface Summary {
  /** Слова, по которым модель ответила */
  processed: number
  /** Сколько слов получили каждую метку — по id, с названием из ответа */
  added: Record<number, { name: string; count: number }>
  /** Метка не подошла или уже стояла */
  unchanged: number
  /** Слова удалили, пока модель думала */
  skipped: number
}

const EMPTY: Summary = { processed: 0, added: {}, unchanged: 0, skipped: 0 }

function addBatch(summary: Summary, batch: ClassifyBatch): Summary {
  const added = { ...summary.added }
  let unchanged = summary.unchanged
  for (const result of batch.results) {
    if (result.added && result.label) {
      const prev = added[result.label.id]
      added[result.label.id] = { name: result.label.name, count: (prev?.count ?? 0) + 1 }
    } else {
      unchanged += 1
    }
  }
  return {
    processed: summary.processed + batch.results.length,
    added,
    unchanged,
    skipped: summary.skipped + batch.skipped,
  }
}

/** Целое из поля ввода; пусто или не число — `null`. */
function parseCount(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null
  return Number(text.trim())
}

function SummaryView({ summary }: { summary: Summary }) {
  const added = Object.values(summary.added).sort((a, b) => b.count - a.count)
  return (
    <div className="flex flex-col gap-2 text-ink-soft">
      <p>Обработано: {words(summary.processed)}</p>
      {added.length ? (
        <div>
          <p>Получили метку:</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {added.map((item) => (
              <li key={item.name} className="rounded bg-panel px-2 py-0.5 text-sm">
                {item.name} — {item.count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p>Остались без новой метки: {words(summary.unchanged)}</p>
      {summary.skipped ? <p>Пропущено удалённых: {words(summary.skipped)}</p> : null}
    </div>
  )
}

/** Чипы набора меток: все включены, выключенная модели не предлагается. */
function LabelChips({
  labels,
  excluded,
  onToggle,
}: {
  labels: Label[]
  excluded: Set<number>
  onToggle: (id: number) => void
}) {
  return (
    <ul className="flex flex-wrap gap-2">
      {labels.map((label) => {
        const on = !excluded.has(label.id)
        return (
          <li key={label.id}>
            <button
              type="button"
              onClick={() => onToggle(label.id)}
              aria-pressed={on}
              className={`rounded px-3 py-1 text-sm transition-colors ${
                on ? 'bg-accent text-white' : 'bg-panel text-muted line-through hover:bg-hairline'
              }`}
            >
              {label.name}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** «Начать с»: выбор записи поиском по словарю. */
function WordPicker({
  picked,
  onPick,
}: {
  picked: Cursor | null
  onPick: (cursor: Cursor | null) => void
}) {
  const [search, setSearch] = useState('')
  const term = search.trim()
  const { data } = useQuery({
    queryKey: ['words', 'autoLabelPick', term],
    queryFn: () => api.listWords({ search: term, limit: 10 }),
    enabled: term.length > 0,
  })

  if (picked) {
    return (
      <span className="flex items-center gap-3">
        <span className="font-semibold text-ink">{picked.word}</span>
        <button type="button" onClick={() => onPick(null)} className={LINK}>
          другое слово
        </button>
      </span>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Найти слово"
        aria-label="Слово, с которого начать"
        className={INPUT}
      />
      {term && data ? (
        data.items.length ? (
          <ul className="flex flex-col">
            {data.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onPick({ from_id: item.id, word: item.word })}
                  className="w-full rounded px-3 py-1 text-left hover:bg-panel"
                >
                  <span className="text-ink">{item.word}</span>{' '}
                  <span className="text-sm text-muted">{item.translation}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Ничего не найдено</p>
        )
      ) : null}
    </div>
  )
}

/**
 * Автоматическая разметка на «Словаре»: проходит пачками слова под текущими
 * фильтрами и ставит каждому подходящую метку из набора или ничего.
 *
 * Этап ведёт браузер: сервер размечает одну пачку за запрос и отдаёт курсор
 * следующей, поэтому этап можно ограничить, остановить и продолжить с места
 * остановки. Метки только добавляются, прогресс не меняется.
 */
export function AutoLabelPanel({
  filters,
  onClose,
}: {
  filters: ClassifyFilters
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { data: labels } = useQuery({ queryKey: ['labels'], queryFn: api.listLabels })

  // Удобство одного браузера, а не данные: при пустом хранилище действуют
  // значения по умолчанию и этап начинается с начала
  const [storedBatchSize, setStoredBatchSize] = useLocalStorage(
    'autoLabel.batchSize',
    DEFAULT_BATCH_SIZE,
  )
  const [storedLimit, setStoredLimit] = useLocalStorage<number | null>('autoLabel.limit', null)
  const [resume, setResume] = useLocalStorage<Cursor | null>('autoLabel.resume', null)

  const [batchText, setBatchText] = useState(String(storedBatchSize))
  const [limitText, setLimitText] = useState(storedLimit === null ? '' : String(storedLimit))
  // Храним выключенные, а не включённые: новая метка сразу входит в набор,
  // удалённая сама выпадает из списка `labels`
  const [excluded, setExcluded] = useState<Set<number>>(new Set())
  const [startMode, setStartMode] = useState<StartMode>(resume ? 'resume' : 'beginning')
  const [picked, setPicked] = useState<Cursor | null>(null)

  const [phase, setPhase] = useState<Phase>('idle')
  const [summary, setSummary] = useState<Summary>(EMPTY)
  // Всего в этапе: обработанные плюс `remaining` последней пачки, не больше лимита
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Откуда продолжить после остановки или ошибки; `null` в `from_id` — с начала
  const [cursor, setCursor] = useState<{ from_id: number | null; word: string | null }>({
    from_id: null,
    word: null,
  })
  // Просьба остановиться читается между пачками: оборванный `fetch` не отменил
  // бы работу сервера, и мы не узнали бы, применилась ли пачка
  const stopRef = useRef(false)
  // Панель закрыли посреди этапа — следующая пачка не начинается
  useEffect(
    () => () => {
      stopRef.current = true
    },
    [],
  )

  const selected = labels?.filter((label) => !excluded.has(label.id)) ?? []
  const batchSize = parseCount(batchText)
  const batchValid = batchSize !== null && batchSize >= 1 && batchSize <= MAX_BATCH_SIZE
  const limit = limitText.trim() ? parseCount(limitText) : null
  const limitValid = !limitText.trim() || (limit !== null && limit >= 1)

  const startFrom: Cursor | null =
    startMode === 'resume' ? resume : startMode === 'word' ? picked : null
  const startMissing = startMode !== 'beginning' && startFrom === null

  // Сколько слов попадёт в этап — тем же отбором, что у списка
  const { data: available } = useQuery({
    queryKey: ['words', 'autoLabelCount', filters, startFrom?.from_id ?? null],
    queryFn: () =>
      api.listWords({ ...filters, fromId: startFrom?.from_id ?? null, limit: 1 }),
    enabled: phase === 'idle' && !startMissing,
    select: (page) => page.total,
  })
  const stageCount =
    available === undefined ? null : limit !== null ? Math.min(available, limit) : available

  const active = phase === 'running' || phase === 'stopping'
  const hasLabels = Boolean(labels?.length)
  const canStart =
    selected.length > 0 && batchValid && limitValid && !startMissing && stageCount !== 0

  /** Слово, с которого начнётся следующая пачка, — для «Продолжить с «…»». */
  const wordAt = async (fromId: number) => {
    try {
      const page = await api.listWords({ ...filters, fromId, limit: 1 })
      return page.items[0]?.word ?? null
    } catch {
      return null
    }
  }

  /** `expected` — число слов этапа, если оно известно до первой пачки. */
  const run = async (
    from: { from_id: number | null; word: string | null },
    expected: number | null,
  ) => {
    if (!batchValid || batchSize === null || !limitValid) return
    const labelIds = selected.map((label) => label.id)
    setStoredBatchSize(batchSize)
    setStoredLimit(limit)
    stopRef.current = false
    let acc = EMPTY
    let fromId = from.from_id
    setPhase('running')
    setSummary(EMPTY)
    setTotal(expected)
    setError(null)
    setCursor(from)

    try {
      for (;;) {
        const seen = acc.processed + acc.skipped
        const batch: ClassifyBatch = await api.classifyBatch({
          ...filters,
          label_ids: labelIds,
          from_id: fromId,
          // Последняя пачка добирает ровно до лимита этапа
          limit: limit === null ? batchSize : Math.min(batchSize, limit - seen),
        })
        acc = addBatch(acc, batch)
        const seenNow = acc.processed + acc.skipped
        setSummary(acc)
        setTotal(
          limit === null
            ? seenNow + batch.remaining
            : Math.min(limit, seenNow + batch.remaining),
        )
        // Новые метки сразу видны в списке, счётчики на «Метках» актуальны
        queryClient.invalidateQueries({ queryKey: ['words'] })
        queryClient.invalidateQueries({ queryKey: ['labels'] })

        fromId = batch.next_from_id
        if (fromId === null) {
          // Выборка пройдена до конца — продолжать нечего
          setResume(null)
          setPhase('done')
          return
        }
        const next = { from_id: fromId, word: (await wordAt(fromId)) ?? '' }
        setCursor(next)
        // Место остановки пишется после каждой пачки: перезагрузка страницы
        // посреди этапа его не теряет. Этап, упёршийся в лимит, тоже его
        // оставляет — следующий этап естественно продолжит отсюда
        setResume(next)
        if (limit !== null && seenNow >= limit) {
          setPhase('done')
          return
        }
        if (stopRef.current) {
          setPhase('stopped')
          return
        }
      }
    } catch (err) {
      // Результаты прежних пачек уже на словах — показываем только причину
      setError(err instanceof Error ? err.message : String(err))
      setPhase('failed')
    }
  }

  const stop = () => {
    stopRef.current = true
    setPhase('stopping')
  }

  const newStage = () => {
    setPhase('idle')
    setSummary(EMPTY)
    setTotal(null)
    setError(null)
    setPicked(null)
    setStartMode(resume ? 'resume' : 'beginning')
  }

  const toggleLabel = (id: number) => {
    const next = new Set(excluded)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExcluded(next)
  }

  const seen = summary.processed + summary.skipped
  const percent = total ? Math.min(100, Math.round((seen / total) * 100)) : 0

  return (
    <section className="flex flex-col gap-5 rounded-md border border-hairline p-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold text-ink">Автоматическая разметка</h2>
        <button type="button" onClick={onClose} disabled={active} className={LINK}>
          Закрыть
        </button>
      </div>

      {labels && !hasLabels ? (
        <p className="text-muted">
          Сначала заведите метки на вкладке{' '}
          <Link to="/settings?tab=labels" className="text-accent underline underline-offset-4">
            «Метки»
          </Link>
          .
        </p>
      ) : (
        <p className="text-muted">
          Модель выберет каждому слову под текущими фильтрами «Словаря» одну метку из
          набора или ни одной. Метки, которые уже стоят, не снимаются; прогресс не
          меняется. Слова идут в порядке словаря.
        </p>
      )}

      {phase === 'idle' && labels && hasLabels ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm text-muted">Метки</span>
            <LabelChips labels={labels} excluded={excluded} onToggle={toggleLabel} />
            {selected.length === 0 ? (
              <p className="text-sm text-wrong">Включите хотя бы одну метку</p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-6">
            <label className="flex flex-col gap-2">
              <span className="text-sm text-muted">Не больше, слов</span>
              <input
                value={limitText}
                onChange={(event) => setLimitText(event.target.value)}
                inputMode="numeric"
                placeholder="все"
                className={`w-28 ${INPUT}`}
              />
            </label>
            <label className="flex flex-col gap-2">
              <span className="text-sm text-muted">Размер пачки</span>
              <input
                value={batchText}
                onChange={(event) => setBatchText(event.target.value)}
                inputMode="numeric"
                className={`w-28 ${INPUT}`}
              />
            </label>
          </div>
          {!limitValid ? <p className="text-sm text-wrong">Лимит — целое число от 1</p> : null}
          {!batchValid ? (
            <p className="text-sm text-wrong">Размер пачки — от 1 до {MAX_BATCH_SIZE}</p>
          ) : null}

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm text-muted">Начать с</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={startMode === 'beginning'}
                onChange={() => setStartMode('beginning')}
              />
              начала
            </label>
            {resume ? (
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  checked={startMode === 'resume'}
                  onChange={() => setStartMode('resume')}
                />
                места остановки{resume.word ? ` — «${resume.word}»` : ''}
              </label>
            ) : null}
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={startMode === 'word'}
                onChange={() => setStartMode('word')}
              />
              выбранного слова
            </label>
            {startMode === 'word' ? (
              <div className="ml-6">
                <WordPicker picked={picked} onPick={setPicked} />
              </div>
            ) : null}
          </fieldset>

          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() =>
                run(
                  { from_id: startFrom?.from_id ?? null, word: startFrom?.word ?? null },
                  stageCount,
                )
              }
              disabled={!canStart}
              className={PRIMARY}
            >
              Запустить
            </button>
            {startMissing ? (
              <span className="text-sm text-muted">Выберите слово, с которого начать</span>
            ) : stageCount === 0 ? (
              <span className="text-sm text-muted">
                Под текущими фильтрами{startFrom ? ' с этого места' : ''} слов нет
              </span>
            ) : stageCount !== null ? (
              <span className="text-sm text-muted">В этап попадёт {words(stageCount)}</span>
            ) : null}
          </div>
        </div>
      ) : null}

      {phase !== 'idle' ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">
            {phase === 'running' ? 'Размечаем… ' : null}
            {phase === 'stopping' ? 'Останавливается после текущей пачки… ' : null}
            обработано {seen}
            {total !== null ? ` из ${total}` : null}
          </p>
          <div className="h-2 overflow-hidden rounded bg-hairline">
            <div
              className="h-full bg-accent transition-[width]"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ) : null}

      {phase === 'running' ? (
        <div>
          <button type="button" onClick={stop} className={SECONDARY}>
            Остановить
          </button>
        </div>
      ) : null}

      {error ? <ErrorBox message={error} /> : null}

      {phase === 'done' || phase === 'stopped' || phase === 'failed' ? (
        <>
          <SummaryView summary={summary} />
          <div className="flex flex-wrap items-center gap-4">
            {phase !== 'done' ? (
              <button
                type="button"
                onClick={() => run(cursor, null)}
                disabled={selected.length === 0}
                className={PRIMARY}
              >
                {cursor.word ? `Продолжить с «${cursor.word}»` : 'Продолжить'}
              </button>
            ) : null}
            <button type="button" onClick={newStage} className={SECONDARY}>
              Новый этап
            </button>
          </div>
        </>
      ) : null}
    </section>
  )
}
