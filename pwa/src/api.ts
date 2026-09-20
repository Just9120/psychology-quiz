import type { Account, Answer, AnswerResult, QuizState, Setup, SetupOptions, ProgressOverview, HistoryPage, AttemptPage, ErrorsPage, ResetPreview } from './types'
import type { GlossaryState, GlossaryTopic } from './types'

export class ApiError extends Error {
  constructor(public code: string, public status = 0) { super(code) }
}

const actions = new Set(['auth/me', 'auth/login', 'auth/register', 'auth/verify', 'auth/recover', 'auth/reset',
  'auth/logout', 'identity/new', 'link/start', 'link/complete', 'quiz/state', 'quiz/options', 'quiz/setup', 'quiz/answer',
  'progress/overview', 'progress/history', 'progress/attempt', 'progress/errors', 'progress/train', 'progress/reset-preview', 'progress/reset-confirm',
  'glossary/options', 'glossary/state', 'glossary/setup', 'glossary/answer', 'glossary/next', 'glossary/restart'])
let csrf: string | null = null

export async function request<T>(action: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  if (!actions.has(action)) throw new ApiError('invalid_destination')
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timeout = window.setTimeout(abort, 15000)
  try {
    const response = await fetch(`/web/${action}`, {
      method: payload === undefined ? 'GET' : 'POST',
      credentials: 'same-origin', mode: 'same-origin', redirect: 'error', cache: 'no-store',
      headers: payload === undefined ? {} : { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
      body: payload === undefined ? undefined : JSON.stringify(payload), signal: controller.signal,
    })
    if (response.status === 401) csrf = null
    const body = await response.json().catch(() => null)
    if (!response.ok || !body || body.ok !== true) {
      throw new ApiError(typeof body?.error === 'string' ? body.error : 'unavailable', response.status)
    }
    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(signal?.aborted ? 'aborted' : 'network')
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}

export const api = {
  async me(signal?: AbortSignal) {
    const result = await request<Account>('auth/me', undefined, signal)
    csrf = result.csrf_token
    return result
  },
  login: (email: string, password: string) => request('auth/login', { email, password }),
  register: (email: string) => request('auth/register', { email }),
  verify: (token: string, password: string) => request('auth/verify', { token, password }),
  recover: (email: string) => request('auth/recover', { email }),
  reset: (token: string, password: string) => request('auth/reset', { token, password }),
  async logout() { await request('auth/logout', {}); csrf = null },
  newIdentity: () => request('identity/new', {}),
  linkStart: () => request<{ ok: true; code: string }>('link/start', {}),
  linkComplete: () => request('link/complete', {}),
  options: () => request<{ ok: true; setup_options: SetupOptions }>('quiz/options'),
  state: () => request<QuizState>('quiz/state'),
  setup: (setup: Setup) => request<QuizState>('quiz/setup', setup),
  answer: (answer: Answer) => request<AnswerResult>('quiz/answer', answer),
  progress: () => request<ProgressOverview>('progress/overview'),
  glossaryOptions: () => request<{ ok: true; topics: GlossaryTopic[] }>('glossary/options'),
  glossaryState: () => request<{ ok: true; glossary_state: GlossaryState }>('glossary/state'),
  glossaryStart: (topic_id: string, question_count: number | 'all', expected_session_id: string | null, replace_active: boolean) => request<{ ok: true; glossary_state: GlossaryState }>('glossary/setup', { topic_id, question_count, expected_session_id, replace_active }),
  glossaryAnswer: (session_id: string, step_id: number, selected_option_index: number) => request<{ ok: true; glossary_state: GlossaryState }>('glossary/answer', { session_id, step_id, selected_option_index }),
  glossaryNext: (session_id: string, step_id: number) => request<{ ok: true; glossary_state: GlossaryState }>('glossary/next', { session_id, step_id }),
  resetPreview: (topic: string | null = null) => request<ResetPreview>('progress/reset-preview', { scope: topic === null ? 'all' : 'topic', topic }),
  resetLearning: (preview: ResetPreview) => request('progress/reset-confirm', { scope: preview.scope, topic: preview.topic, expected_revision: preview.revision, confirm: true }),
  history: (before: number | null = null) => request<HistoryPage>('progress/history', { before }),
  attempt: (session_id: number, after: number | null = null) => request<AttemptPage>('progress/attempt', { session_id, after }),
  errors: (before: number | null = null) => request<ErrorsPage>('progress/errors', { before }),
  trainErrors: (expected_session_id: number | null, replace_active: boolean, question_count: number | null) => request<QuizState>('progress/train', { expected_session_id, replace_active, question_count }),
}

const messages: Record<string, string> = {
  invalid_credentials: 'Не удалось войти. Проверьте почту и пароль.',
  unauthorized: 'Сессия завершилась. Войдите ещё раз — сохранённый прогресс останется на месте.',
  password_length: 'Используйте от 15 до 128 символов. Подойдёт длинная фраза.',
  invalid_token: 'Ссылка недействительна или истекла. Запросите новое письмо.',
  rate_limited: 'Слишком много попыток. Подождите и попробуйте позже.',
  mail_unavailable: 'Не удалось отправить письмо. Попробуйте позже.',
  invalid_link: 'Подтверждение ещё не получено или код истёк. Проверьте Telegram или создайте новый код.',
  identity_unavailable: 'Эта учётная запись уже связана. Прогресс не был изменён.',
  identity_already_chosen: 'Прогресс уже выбран. Объединение двух историй пока не поддерживается.',
  no_categories: 'Темы пока недоступны. Попробуйте обновить страницу позже.',
  no_questions: 'Для этих условий пока нет вопросов. Измените настройки.',
  no_errors: 'Доступных ошибок уже нет. Обновите список — сохранённая история осталась на месте.',
  practice_changed: 'Квиз изменился в другом окне. Восстановите актуальную попытку.',
  reset_changed: 'Прогресс изменился. Загрузите новый предварительный просмотр и подтвердите сброс заново.',
  nothing_to_reset: 'Нет попыток для сброса. Обновите предварительный просмотр.',
  reset_confirmation_required: 'Для сброса требуется явное подтверждение.',
  active_attempt: 'У вас есть незавершённый квиз. Обновите список и подтвердите замену попытки.',
  attempt_not_found: 'Эта попытка недоступна. Обновите историю.',
  invalid_setup: 'Эти параметры недоступны. Обновите список тем и выберите заново.',
  invalid_glossary_setup: 'Эти параметры глоссария недоступны. Обновите список тем.',
  glossary_unavailable: 'Для этой темы пока недостаточно доступных терминов.',
  glossary_changed: 'Глоссарий изменился в другом окне. Восстановите сохранённое состояние.',
  active_glossary: 'Подтвердите замену незавершённого теста по терминам.',
  csrf_failed: 'Не удалось подтвердить запрос. Обновите страницу и повторите действие.',
  origin_forbidden: 'Этот адрес приложения пока не настроен. Обратитесь к владельцу.',
  network: 'Нет подтверждения от сервера. Проверьте подключение и повторите запрос.',
  database_unavailable: 'Сервер занят. Попробуйте ещё раз через несколько секунд.',
  auth_busy: 'Сервер занят. Попробуйте ещё раз через несколько секунд.',
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404 && !messages[error.code]) return 'Этот раздел пока недоступен. Попробуйте позже.'
    return messages[error.code] ?? 'Не удалось выполнить действие. Попробуйте ещё раз.'
  }
  return 'Не удалось выполнить действие. Попробуйте ещё раз.'
}
