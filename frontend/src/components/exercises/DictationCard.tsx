import { useEffect, useRef, useState } from 'react'

import type { DictationExercise } from '../../api/types'
import { useHotkeys } from '../../hooks/useHotkeys'
import { useSpeech } from '../../speech/SpeechProvider'
import { SpeakerIcon } from '../icons'
import { Button, Caption, HintButton } from '../ui'
import { VoicePicker } from '../VoicePicker'
import type { ExerciseCardProps } from './types'

export function DictationCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<DictationExercise>) {
  const { speak, voices, selectVoice, supported } = useSpeech()
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

  useHotkeys(
    Object.fromEntries(
      Array.from({ length: 9 }, (_, index) => [
        String(index + 1),
        (event: KeyboardEvent) => {
          const voice = voices[index]
          if (!voice) return
          // Поле ввода автофокусируется, но слов с цифрами в словаре нет,
          // поэтому цифры всегда переключают голос; preventDefault не даёт
          // символу попасть в ответ.
          event.preventDefault()
          selectVoice(voice.uri)
          speak(exercise.audio_text)
        },
      ]),
    ),
    !locked,
  )

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-8">
      <div className="flex items-center gap-3">
        <HintButton active={usedHint} onClick={() => setUsedHint(true)} />
        <Caption>Напишите услышанное слово</Caption>
      </div>

      {usedHint ? <p className="text-lg text-ink-soft italic">{exercise.hint}</p> : null}

      {supported ? (
        <div className="flex flex-wrap items-center justify-center gap-8">
          <button
            type="button"
            onClick={() => speak(exercise.audio_text)}
            className="flex h-24 w-28 flex-col items-center justify-center gap-1 rounded bg-correct text-white transition-opacity hover:opacity-90"
          >
            <SpeakerIcon className="size-7" />
            <span className="text-sm leading-tight">
              Нажмите
              <br />
              от 1 до {Math.max(voices.length, 1)}
            </span>
          </button>
          <VoicePicker onPick={() => speak(exercise.audio_text)} />
        </div>
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
      <p className="-mt-4 text-sm text-muted">Используйте клавиатуру</p>

      <Button onClick={submit} disabled={locked} hotkeyLabel="Кнопка Enter">
        Продолжить
      </Button>
    </div>
  )
}
