import { useEffect } from 'react'

import { useHotkeys } from '../../hooks/useHotkeys'
import { useSpeech } from '../../speech/SpeechProvider'
import { Button, SpeakButton } from '../ui'

interface Props {
  correct: boolean
  /** Английское слово — его произносим и показываем крупно */
  word: string
  translation: string
  example?: string | null
  exampleTranslation?: string | null
  onContinue: () => void
}

/** Плашка результата: карточка слова целиком плюс подтверждение перехода. */
export function Feedback({
  correct,
  word,
  translation,
  example,
  exampleTranslation,
  onContinue,
}: Props) {
  const { speak, autoplay, supported } = useSpeech()

  useHotkeys({
    Enter: (event) => {
      event.preventDefault()
      onContinue()
    },
  })

  // Верный ответ проговариваем: слово запоминается вместе со звучанием
  useEffect(() => {
    if (correct && autoplay) speak(word)
  }, [correct, word, autoplay, speak])

  return (
    <div
      role="status"
      className={`flex w-full max-w-xl flex-col items-center gap-3 rounded-md px-6 py-5 text-center ${
        correct ? 'bg-correct-soft text-correct' : 'bg-wrong-soft text-wrong'
      }`}
    >
      <p className="text-xl font-semibold">{correct ? 'Верно' : 'Неверно'}</p>

      <div className="flex items-center gap-3">
        <p className="text-2xl font-bold text-ink">{word}</p>
        {supported ? (
          <SpeakButton onClick={() => speak(word)} title="Произнести ещё раз" />
        ) : null}
      </div>

      <p className="text-lg text-ink-soft">{translation}</p>

      {example ? (
        <p className="text-base text-ink-soft italic">
          {example}
          {exampleTranslation ? (
            <span className="block text-muted not-italic">{exampleTranslation}</span>
          ) : null}
        </p>
      ) : null}

      <Button onClick={onContinue} hotkeyLabel="Кнопка Enter">
        Продолжить
      </Button>
    </div>
  )
}
