export type ExerciseType =
  | 'intro'
  | 'choice_ru_en'
  | 'choice_en_ru'
  | 'letters'
  | 'writing_ru_en'
  | 'dictation'

export type WordStatus = 'learning' | 'review' | 'known' | 'suspended'

/** Статус в словаре: `new` — не статус, а его отсутствие (нет прогресса). */
export type WordStatusValue = WordStatus | 'new'

/** Что делаем на занятии: знакомимся с новыми словами или повторяем изученные. */
export type StudyMode = 'learn' | 'review'

/**
 * Колода: слова или фразы. У фраз свои маршруты (`/phrases`, `/phrase-labels`,
 * `/phrase-study`, `/phrase-stats`), но ответы — те же схемы, что у слов:
 * `word` — текст фразы, `word_id` — id фразы, `word_count` у метки — число фраз.
 */
export type Deck = 'words' | 'phrases'

/** Метка в составе слова. */
export interface LabelRef {
  id: number
  name: string
}

/** Метка в общем списке: счётчик нужен списку и подтверждению удаления. */
export interface Label {
  id: number
  name: string
  /** Пояснение темы для автоматической разметки; `null` — модель судит по названию */
  description: string | null
  word_count: number
}

/** Частичная правка метки: меняются только переданные поля. */
export interface LabelUpdate {
  name?: string
  /** `null` или пустая строка стирают описание */
  description?: string | null
}

export interface Word {
  id: number
  word: string
  translation: string
  example: string | null
  example_translation: string | null
  created_at: string
  /** «Учить первым»: бывает только у нового слова и снимается, когда оно уходит в изучение */
  priority: boolean
  /** По названию без учёта регистра, «ё» = «е»; `[]` у слова без меток */
  labels: LabelRef[]
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

/** Строка файла, пропущенная при импорте: номер как в табличном редакторе. */
export interface ImportSkippedRow {
  line: number
  reason: string
}

/**
 * Итог импорта CSV. Счётчики считают строки файла:
 * `rows == created + merged + unchanged + skipped`. В `skipped_rows` — не все
 * пропуски, если их много; полное число — в `skipped`.
 */
export interface ImportReport {
  rows: number
  created: number
  merged: number
  unchanged: number
  skipped: number
  skipped_rows: ImportSkippedRow[]
  labels_created: string[]
  ignored_columns: string[]
}

/** Фильтры «Словаря», с которыми открыта разметка: значат то же, что у списка. */
export interface ClassifyFilters {
  search?: string
  status?: string
  priority?: boolean
  /** id метки или `none` — слова без меток */
  label?: number | 'none'
}

/**
 * Одна пачка автоматической разметки. Сервер не помнит этап: курсор `from_id`
 * берётся из ответа предыдущей пачки, `null` — с начала.
 */
export interface ClassifyRequest extends ClassifyFilters {
  label_ids: number[]
  from_id?: number | null
  limit: number
}

export interface ClassifyResult {
  word_id: number
  word: string
  translation: string
  /** `null` — ни одна метка набора не подошла */
  label: LabelRef | null
  /** Метка поставлена этим запросом; уже стоявшая — `false` */
  added: boolean
}

export interface ClassifyBatch {
  /** По слову на каждое обработанное, в порядке `id` */
  results: ClassifyResult[]
  /** Слова, удалённые, пока модель думала */
  skipped: number
  /** Курсор следующей пачки; `null` — подходящих слов дальше нет */
  next_from_id: number | null
  /** Сколько подходящих слов осталось с `id ≥ next_from_id` */
  remaining: number
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

/** Ответа и подсказки в карточке нет — их не во что подсмотреть. */
export interface WritingRuEnExercise {
  type: 'writing_ru_en'
  word_id: number
  prompt: string
}

export interface DictationExercise {
  type: 'dictation'
  word_id: number
  audio_text: string
  hint: string
}

/**
 * Карточка-знакомство сюда не входит: знакомство идёт по слову целиком,
 * до раундов, и упражнением никогда не приходит.
 */
export type Exercise =
  | ChoiceExercise
  | LettersExercise
  | WritingRuEnExercise
  | DictationExercise

export interface SessionCounts {
  new: number
  learning: number
  review_due: number
  in_study: number
}

/**
 * Раунд занятия: один тип упражнения на все слова занятия.
 * Раунды одинаково устроены в обоих режимах, поэтому имя без «повторения».
 */
export interface ExerciseRound {
  exercise: ExerciseType
  exercises: Exercise[]
}

export interface SessionPayload {
  mode: StudyMode
  /** Ключ занятия; приходит в обоих режимах, когда занятию есть чем заняться */
  session_id: string | null
  /** Заполнено в режиме `learn` */
  new_words: Word[]
  /**
   * Заполнено в режиме `review`: все раунды в фиксированном порядке.
   * План изучения приходит отдельно, из `buildRounds`: его состав известен
   * только после знакомства.
   */
  rounds: ExerciseRound[]
  counts: SessionCounts
}

export interface SelectResponse {
  progress: Progress
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
  /** Обязателен в обоих режимах — иначе сервер ответит 422 */
  session_id: string
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

/**
 * Итог одного слова за занятие, посчитанный сервером по журналу.
 * В режиме `learn` `mistakes` информационный: на расписание он не влияет.
 */
export interface SessionFinishResult {
  word_id: number
  mistakes: number
  quality: number
  progress: Progress
}

/** Метка слов в выборе группы: размер и место в текущем круге. */
export interface GroupSummary {
  label_id: number
  name: string
  /** Слова с этой меткой в любом статусе */
  word_count: number
  /** Пройдено в текущем круге, 0..word_count */
  done: number
  /** Номер текущего круга; 0 — по группе ещё не занимались */
  cycle: number
}

/** Порция занятия по группе: пять раундов без знакомства. */
export interface GroupSessionPayload {
  label_id: number
  name: string
  /** null — в группе нет слов, занятия нет */
  session_id: string | null
  rounds: ExerciseRound[]
  word_count: number
  /** Пройдено в текущем круге до этого занятия */
  done: number
  cycle: number
}

export interface GroupAnswerPayload {
  word_id: number
  label_id: number
  session_id: string
  /** Кроме `intro` — иначе сервер ответит 422 */
  exercise: ExerciseType
  answer: string | null
  used_hint?: boolean
  attempt?: number
  duration_ms?: number
}

/** Поля `AnswerResponse` без прогресса: занятие по группе его не трогает. */
export interface GroupAnswerResponse {
  correct: boolean
  correct_answer: string
  word: string
  translation: string
  example: string | null
  example_translation: string | null
  quality: number
  repeat_in_session: boolean
  next_exercise: Exercise | null
}

/** Слово, прошедшее все раунды порции и отмеченное пройденным в своём круге. */
export interface GroupFinishResult {
  word_id: number
  mistakes: number
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
  /**
   * Названия, а не id: новые метки создаются вместе со словом. В правке
   * отсутствие поля не меняет метки, `[]` снимает все.
   */
  labels?: string[]
}

/**
 * В каком порядке «Изучение» берёт новые слова. На «Повторение» не влияет:
 * там слова идут по сроку.
 */
export type NewWordsOrder = 'oldest_first' | 'newest_first'

/** Настройки приложения, которые хранятся на сервере, а не в браузере. */
export interface AppSettings {
  new_words_order: NewWordsOrder
}

/** Подключение к классификатору меток. */
export interface ClassifierInput {
  base_url: string
  api_key: string
  model: string
}

/** Действующее подключение; `is_default` — ничего не сохранено, всё по умолчанию. */
export interface ClassifierSettings extends ClassifierInput {
  is_default: boolean
}

/** Итог «Проверить подключение»: неудача — ответ с причиной, а не ошибка запроса. */
export interface ClassifierCheck {
  ok: boolean
  detail: string
}
