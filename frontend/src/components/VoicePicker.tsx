import { useSpeech } from '../speech/SpeechProvider'

/** Переключатель голосов с горячими клавишами 1–9, как на макете диктанта. */
export function VoicePicker({ onPick }: { onPick?: (text: string) => void }) {
  const { voices, selected, selectVoice } = useSpeech()

  if (voices.length === 0) return null

  return (
    <div className="flex flex-wrap justify-center gap-5">
      {voices.map((voice, index) => {
        const active = selected?.uri === voice.uri
        return (
          <button
            key={voice.uri}
            type="button"
            onClick={() => {
              selectVoice(voice.uri)
              onPick?.(voice.name)
            }}
            className={`flex w-20 flex-col items-center gap-1 transition-opacity ${
              active ? 'opacity-100' : 'opacity-45 hover:opacity-75'
            }`}
            title={`${voice.name} (${voice.lang})`}
          >
            <span
              className={`text-sm ${active ? 'font-semibold text-ink' : 'text-muted'}`}
            >
              {index + 1}
            </span>
            <span className="text-base leading-none">{active ? voice.flag : ' '}</span>
            <span className="text-3xl leading-none">{voice.emoji}</span>
            <span
              className={`truncate text-sm ${active ? 'font-semibold text-ink' : 'text-muted'}`}
            >
              {voice.name}
            </span>
          </button>
        )
      })}
    </div>
  )
}
