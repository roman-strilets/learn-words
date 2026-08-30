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
  /**
   * `select` — знакомство с новым словом (кнопки «Уже знаю» / «Изучить»).
   * `repeat` — слово откатилось на нулевой шаг после ошибки, показываем заново.
   */
  variant: 'select' | 'repeat'
  index?: number
  total?: number
  onLearn: () => void
  onKnow?: () => void
  locked: boolean
}

export function IntroCard({
  content,
  variant,
  index,
  total,
  onLearn,
  onKnow,
  locked,
}: Props) {
  const { speak, autoplay, supported } = useSpeech()

  useSpeakOnce(content.word, autoplay)

  useHotkeys(
    {
      Enter: (event) => {
        event.preventDefault()
        onLearn()
      },
      Escape: (event) => {
        if (!onKnow) return
        event.preventDefault()
        onKnow()
      },
    },
    !locked,
  )

  const isSelect = variant === 'select'

  return (
    <div className="flex flex-col items-center gap-8">
      <header className="flex flex-col items-center gap-3">
        <h1 className="text-center text-5xl font-bold text-ink">
          {isSelect ? 'Выберите слова для изучения' : 'Запомните слово'}
        </h1>
        {isSelect && total ? (
          <Caption>
            Слов {(index ?? 0) + 1} из {total}
          </Caption>
        ) : (
          <Caption>Вернёмся к нему ещё раз в этой сессии</Caption>
        )}
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
        {isSelect && onKnow ? (
          <Button
            variant="secondary"
            onClick={onKnow}
            disabled={locked}
            hotkeyLabel="Кнопка Escape"
          >
            Уже знаю
          </Button>
        ) : null}
        <Button onClick={onLearn} disabled={locked} hotkeyLabel="Кнопка Enter">
          {isSelect ? 'Изучить' : 'Продолжить'}
          <ChevronIcon className="size-5" />
        </Button>
      </div>
    </div>
  )
}
