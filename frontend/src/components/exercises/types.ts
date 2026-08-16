export interface AnswerSubmit {
  answer: string | null
  usedHint: boolean
}

export interface ExerciseCardProps<T> {
  exercise: T
  onAnswer: (submit: AnswerSubmit) => void
  /** Ответ уже отправлен — блокируем повторные нажатия */
  locked: boolean
}
