import { chooseMenu } from './choose-menu'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AnswerReview, ErrorsView, ProgressView } from '../src/ProgressView'
import { MiniProgress } from '../src/miniapp/MiniProgress'
import { App } from '../src/App'
import { api, ApiError } from '../src/api'
import type { ErrorsPage, HistoryAttempt, ProgressOverview, SavedAnswer } from '../src/types'

const overview: ProgressOverview = { ok: true, summary: { answered: 1, correct: 0, accuracy: 0, attempts: 1, finished: 0, knowledge_gaps: 0 }, topics: [{ topic: 'Память', answered: 1, correct: 0, accuracy: 0, days: [{ day: '2026-09-20', answered: 1, correct: 0, accuracy: 0 }] }], days: [{ day: '2026-09-20', answered: 1, correct: 0, accuracy: 0 }] }
const answer: SavedAnswer = { answer_id: 1, question_id: 1, session_id: 1, answered_at: '2026-09-20 06:00:00', is_correct: false, question_text: 'Исходный вопрос?', topic: 'Память', selected_option_text: 'Ошибка', correct_option_text: 'Верный вариант', explanation: 'Исходное объяснение', snapshot_provenance: 'captured', content_sha256: 'original' }
const errors: ErrorsPage = { ok: true, items: [{ ...answer, edition_state: 'changed', trainable: true }], next_before: null, total: 1, trainable_count: 1, latest_session_id: 1, has_active_attempt: true }

it('opens a deep history row at the heading and returns focus and scroll to that row', async () => {
  const attempt: HistoryAttempt = { session_id: 42, status: 'finished', started_at: answer.answered_at,
    finished_at: answer.answered_at, total_questions: 1, answered: 1, correct: 0, accuracy: 0 }
  const props = { data: overview, history: { ok: true as const, items: [attempt], next_before: null },
    busy: false, onRefresh: vi.fn(), onMore: vi.fn(), onOpen: vi.fn(), onBack: vi.fn(), onMoreAnswers: vi.fn() }
  const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  const position = vi.spyOn(window, 'scrollY', 'get').mockReturnValue(1800)
  const view = render(<ProgressView {...props} detail={null} />)
  const row = document.getElementById('attempt-42')!
  await userEvent.setup().click(row)
  expect(props.onOpen).toHaveBeenCalledWith(42)
  const detail = { ok: true as const, attempt, items: [answer], next_after: 1 }
  view.rerender(<ProgressView {...props} detail={detail} />)
  expect(screen.getByRole('heading', { name: 'Разбор попытки' })).toHaveFocus()
  expect(scroll).toHaveBeenLastCalledWith({ top: 0 })
  scroll.mockClear()
  view.rerender(<ProgressView {...props} detail={{ ...detail, items: [answer, { ...answer, answer_id: 2 }] }} />)
  expect(scroll).not.toHaveBeenCalled()
  view.rerender(<ProgressView {...props} detail={null} />)
  expect(document.getElementById('attempt-42')).toHaveFocus()
  expect(scroll).toHaveBeenLastCalledWith({ top: 1800 })
  position.mockRestore()
  scroll.mockRestore()
})

it('explains small-sample evidence and does not present accuracy as mastery', () => {
  render(<ProgressView data={overview} history={{ ok: true, items: [], next_before: null }} detail={null} busy={false} onRefresh={vi.fn()} onMore={vi.fn()} onOpen={vi.fn()} onBack={vi.fn()} onMoreAnswers={vi.fn()} />)
  expect(screen.getByText(/Процент отражает результат практики/)).toBeVisible()
  expect(screen.getByText(/хотя бы в два разных дня/)).toBeVisible()
  expect(screen.getByText('0 из 1 ответов')).toBeVisible()
})

it('shows durable knowledge gaps separately from practice accuracy in both clients', () => {
  const data: ProgressOverview = { ...overview,
    summary: { ...overview.summary, answered: 2, correct: 1, accuracy: 50, knowledge_gaps: 1 },
    glossary: { answered: 1, correct: 0, accuracy: 0, knowledge_gaps: 0 },
  }
  const pwa = render(<ProgressView data={data} history={{ ok: true, items: [], next_before: null }}
    detail={null} busy={false} onRefresh={vi.fn()} onMore={vi.fn()} onOpen={vi.fn()}
    onBack={vi.fn()} onMoreAnswers={vi.fn()} />)
  expect(screen.getByText('1 из 2 ответов')).toBeVisible()
  expect(screen.getByText('«Не знаю» в квизах и глоссарии: 1')).toBeVisible()
  pwa.unmount()
  render(<MiniProgress data={data} busy={false} onRefresh={vi.fn()} />)
  expect(screen.getByText(/Ответов: 2 · Верных: 1/)).toBeVisible()
  expect(screen.getByText('«Не знаю» в квизах и глоссарии: 1')).toBeVisible()
})

it('shows the distinct-question threshold and only then personal recommendations in both clients', () => {
  const props = { history: { ok: true as const, items: [], next_before: null }, detail: null,
    busy: false, onRefresh: vi.fn(), onMore: vi.fn(), onOpen: vi.fn(), onBack: vi.fn(), onMoreAnswers: vi.fn() }
  const pending: ProgressOverview = { ...overview,
    recommendations: { eligible: false, distinct_questions: 49, items: [] } }
  const ready: ProgressOverview = { ...overview,
    recommendations: { eligible: true, distinct_questions: 50,
      items: [{ topic: 'Память', answered: 3, accuracy: 33.3, reason: 'Есть неверные ответы' }] } }
  const pwa = render(<ProgressView data={pending} {...props} />)
  expect(screen.getByText(/Сейчас: 49/)).toBeVisible()
  expect(screen.queryByText(/Есть неверные ответы/)).not.toBeInTheDocument()
  pwa.rerender(<ProgressView data={ready} {...props} />)
  expect(screen.getByText(/Есть неверные ответы/)).toBeVisible()
  pwa.unmount()

  const mini = render(<MiniProgress data={pending} busy={false} onRefresh={vi.fn()} />)
  expect(screen.getByText(/Сейчас: 49/)).toBeVisible()
  mini.rerender(<MiniProgress data={ready} busy={false} onRefresh={vi.fn()} />)
  expect(screen.getByText(/Есть неверные ответы/)).toBeVisible()
})

it('keeps unmapped evidence visible and filters history with the chosen curriculum scope', async () => {
  const scope = vi.fn()
  const part = { scope: 'topic:t_111111111111', title: 'Внимание', answered: 1, correct: 0, accuracy: 0, days: overview.days }
  const unmapped = { ...part, scope: 'unmapped', title: 'Без подтверждённой темы' }
  const data = { ...overview, curriculum: { disciplines: [{ ...part, scope: 'discipline:general', title: 'Общая психология', topics: [part], unmapped_answers: 0 }], unmapped } }
  render(<ProgressView data={data} history={{ ok: true, items: [], next_before: null }} detail={null} busy={false} scope="unmapped" onScope={scope} onRefresh={vi.fn()} onMore={vi.fn()} onOpen={vi.fn()} onBack={vi.fn()} onMoreAnswers={vi.fn()} />)
  expect(screen.getByText(/не приписываются вложенной теме нового банка/)).toBeVisible()
  expect(screen.getByText(/результат карточки относится ко всей попытке/)).toBeVisible()
  await chooseMenu(userEvent.setup(), screen.getByRole('combobox'), 'topic:t_111111111111')
  expect(scope).toHaveBeenCalledWith('topic:t_111111111111')
  await userEvent.click(screen.getByRole('button', { name: 'Все попытки' }))
  expect(scope).toHaveBeenCalledWith(null)
})

it('requires explicit active-attempt replacement and clears confirmation when the attempt changes', async () => {
  const train = vi.fn(), user = userEvent.setup()
  const props = { data: errors, busy: false, onRefresh: vi.fn(), onMore: vi.fn(), onTrain: train, onResume: vi.fn() }
  const view = render(<ErrorsView {...props} />)
  await user.click(screen.getByRole('button', { name: 'Начать тренировку' }))
  expect(train).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Отмена' }))
  expect(train).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Начать тренировку' }))
  view.rerender(<ErrorsView {...props} data={{ ...errors, latest_session_id: 2 }} />)
  expect(screen.queryByRole('button', { name: 'Заменить квиз и начать' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Начать тренировку' }))
  await user.click(screen.getByRole('button', { name: 'Заменить квиз и начать' }))
  expect(train).toHaveBeenCalledWith(true, 5)
})

it('labels reconstructed legacy content without changing the recorded outcome', () => {
  render(<AnswerReview item={{ ...answer, snapshot_provenance: 'legacy_backfill_current' }} />)
  expect(screen.getByText(/исходный текст мог отличаться/)).toBeVisible()
  expect(screen.getByText('Ответ был неверным')).toBeVisible()
})

it('clears personal progress when authentication expires on a later page', async () => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', display_name: null, csrf_token: 'test', needs_identity: false, telegram_linked: true, link_pending: false, link_confirmed: false, link_target: null })
  vi.spyOn(api, 'options').mockResolvedValue({ ok: true, setup_options: { categories: [], question_count_choices: [5], difficulty_choices: ['any'] } })
  vi.spyOn(api, 'state').mockResolvedValue({ ok: true, runner_state: { state: 'setup', status: 'ok', session: null } })
  vi.spyOn(api, 'progress').mockResolvedValue(overview)
  vi.spyOn(api, 'history').mockResolvedValue({ ok: true, items: [], next_before: 1 })
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Мой прогресс' }))
  expect(await screen.findByRole('heading', { name: 'Мой прогресс' })).toBeVisible()
  vi.spyOn(api, 'history').mockRejectedValue(new ApiError('unauthorized', 401))
  await userEvent.click(screen.getByRole('button', { name: 'Ещё попытки' }))
  expect(await screen.findByRole('button', { name: 'Войти в пространство' })).toBeVisible()
  expect(screen.queryByText('0 из 1 ответов')).not.toBeInTheDocument()
})

it('renders the saved case situation, conditions and rationale in history and errors', async () => {
  const item = { ...answer, case: { situation: 'Исходная ситуация клиента', approach: 'Уточнение запроса', conditions: ['Исходное условие'], ambiguity: 'Учитываем контекст', option_rationales: ['Первый вариант: уточнение', 'Второй вариант: преждевременный совет'] } }
  const view = render(<AnswerReview item={item} />)
  expect(screen.getByText('Исходная ситуация клиента')).toBeVisible()
  expect(screen.getByText('Исходное условие')).toBeVisible()
  expect(screen.getByText('Второй вариант: преждевременный совет')).toBeVisible()
  view.rerender(<AnswerReview item={{ ...item, selected_option_index: 1, options: [
    { option_index: 0, option_text: 'Сохранённый первый вариант', is_correct: true },
    { option_index: 1, option_text: 'Сохранённый второй вариант', is_correct: false },
  ] }} />)
  expect(screen.getByText('Сохранённый первый вариант')).toBeVisible()
  expect(screen.getByText('Сохранённый второй вариант')).toBeVisible()
  expect(screen.getByText('· Ваш ответ')).toBeVisible()
  expect(screen.getByText('· Правильный ответ')).toBeVisible()
  view.unmount()
  render(<ErrorsView data={{ ...errors, items: [{ ...errors.items[0], case: item.case }] }} busy={false} onRefresh={vi.fn()} onMore={vi.fn()} onTrain={vi.fn()} onResume={vi.fn()} />)
  await userEvent.setup().click(screen.getByText('Разобрать ответ'))
  expect(screen.getByText('Исходная ситуация клиента')).toBeVisible()
  expect(screen.getByText('Учитываем контекст')).toBeVisible()
})
