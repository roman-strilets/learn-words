export type ExerciseType =
  | 'intro'
  | 'choice_ru_en'
  | 'choice_en_ru'
  | 'letters'
  | 'dictation'

export type WordStatus = 'learning' | 'review' | 'known' | 'suspended'

/** Статус в словаре: `new` — не статус, а его отсутствие (нет прогресса). */
export type WordStatusValue = WordStatus | 'new'

/** Что делаем на занятии: знакомимся с новыми словами или повторяем изученные. */
export type StudyMode = 'learn' | 'review'

export interface Word {
  id: number
  word: string
  translation: string
  example: string | null
  example_translation: string | null
  created_at: string
}

export interface Progress {
  status: WordStatus
  step: number
  repetitions: number
  ease: number
  interval_days: number
  due_at: string
  lapses: number
}

export interface WordWithProgress extends Word {
  progress: Progress | null
}

export interface WordPage {
  items: WordWithProgress[]
  total: number
  limit: number
  offset: number
}

export interface IntroExercise {
  type: 'intro'
  word_id: number
  word: string
  translation: string
  example: string | null
  example_translation: string | null
}

export interface ChoiceExercise {
  type: 'choice_ru_en' | 'choice_en_ru'
  word_id: number
  prompt: string
  options: string[]
  hint: string | null
}

export interface LettersExercise {
  type: 'letters'
  word_id: number
  prompt: string
  /** `_` — ячейка под букву, любой другой символ — фиксированный разделитель */
  mask: string
  /** Само слово: карточка не даёт поставить букву не на своё место */
  solution: string
  letters: string[]
  show_letters: boolean
  hint: string | null
}

export interface DictationExercise {
  type: 'dictation'
  word_id: number
  audio_text: string
  hint: string
}

export type Exercise =
  | IntroExercise
  | ChoiceExercise
  | LettersExercise
  | DictationExercise

export interface SessionCounts {
  new: number
  learning: number
  review_due: number
  in_study: number
}

/** Раунд занятия-повторения: один тип упражнения на все слова занятия. */
export interface ReviewRound {
  exercise: ExerciseType
  exercises: Exercise[]
}

export interface SessionPayload {
  mode: StudyMode
  /** Ключ занятия; заполнен в режиме `review`, когда есть что повторять */
  session_id: string | null
  /** Заполнено в режиме `learn` */
  new_words: Word[]
  /** Заполнено в режиме `review`: четыре раунда в фиксированном порядке */
  rounds: ReviewRound[]
  counts: SessionCounts
}

export interface SelectResponse {
  progress: Progress
  next_exercise: Exercise | null
  /** Замена слову, помеченному «уже знаю», чтобы занятие не стало короче */
  replacement: Word | null
}

export interface AnswerPayload {
  word_id: number
  exercise: ExerciseType
  answer: string | null
  used_hint?: boolean
  /** Номер показа слова в текущем раунде: вторая и дальше снижают оценку */
  attempt?: number
  duration_ms?: number
  mode?: StudyMode
  /** Обязателен при `mode: 'review'` — иначе сервер ответит 422 */
  session_id?: string
}

export interface AnswerResponse {
  correct: boolean
  correct_answer: string
  /** Карточка слова целиком — плашка результата показывает её ещё раз */
  word: string
  translation: string
  example: string | null
  example_translation: string | null
  quality: number
  repeat_in_session: boolean
  next_exercise: Exercise | null
  progress: Progress
}

/** Итог одного слова за занятие-повторение, посчитанный сервером по журналу. */
export interface ReviewFinishResult {
  word_id: number
  mistakes: number
  quality: number
  progress: Progress
}

export interface StatsOverview {
  total_words: number
  new: number
  learning: number
  review: number
  known: number
  due_now: number
  due_today: number
  answers_today: number
  new_today: number
  streak_days: number
}

export interface DailyStat {
  date: string
  answers: number
  correct: number
  accuracy: number
  new_words: number
}

export interface WordInput {
  word: string
  translation: string
  example?: string | null
  example_translation?: string | null
}
