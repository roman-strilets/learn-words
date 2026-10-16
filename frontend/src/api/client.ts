import type {
  AnswerPayload,
  AppSettings,
  AnswerResponse,
  ClassifierCheck,
  ClassifierInput,
  ClassifierSettings,
  ClassifyBatch,
  ClassifyRequest,
  DailyStat,
  Deck,
  ExerciseRound,
  GroupAnswerPayload,
  GroupAnswerResponse,
  GroupFinishResult,
  GroupSessionPayload,
  GroupSummary,
  ImportReport,
  Label,
  LabelUpdate,
  SelectResponse,
  SessionFinishResult,
  SessionPayload,
  StatsOverview,
  StudyMode,
  WordInput,
  WordPage,
  WordStatusValue,
  WordWithProgress,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    // FastAPI кладёт человекочитаемое сообщение в detail
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* тело может быть пустым */
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Префиксы маршрутов колоды: у фраз свои, чтобы забытый параметр не увёл в слова. */
const PREFIX: Record<Deck, { items: string; labels: string; study: string; stats: string }> = {
  words: { items: '/words', labels: '/labels', study: '/study', stats: '/stats' },
  phrases: {
    items: '/phrases',
    labels: '/phrase-labels',
    study: '/phrase-study',
    stats: '/phrase-stats',
  },
}

/** Словарь, метки, занятие и статистика колоды — одни и те же методы с её префиксами. */
export function deckApi(deck: Deck) {
  const { items, labels, study, stats } = PREFIX[deck]
  return {
    getSession: (mode: StudyMode) =>
      request<SessionPayload>(`${study}/session?mode=${mode}`),

    // План раундов изучения: зовётся один раз, когда знакомство пройдено и
    // состав занятия окончателен — «Уже знаю» до этого момента меняет слова
    buildRounds: (wordIds: number[]) =>
      request<ExerciseRound[]>(`${study}/rounds`, {
        method: 'POST',
        body: JSON.stringify({ word_ids: wordIds }),
      }),

    select: (wordId: number, action: 'learn' | 'know', excludeIds: number[] = []) =>
      request<SelectResponse>(`${study}/select`, {
        method: 'POST',
        body: JSON.stringify({ word_id: wordId, action, exclude_ids: excludeIds }),
      }),

    answer: (payload: AnswerPayload) =>
      request<AnswerResponse>(`${study}/answer`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    // Конец занятия: сервер сам разбирает журнал занятия и один раз
    // пересчитывает расписание каждого слова, прошедшего все раунды.
    // Режим решает, как выводить итог, и из данных он не выводится
    finishSession: (sessionId: string, mode: StudyMode) =>
      request<SessionFinishResult[]>(`${study}/finish`, {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, mode }),
      }),

    listWords: (params: {
      search?: string
      status?: string
      priority?: boolean
      /** id метки или `none` — записи без меток */
      label?: number | 'none'
      /** Только записи с `id ≥ fromId` — курсор разметки (только слова) */
      fromId?: number | null
      limit?: number
      offset?: number
    }) => {
      const query = new URLSearchParams()
      if (params.search) query.set('search', params.search)
      if (params.status) query.set('status', params.status)
      if (params.priority) query.set('priority', 'true')
      if (params.label !== undefined) query.set('label', String(params.label))
      if (params.fromId) query.set('from_id', String(params.fromId))
      query.set('limit', String(params.limit ?? 50))
      query.set('offset', String(params.offset ?? 0))
      return request<WordPage>(`${items}?${query.toString()}`)
    },

    createWord: (payload: WordInput) =>
      request<WordWithProgress>(items, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    updateWord: ({ id, ...payload }: WordInput & { id: number }) =>
      request<WordWithProgress>(`${items}/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),

    // «Новое» тоже статус: сервер на нём удаляет прогресс
    setWordStatus: ({ id, status }: { id: number; status: WordStatusValue }) =>
      request<WordWithProgress>(`${items}/${id}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status }),
      }),

    // Поднять новую запись в очереди «Изучения»; записи в изучении сервер ответит 409
    setWordPriority: ({ id, priority }: { id: number; priority: boolean }) =>
      request<WordWithProgress>(`${items}/${id}/priority`, {
        method: 'PUT',
        body: JSON.stringify({ priority }),
      }),

    deleteWord: (wordId: number) =>
      request<void>(`${items}/${wordId}`, { method: 'DELETE' }),

    listLabels: () => request<Label[]>(labels),

    createLabel: (payload: { name: string; description?: string | null }) =>
      request<Label>(labels, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    // Частичная правка: переименование не стирает описание
    updateLabel: ({ id, ...payload }: LabelUpdate & { id: number }) =>
      request<Label>(`${labels}/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),

    // Метка снимается со всех записей колоды; записи и прогресс не меняются
    deleteLabel: (labelId: number) =>
      request<void>(`${labels}/${labelId}`, { method: 'DELETE' }),

    overview: () => request<StatsOverview>(`${stats}/overview`),

    daily: (days = 30) => request<DailyStat[]>(`${stats}/daily?days=${days}`),
  }
}

/**
 * Ключи запросов колоды. У слов — прежние ключи, чтобы существующие
 * инвалидации работали; у фраз — свои, чтобы правка фраз не сбрасывала слова.
 */
export function queryKeys(deck: Deck) {
  return deck === 'words'
    ? {
        list: ['words'] as const,
        labels: ['labels'] as const,
        overview: ['overview'] as const,
        daily: (days: number) => ['daily', days] as const,
      }
    : {
        list: ['phrases'] as const,
        labels: ['phrase-labels'] as const,
        overview: ['overview', 'phrases'] as const,
        daily: (days: number) => ['daily', 'phrases', days] as const,
      }
}

/**
 * Занятие по группе — слова одной метки, пять раундов без знакомства.
 * Расписание, статусы и статистику оно не трогает, поэтому маршруты свои.
 */
export const groupApi = {
  groups: () => request<GroupSummary[]>('/group-study/groups'),

  // POST, а не GET: сборка порции заводит строки круга группы на сервере
  session: (labelId: number) =>
    request<GroupSessionPayload>('/group-study/session', {
      method: 'POST',
      body: JSON.stringify({ label_id: labelId }),
    }),

  answer: (payload: GroupAnswerPayload) =>
    request<GroupAnswerResponse>('/group-study/answer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Слова, прошедшие все раунды, сервер отмечает пройденными в их круге
  finish: (sessionId: string) =>
    request<GroupFinishResult[]>('/group-study/finish', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),

  // Новый круг в новом порядке; прогресс слов не меняется
  restart: (labelId: number) =>
    request<void>(`/group-study/groups/${labelId}/restart`, { method: 'POST' }),
}

export const groupQueryKeys = {
  groups: ['group-study', 'groups'] as const,
}

export const api = {
  ...deckApi('words'),

  // Одна пачка автоматической разметки: модель думает над ней до двух минут.
  // 502/504 — классификатор недоступен или не ответил, `detail` называет причину
  classifyBatch: (payload: ClassifyRequest) =>
    request<ClassifyBatch>('/labels/classify', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Файл уходит как есть, сырыми байтами: декодирует сервер и сам объясняет
  // ошибку кодировки, а `File.text()` молча заменил бы чужие байты на «�».
  // Свой заголовок перекрывает JSON-заголовок `request()`: `init` идёт после него
  importWords: (file: File) =>
    request<ImportReport>('/words/import', {
      method: 'POST',
      body: file,
      headers: { 'Content-Type': 'text/csv' },
    }),

  getSettings: () => request<AppSettings>('/settings'),

  updateSettings: (payload: AppSettings) =>
    request<AppSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getClassifier: () => request<ClassifierSettings>('/settings/classifier'),

  saveClassifier: (payload: ClassifierInput) =>
    request<ClassifierSettings>('/settings/classifier', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // Забывает сохранённое и отдаёт значения по умолчанию
  resetClassifier: () =>
    request<ClassifierSettings>('/settings/classifier', { method: 'DELETE' }),

  // Проверяет переданные значения, не сохраняя их
  checkClassifier: (payload: ClassifierInput) =>
    request<ClassifierCheck>('/settings/classifier/check', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
