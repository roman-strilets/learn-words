import { useHotkeys } from '../../hooks/useHotkeys'
import { useSpeakOnce, useSpeech } from '../../speech/SpeechProvider'
import { ChevronIcon } from '../icons'
import { Button, Caption, SpeakButton } from '../ui'

export interface IntroContent {
  wordId: number
  word: string
  translation: string
  example: string | null
  example_translation: string | null
}

interface Props {
  content: IntroContent
  /** Позиция слова в знакомстве и всего слов в занятии — для счётчика */
  index: number
  total: number
  onLearn: () => void
  onKnow: () => void
  locked: boolean
}

/** Карточка знакомства: показывает слово целиком и спрашивает, брать ли его. */
export function IntroCard({ content, index, total, onLearn, onKnow, locked }: Props) {
  const { speak, autoplay, supported } = useSpeech()

  useSpeakOnce(content.word, autoplay)

  useHotkeys(
    {
      Enter: (event) => {
        event.preventDefault()
        onLearn()
      },
      Escape: (event) => {
        event.preventDefault()
        onKnow()
      },
    },
    !locked,
  )

  return (
    <div className="flex flex-col items-center gap-8">
      <header className="flex flex-col items-center gap-3">
        <h1 className="text-center text-5xl font-bold text-ink">
          Выберите слова для изучения
        </h1>
        <Caption>
          Слов {index + 1} из {total}
        </Caption>
      </header>

      <article className="w-full max-w-xl rounded-lg border border-hairline px-8 py-7">
        <div className="flex items-start justify-end">
          <SpeakButton onClick={() => speak(content.word)} disabled={!supported} />
        </div>

        <div className="flex flex-col items-center gap-4 py-6">
          <p className="text-center text-5xl font-bold text-ink">{content.word}</p>
          <p className="underline-dashed text-center text-2xl text-muted">
            {content.translation}
          </p>
        </div>

        {/* Пример показываем сразу: знакомство со словом идёт вместе с контекстом */}
        {content.example ? (
          <div className="border-t border-hairline pt-4 text-center">
            <p className="text-ink-soft italic">{content.example}</p>
            {content.example_translation ? (
              <p className="mt-1 text-sm text-muted">{content.example_translation}</p>
            ) : null}
          </div>
        ) : null}
      </article>

      <div className="flex items-start gap-4">
        <Button
          variant="secondary"
          onClick={onKnow}
          disabled={locked}
          hotkeyLabel="Кнопка Escape"
        >
          Уже знаю
        </Button>
        <Button onClick={onLearn} disabled={locked} hotkeyLabel="Кнопка Enter">
          Изучить
          <ChevronIcon className="size-5" />
        </Button>
      </div>
    </div>
  )
}
