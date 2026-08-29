import type { WordStatusValue } from '../api/types'

/**
 * Бэкенд отдаёт naive UTC («2026-08-16T10:00:00»), а `new Date()` трактует
 * строку без зоны как локальное время — без явного Z даты уезжают на смещение.
 */
export function parseUtc(value: string): Date {
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

const DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

export function formatDate(value: string): string {
  return DATE_FORMAT.format(parseUtc(value))
}

const DAY_MS = 24 * 60 * 60 * 1000

/** «сейчас» / «завтра» / «через 12 дней» — понятнее абсолютной даты. */
export function formatDue(value: string): string {
  const diff = parseUtc(value).getTime() - Date.now()
  if (diff <= 0) return 'сейчас'

  const days = Math.ceil(diff / DAY_MS)
  if (days === 1) return 'завтра'
  if (days < 7) return `через ${days} дн.`
  return formatDate(value)
}

export const STATUS_LABEL: Record<WordStatusValue, string> = {
  new: 'Новое',
  learning: 'Изучается',
  review: 'На повторении',
  known: 'Знаю',
  suspended: 'Отложено',
}

export const STATUS_CLASS: Record<WordStatusValue, string> = {
  new: 'bg-hairline text-ink-soft',
  learning: 'bg-accent/10 text-accent',
  review: 'bg-correct-soft text-correct',
  known: 'bg-panel text-muted',
  suspended: 'bg-wrong-soft text-wrong',
}

export function plural(count: number, forms: [string, string, string]): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1]
  return forms[2]
}
