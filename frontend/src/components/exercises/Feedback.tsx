import { useHotkeys } from '../../hooks/useHotkeys'

interface Props {
  correct: boolean
  correctAnswer: string
  onContinue: () => void
}

/** Плашка результата: верный ответ гаснет сам, ошибка ждёт подтверждения. */
export function Feedback({ correct, correctAnswer, onContinue }: Props) {
  useHotkeys({
    Enter: (event) => {
      event.preventDefault()
      onContinue()
    },
  })

  return (
    <div
      role="status"
      className={`flex w-full max-w-xl flex-col items-center gap-2 rounded-md px-6 py-4 text-center ${
        correct ? 'bg-correct-soft text-correct' : 'bg-wrong-soft text-wrong'
      }`}
    >
      <p className="text-xl font-semibold">{correct ? 'Верно' : 'Неверно'}</p>
      <p className="text-2xl font-bold text-ink">{correctAnswer}</p>
      {!correct ? (
        <button
          type="button"
          onClick={onContinue}
          className="text-sm text-accent underline underline-offset-4"
        >
          Продолжить — кнопка Enter
        </button>
      ) : null}
    </div>
  )
}
