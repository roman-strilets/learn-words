export interface AnswerSubmit {
  answer: string | null
  usedHint: boolean
  /** Номер попытки: вторая и дальше снижают оценку в SRS */
  attempt?: number
}

export interface ExerciseCardProps<T> {
  exercise: T
  onAnswer: (submit: AnswerSubmit) => void
  /** Ответ уже отправлен — блокируем повторные нажатия */
  locked: boolean
}
