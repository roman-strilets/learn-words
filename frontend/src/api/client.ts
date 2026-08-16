import type {
  AnswerPayload,
  AnswerResponse,
  DailyStat,
  SelectResponse,
  SessionPayload,
  StatsOverview,
  WordInput,
  WordPage,
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
  getSession: () => request<SessionPayload>('/study/session'),

  select: (wordId: number, action: 'learn' | 'know') =>
    request<SelectResponse>('/study/select', {
      method: 'POST',
      body: JSON.stringify({ word_id: wordId, action }),
    }),

  answer: (payload: AnswerPayload) =>
    request<AnswerResponse>('/study/answer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  resetWord: (wordId: number) =>
    request<void>(`/study/reset/${wordId}`, { method: 'POST' }),

  listWords: (params: {
    search?: string
    status?: string
    limit?: number
    offset?: number
  }) => {
    const query = new URLSearchParams()
    if (params.search) query.set('search', params.search)
    if (params.status) query.set('status', params.status)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return request<WordPage>(`/words?${query.toString()}`)
  },

  createWord: (payload: WordInput) =>
    request<WordWithProgress>('/words', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteWord: (wordId: number) =>
    request<void>(`/words/${wordId}`, { method: 'DELETE' }),

  overview: () => request<StatsOverview>('/stats/overview'),

  daily: (days = 30) => request<DailyStat[]>(`/stats/daily?days=${days}`),
}
