import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { ApiError, groupApi, groupQueryKeys } from '../api/client'
import type { GroupSummary } from '../api/types'
import { RoundsRunner, type RoundsApi } from '../components/RoundsRunner'
import { Button, ErrorBox, Spinner } from '../components/ui'
import { plural } from '../lib/format'

const WORD_FORMS: [string, string, string] = ['слово', 'слова', 'слов']

const LINK = 'text-accent underline underline-offset-4'

interface Summary {
  answered: number
  correct: number
}

function parseLabel(value: string | null): number | null {
  const id = Number(value)
  return value && Number.isInteger(id) && id > 0 ? id : null
}

/** «12 слов · круг 2 · пройдено 5 из 12» — где группа в своём круге. */
function cycleLine(group: Pick<GroupSummary, 'word_count' | 'done' | 'cycle'>): string {
  const parts = [`${group.word_count} ${plural(group.word_count, WORD_FORMS)}`]
  if (group.cycle > 0) parts.push(`круг ${group.cycle}`)
  parts.push(`пройдено ${group.done} из ${group.word_count}`)
  return parts.join(' · ')
}

function cycleIsComplete(group: GroupSummary): boolean {
  return group.word_count > 0 && group.done === group.word_count
}

function useGroups() {
  return useQuery({ queryKey: groupQueryKeys.groups, queryFn: groupApi.groups })
}

/**
 * «Учить группу»: без `?label=` — выбор метки, с ним — занятие по её словам.
 * Занятие идёт теми же раундами, что повторение, но расписание, статусы и
 * статистику не трогает: на сервере у него свой круг и свой журнал.
 */
export function GroupStudyPage() {
  const [params] = useSearchParams()
  const labelId = parseLabel(params.get('label'))
  // key: другая метка — другое занятие, очередь и итог собираются заново
  return labelId === null ? <GroupList /> : <GroupSession key={labelId} labelId={labelId} />
}

function GroupList() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useGroups()

  // Подтверждения нет: прогресс слов не стирается, теряется только место в круге
  const restart = useMutation({
    mutationFn: groupApi.restart,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: groupQueryKeys.groups }),
  })

  if (isLoading) return <Spinner />
  if (error) return <ErrorBox message={(error as Error).message} />
  if (!data) return null

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-center text-4xl font-bold text-ink">Учить группу</h1>
        <p className="max-w-md text-center text-muted">
          Групп пока нет: группа — это слова с одной меткой. Заведите метки и поставьте их
          словам.
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link to="/settings?tab=labels" className={LINK}>
            Метки
          </Link>
          <Link to="/" className={LINK}>
            На главную
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full max-w-2xl flex-col gap-8">
      <header className="flex flex-col items-center gap-2">
        <h1 className="text-center text-4xl font-bold text-ink">Учить группу</h1>
        <p className="text-center text-muted">
          Слова одной метки в любом статусе — пять раундов без знакомства. Расписание и
          статистика не меняются.
        </p>
      </header>

      {restart.error ? <ErrorBox message={(restart.error as Error).message} /> : null}

      <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline">
        {data.map((group) => (
          <li
            key={group.label_id}
            className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex flex-col gap-1">
              <span className="text-lg font-semibold text-ink">{group.name}</span>
              <span className="text-sm text-muted">{cycleLine(group)}</span>
              {cycleIsComplete(group) ? (
                <span className="text-sm text-muted">следующее занятие начнёт новый круг</span>
              ) : null}
            </div>
            <div className="flex items-center gap-3">
              {group.done > 0 ? (
                <Button
                  variant="ghost"
                  className="px-4 py-2 text-base"
                  disabled={restart.isPending}
                  onClick={() => restart.mutate(group.label_id)}
                >
                  Начать круг заново
                </Button>
              ) : null}
              {group.word_count > 0 ? (
                <Link
                  to={`/study/group?label=${group.label_id}`}
                  className="rounded-md bg-accent px-6 py-2 text-base font-semibold text-white transition-colors hover:bg-accent-hover"
                >
                  Учить
                </Link>
              ) : (
                <span className="text-sm text-muted">нет слов</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function GroupSession({ labelId }: { labelId: number }) {
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<Summary | null>(null)
  const groups = useGroups()

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['group-study', 'session', labelId],
    queryFn: () => groupApi.session(labelId),
    // Порция — снимок на момент запроса; фоновые перезапросы сбили бы очередь
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
  })

  const roundsApi = useMemo<RoundsApi>(
    () => ({
      answer: (payload) => groupApi.answer({ ...payload, label_id: labelId }),
      finish: groupApi.finish,
    }),
    [labelId],
  )

  const handleFinished = useCallback(
    (result: Summary) => {
      setSummary(result)
      queryClient.invalidateQueries({ queryKey: groupQueryKeys.groups })
    },
    [queryClient],
  )

  // Следующая порция берёт непройденные слова круга (FR-005)
  const nextPortion = async () => {
    setSummary(null)
    await refetch()
  }

  const backLinks = (
    <div className="flex flex-wrap justify-center gap-4">
      <Link to="/study/group" className={LINK}>
        К списку групп
      </Link>
      <Link to="/" className={LINK}>
        На главную
      </Link>
    </div>
  )

  if (isLoading) return <Spinner label="Собираем слова группы…" />
  if (error) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <div className="flex flex-col items-center gap-6">
        <ErrorBox message={missing ? 'Такой метки нет — возможно, её удалили.' : error.message} />
        {backLinks}
      </div>
    )
  }
  if (!data) return null

  if (summary) {
    const accuracy = summary.answered
      ? Math.round((summary.correct / summary.answered) * 100)
      : 0
    const group = groups.data?.find((item) => item.label_id === labelId)
    return (
      <div className="flex flex-col items-center gap-8">
        <h1 className="text-5xl font-bold text-ink">Сессия завершена</h1>
        <div className="flex flex-col items-center gap-1">
          <p className="text-lg text-muted">
            {summary.answered} {plural(summary.answered, ['ответ', 'ответа', 'ответов'])} ·
            точность {accuracy}%
          </p>
          {group ? (
            <>
              <p className="text-muted">
                {group.name}: {cycleLine(group)}
              </p>
              {cycleIsComplete(group) ? (
                <p className="text-sm text-muted">следующее занятие начнёт новый круг</p>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="flex items-start gap-4">
          <Link
            to="/"
            className="rounded-md bg-neutral-btn px-8 py-4 text-lg font-semibold text-white transition-colors hover:bg-neutral-btn-hover"
          >
            На главную
          </Link>
          <Button onClick={nextPortion} disabled={isFetching}>
            Следующая порция
          </Button>
        </div>
      </div>
    )
  }

  // Ключ занятия сервер выдаёт ровно тогда, когда в группе есть слова
  if (!data.session_id) {
    return (
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-center text-4xl font-bold text-ink">В группе нечего учить</h1>
        <p className="max-w-md text-center text-muted">
          У метки «{data.name}» сейчас нет слов. Поставьте её словам в словаре.
        </p>
        {backLinks}
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <p className="text-sm text-muted">
        {data.name} · круг {data.cycle}
      </p>
      <RoundsRunner
        key={data.session_id}
        api={roundsApi}
        rounds={data.rounds}
        sessionId={data.session_id}
        onFinished={handleFinished}
        finishErrorText="Ответы сохранены, но круг группы ещё не отмечен."
      />
    </div>
  )
}
