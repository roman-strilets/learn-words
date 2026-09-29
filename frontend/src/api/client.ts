import type {
  AnswerPayload,
  AppSettings,
  AnswerResponse,
  DailyStat,
  ExerciseRound,
  Label,
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

export const api = {
  getSession: (mode: StudyMode) =>
    request<SessionPayload>(`/study/session?mode=${mode}`),

  // План раундов изучения: зовётся один раз, когда знакомство пройдено и
  // состав занятия окончателен — «Уже знаю» до этого момента меняет слова
  buildRounds: (wordIds: number[]) =>
    request<ExerciseRound[]>('/study/rounds', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds }),
    }),

  select: (wordId: number, action: 'learn' | 'know', excludeIds: number[] = []) =>
    request<SelectResponse>('/study/select', {
      method: 'POST',
      body: JSON.stringify({ word_id: wordId, action, exclude_ids: excludeIds }),
    }),

  answer: (payload: AnswerPayload) =>
    request<AnswerResponse>('/study/answer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Конец занятия: сервер сам разбирает журнал занятия и один раз
  // пересчитывает расписание каждого слова, прошедшего все четыре раунда.
  // Режим решает, как выводить итог, и из данных он не выводится
  finishSession: (sessionId: string, mode: StudyMode) =>
    request<SessionFinishResult[]>('/study/finish', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, mode }),
    }),

  listWords: (params: {
    search?: string
    status?: string
    priority?: boolean
    /** id метки или `none` — слова без меток */
    label?: number | 'none'
    limit?: number
    offset?: number
  }) => {
    const query = new URLSearchParams()
    if (params.search) query.set('search', params.search)
    if (params.status) query.set('status', params.status)
    if (params.priority) query.set('priority', 'true')
    if (params.label !== undefined) query.set('label', String(params.label))
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return request<WordPage>(`/words?${query.toString()}`)
  },

  createWord: (payload: WordInput) =>
    request<WordWithProgress>('/words', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateWord: ({ id, ...payload }: WordInput & { id: number }) =>
    request<WordWithProgress>(`/words/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  // «Новое» тоже статус: сервер на нём удаляет прогресс
  setWordStatus: ({ id, status }: { id: number; status: WordStatusValue }) =>
    request<WordWithProgress>(`/words/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),

  // Поднять новое слово в очереди «Изучения»; слову в изучении сервер ответит 409
  setWordPriority: ({ id, priority }: { id: number; priority: boolean }) =>
    request<WordWithProgress>(`/words/${id}/priority`, {
      method: 'PUT',
      body: JSON.stringify({ priority }),
    }),

  deleteWord: (wordId: number) =>
    request<void>(`/words/${wordId}`, { method: 'DELETE' }),

  listLabels: () => request<Label[]>('/labels'),

  createLabel: (name: string) =>
    request<Label>('/labels', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  renameLabel: ({ id, name }: { id: number; name: string }) =>
    request<Label>(`/labels/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  // Метка снимается со всех слов; слова и прогресс не меняются
  deleteLabel: (labelId: number) =>
    request<void>(`/labels/${labelId}`, { method: 'DELETE' }),

  overview: () => request<StatsOverview>('/stats/overview'),

  daily: (days = 30) => request<DailyStat[]>(`/stats/daily?days=${days}`),

  getSettings: () => request<AppSettings>('/settings'),

  updateSettings: (payload: AppSettings) =>
    request<AppSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
}
