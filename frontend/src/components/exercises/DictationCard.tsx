import { useEffect, useRef, useState } from 'react'

import type { DictationExercise } from '../../api/types'
import { useSpeech } from '../../speech/SpeechProvider'
import { SpeakerIcon } from '../icons'
import { Caption, HintButton } from '../ui'
import type { ExerciseCardProps } from './types'

export function DictationCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<DictationExercise>) {
  const { speak, supported } = useSpeech()
  const [value, setValue] = useState('')
  const [usedHint, setUsedHint] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setValue('')
    setUsedHint(false)
    inputRef.current?.focus()
    speak(exercise.audio_text)
  }, [exercise.word_id, exercise.audio_text, speak])

  const submit = () => {
    if (locked) return
    onAnswer({ answer: value, usedHint })
  }

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-8">
      <div className="flex items-center gap-3">
        <HintButton active={usedHint} onClick={() => setUsedHint(true)} />
        <Caption>Напишите услышанное слово</Caption>
      </div>

      {usedHint ? <p className="text-lg text-ink-soft italic">{exercise.hint}</p> : null}

      {supported ? (
        <button
          type="button"
          onClick={() => speak(exercise.audio_text)}
          className="flex h-24 w-28 flex-col items-center justify-center gap-1 rounded bg-correct text-white transition-opacity hover:opacity-90"
        >
          <SpeakerIcon className="size-7" />
          <span className="text-sm leading-tight">
            Прослушать
            <br />
            ещё раз
          </span>
        </button>
      ) : (
        <p className="text-muted">
          Браузер не поддерживает озвучку — слово: <b>{exercise.audio_text}</b>
        </p>
      )}

      <input
        ref={inputRef}
        value={value}
        disabled={locked}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="Напишите слово"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        className="w-full max-w-xl rounded bg-panel px-6 py-5 text-center text-3xl text-ink outline-none placeholder:text-muted focus:ring-2 focus:ring-accent"
      />
      <p className="-mt-4 text-sm text-muted">Введите слово и нажмите Enter</p>
    </div>
  )
}
