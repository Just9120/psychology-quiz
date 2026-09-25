import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AnswerReview, ErrorsView, ProgressView } from '../src/ProgressView'
import { App } from '../src/App'
import { api, ApiError } from '../src/api'
import type { ErrorsPage, ProgressOverview, SavedAnswer } from '../src/types'

const overview: ProgressOverview = { ok: true, summary: { answered: 1, correct: 0, accuracy: 0, attempts: 1, finished: 0 }, topics: [{ topic: 'Память', answered: 1, correct: 0, accuracy: 0, days: [{ day: '2026-09-20', answered: 1, correct: 0, accuracy: 0 }] }], days: [{ day: '2026-09-20', answered: 1, correct: 0, accuracy: 0 }] }
const answer: SavedAnswer = { answer_id: 1, question_id: 1, session_id: 1, answered_at: '2026-09-20 06:00:00', is_correct: false, question_text: 'Исходный вопрос?', topic: 'Память', selected_option_text: 'Ошибка', correct_option_text: 'Верный вариант', explanation: 'Исходное объяснение', snapshot_provenance: 'captured', content_sha256: 'original' }
const errors: ErrorsPage = { ok: true, items: [{ ...answer, edition_state: 'changed', trainable: true }], next_before: null, total: 1, trainable_count: 1, latest_session_id: 1, has_active_attempt: true }

it('explains small-sample evidence and does not present accuracy as mastery', () => {
  render(<ProgressView data={overview} history={{ ok: true, items: [], next_before: null }} detail={null} busy={false} onRefresh={vi.fn()} onMore={vi.fn()} onOpen={vi.fn()} onBack={vi.fn()} onMoreAnswers={vi.fn()} />)
  expect(screen.getByText(/Процент отражает результат практики/)).toBeVisible()
  expect(screen.getByText(/хотя бы в два разных дня/)).toBeVisible()
  expect(screen.getByText('0 из 1 ответов')).toBeVisible()
})

it('keeps unmapped evidence visible and filters history with the chosen curriculum scope', async () => {
  const scope = vi.fn()
  const part = { scope: 'topic:t_111111111111', title: 'Внимание', answered: 1, correct: 0, accuracy: 0, days: overview.days }
  const unmapped = { ...part, scope: 'unmapped', title: 'Без подтверждённой темы' }
  const data = { ...overview, curriculum: { disciplines: [{ ...part, scope: 'discipline:general', title: 'Общая психология', topics: [part], unmapped_answers: 0 }], unmapped } }
  render(<ProgressView data={data} history={{ ok: true, items: [], next_before: null }} detail={null} busy={false} scope="unmapped" onScope={scope} onRefresh={vi.fn()} onMore={vi.fn()} onOpen={vi.fn()} onBack={vi.fn()} onMoreAnswers={vi.fn()} />)
  expect(screen.getByText(/не приписываются вложенной теме нового банка/)).toBeVisible()
  expect(screen.getByText(/результат карточки относится ко всей попытке/)).toBeVisible()
  await userEvent.selectOptions(screen.getByRole('combobox'), 'topic:t_111111111111')
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
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', csrf_token: 'test', needs_identity: false, telegram_linked: true, link_pending: false, link_confirmed: false, link_target: null })
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
