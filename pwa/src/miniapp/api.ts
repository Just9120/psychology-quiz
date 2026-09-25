import type { AchievementsOverview, Answer, AnswerResult, GlossaryState, GlossaryTopic, GoalKind, GoalsOverview, MasteryOverview, QuizState, ReadingStatus, ReviewQueue, Setup, SetupOptions } from '../types'

// Static deployment-owned API target; launch parameters cannot redirect initData.
const origin = 'https://quiz-api.librechat.online'
const routes = new Set([
  'state', 'setup-options', 'setup', 'answer',
  'glossary/topics', 'glossary/start', 'glossary/answer', 'glossary/next',
  'literature/topics', 'literature/items', 'literature/progress',
  'learning/review', 'learning/mastery', 'learning/goals', 'learning/achievements',
  'learning/goal-set', 'learning/review-start', 'learning/review-glossary-start',
])

declare global {
  interface Window { Telegram?: { WebApp?: { initData?: string; ready?: () => void; expand?: () => void } } }
}

export class MiniAppError extends Error {
  constructor(public code: string, public status = 0) { super(code) }
}

export async function miniRequest<T>(route: string, payload?: object): Promise<T> {
  if (!routes.has(route.split('?')[0]) || (route.includes('?') && !route.startsWith('literature/items?topic_id='))) throw new MiniAppError('invalid_destination')
  const initData = window.Telegram?.WebApp?.initData
  if (!initData) throw new MiniAppError('telegram_required', 401)
  const url = new URL(`/miniapp/${route}`, origin)
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 9000)
  try {
    const response = await fetch(url, {
      method: payload === undefined ? 'GET' : 'POST',
      mode: 'cors', credentials: 'omit', redirect: 'error', cache: 'no-store',
      headers: payload === undefined ? { Authorization: `tma ${initData}` } : { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: payload === undefined ? undefined : JSON.stringify({ init_data: initData, payload }),
      signal: controller.signal,
    })
    const body = await response.json().catch(() => null)
    if (!response.ok || body?.ok !== true) throw new MiniAppError(typeof body?.error === 'string' ? body.error : 'unavailable', response.status)
    return body as T
  } catch (failure) {
    if (failure instanceof MiniAppError) throw failure
    throw new MiniAppError('network')
  } finally { window.clearTimeout(timer) }
}

export const miniApi = {
  state: () => miniRequest<QuizState>('state'),
  options: () => miniRequest<{ ok: true; setup_options: SetupOptions }>('setup-options'),
  setup: (setup: Setup) => miniRequest<QuizState>('setup', setup),
  answer: (answer: Answer) => miniRequest<AnswerResult>('answer', answer),
  glossaryOptions: async () => {
    const result = await miniRequest<{ ok: true; glossary: { topics: GlossaryTopic[] } }>('glossary/topics')
    return { ok: true as const, topics: result.glossary.topics }
  },
  glossaryState: async () => {
    const result = await miniRequest<{ ok: true; glossary_state: GlossaryState }>('answer', { mode: 'glossary', action: 'state' })
    return { ok: true as const, glossary_state: result.glossary_state }
  },
  glossaryStart: (topic_id: string, question_count: number | 'all', expected_session_id: string | null, replace_active: boolean) =>
    miniRequest<{ ok: true; glossary_state: GlossaryState }>('glossary/start', { topic_id, question_count, expected_session_id, replace_active }),
  glossaryAnswer: (session_id: string, step_id: number, selected_option_index: number) =>
    miniRequest<{ ok: true; glossary_state: GlossaryState }>('glossary/answer', { session_id, step_id, selected_option_index }),
  glossaryNext: (session_id: string, step_id: number) =>
    miniRequest<{ ok: true; glossary_state: GlossaryState }>('glossary/next', { session_id, step_id }),
  literatureTopics: () => miniRequest<{ ok: true; literature_topics: MiniLiteratureTopic[] }>('literature/topics'),
  literatureItems: (topic_id?: string) => miniRequest<{ ok: true; literature_items: MiniLiteratureItem[] }>(`literature/items${topic_id ? `?topic_id=${encodeURIComponent(topic_id)}` : ''}`),
  literatureProgress: (literature_id: string, reading_status: ReadingStatus, progress_percent: number | null) =>
    miniRequest<{ ok: true; literature_progress: unknown }>('literature/progress', { literature_id, reading_status, progress_percent }),
  review: () => miniRequest<ReviewQueue>('learning/review'),
  mastery: () => miniRequest<MasteryOverview>('learning/mastery'),
  goals: () => miniRequest<GoalsOverview>('learning/goals'),
  achievements: () => miniRequest<AchievementsOverview>('learning/achievements'),
  setGoal: (goal_kind: GoalKind, weekly_target: number) => miniRequest<GoalsOverview>('learning/goal-set', { goal_kind, weekly_target }),
  startReviewQuiz: (expected_session_id: number | null, replace_active: boolean) =>
    miniRequest<QuizState>('learning/review-start', { expected_session_id, replace_active, question_count: 5 }),
  startReviewGlossary: (topic_id: string, expected_session_id: string | null, replace_active: boolean) =>
    miniRequest<{ ok: true; glossary_state: GlossaryState }>('learning/review-glossary-start', { topic_id, expected_session_id, replace_active, question_count: 5 }),
}

export type MiniLiteratureTopic = { topic_id: string; title: string; module?: string }
export type MiniLiteratureItem = { id: string; topic_id: string; title?: string; authors?: string[]; year?: number | null; why_read?: string; source?: { title?: string; citation?: string }; user_state?: { reading_status: ReadingStatus; progress_percent: number | null } | null }
