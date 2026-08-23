import { Link } from 'react-router'

import type { StudyMode } from '../api/types'

export const MODE_LABEL: Record<StudyMode, string> = {
  learn: 'Учить слова',
  review: 'Повторить слова',
}

const MODE_STYLE: Record<StudyMode, string> = {
  learn: 'bg-accent hover:bg-accent-hover',
  review: 'bg-neutral-btn hover:bg-neutral-btn-hover',
}

const MODES: StudyMode[] = ['learn', 'review']

export function studyPath(mode: StudyMode): string {
  return `/study?mode=${mode}`
}

/** Две кнопки старта занятия: подписи снизу показывают, сколько слов готово. */
export function StudyModeLinks({ hints }: { hints?: Record<StudyMode, string> }) {
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
      {MODES.map((mode) => (
        <div key={mode} className="flex flex-col items-center gap-1">
          <Link
            to={studyPath(mode)}
            className={`rounded-md px-10 py-4 text-xl font-semibold text-white transition-colors ${MODE_STYLE[mode]}`}
          >
            {MODE_LABEL[mode]}
          </Link>
          {hints ? <span className="text-sm text-muted">{hints[mode]}</span> : null}
        </div>
      ))}
    </div>
  )
}
