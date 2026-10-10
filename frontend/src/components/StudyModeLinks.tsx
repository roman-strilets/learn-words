import { Link } from 'react-router'

import type { Deck, StudyMode } from '../api/types'

const LABELS: Record<Deck, Record<StudyMode, string>> = {
  words: { learn: 'Учить слова', review: 'Повторить слова' },
  phrases: { learn: 'Учить фразы', review: 'Повторить фразы' },
}

export function modeLabel(mode: StudyMode, deck: Deck = 'words'): string {
  return LABELS[deck][mode]
}

const MODE_STYLE: Record<StudyMode, string> = {
  learn: 'bg-accent hover:bg-accent-hover',
  review: 'bg-neutral-btn hover:bg-neutral-btn-hover',
}

const MODES: StudyMode[] = ['learn', 'review']

/** Адрес занятия. Без `deck` в адресе занятие — со словами, как раньше. */
export function studyPath(mode: StudyMode, deck: Deck = 'words'): string {
  return deck === 'words' ? `/study?mode=${mode}` : `/study?deck=${deck}&mode=${mode}`
}

/** Две кнопки старта занятия: подписи снизу показывают, сколько записей готово. */
export function StudyModeLinks({
  deck = 'words',
  hints,
}: {
  deck?: Deck
  hints?: Record<StudyMode, string>
}) {
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
      {MODES.map((mode) => (
        <div key={mode} className="flex flex-col items-center gap-1">
          <Link
            to={studyPath(mode, deck)}
            className={`rounded-md px-10 py-4 text-xl font-semibold text-white transition-colors ${MODE_STYLE[mode]}`}
          >
            {modeLabel(mode, deck)}
          </Link>
          {hints ? <span className="text-sm text-muted">{hints[mode]}</span> : null}
        </div>
      ))}
    </div>
  )
}
