import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { QuizSetup } from '../src/QuizSetup'
import { AuthScreen } from '../src/AuthScreen'
import { api, ApiError } from '../src/api'
import { App } from '../src/App'
import { InstallButton } from '../src/install'
import { QuizView } from '../src/QuizView'
import { AccountView } from '../src/AccountView'

it('requires topics, confirms replacement and sends actual mix/all settings', async () => {
  const user = userEvent.setup(), start = vi.fn()
  render(<QuizSetup options={{ categories: [{ id: 1, name: 'Первая' }, { id: 2, name: 'Вторая' }], question_count_choices: [5, 10, 15, 'all'], difficulty_choices: ['any', 'easy'] }} busy={false} activeSessionId={10} onStart={start} onResume={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Начать квиз' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Микс тем' }))
  await user.click(screen.getByRole('checkbox', { name: 'Первая' }))
  await user.click(screen.getByRole('checkbox', { name: 'Вторая' }))
  await user.click(screen.getByRole('button', { name: /^Все$/ }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Начать новый квиз' }))
  expect(start).toHaveBeenCalledWith({ quiz_mode: 'selected_mix', category_ids: [1, 2], question_count: null, difficulty: 'any' }, true)
})

it('requires fresh confirmation when the active attempt changes', async () => {
  const user = userEvent.setup(), start = vi.fn(), resume = vi.fn()
  const options = { categories: [{ id: 1, name: 'Тема' }], question_count_choices: [5 as const], difficulty_choices: ['any' as const] }
  const view = (id: number) => <QuizSetup options={options} busy={false} activeSessionId={id} onStart={start} onResume={resume} />
  const { rerender } = render(view(10))
  await user.click(screen.getByRole('radio', { name: 'Тема' }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(screen.getByRole('button', { name: 'Начать новый квиз' })).toBeVisible()

  rerender(view(11))
  expect(screen.getByRole('button', { name: 'Начать квиз' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Начать новый квиз' }))
  expect(start).toHaveBeenCalledWith(expect.objectContaining({ category_ids: [1] }), true)
})

it('requires fresh replacement confirmation after changing quiz settings', async () => {
  const user = userEvent.setup(), start = vi.fn()
  render(<QuizSetup options={{ categories: [{ id: 1, name: 'Тема' }], question_count_choices: [5, 10],
    difficulty_choices: ['any', 'easy'], content_kind_choices: ['theory', 'case'] }}
    busy={false} activeSessionId={10} onStart={start} onResume={vi.fn()} />)
  await user.click(screen.getByRole('radio', { name: 'Тема' }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(screen.getByRole('button', { name: 'Начать новый квиз' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: '5' }))
  expect(screen.getByRole('button', { name: 'Начать квиз' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Начать новый квиз' }))
  expect(start).toHaveBeenCalledWith(expect.objectContaining({ question_count: 5 }), true)
})

it('registration requests proof before password entry', async () => {
  const user = userEvent.setup(), register = vi.spyOn(api, 'register').mockResolvedValue({ ok: true })
  render(<AuthScreen busy={false} run={async action => action()} proof={null} consumeProof={vi.fn()} onLogin={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Первый вход' }))
  expect(screen.queryByLabelText('Пароль')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('Электронная почта'), 'owner@example.test')
  await user.click(screen.getByRole('button', { name: 'Получить письмо' }))
  expect(register).toHaveBeenCalledWith('owner@example.test')
  expect(await screen.findByRole('status')).toHaveTextContent('Если для этой почты')
})

it('does not show the owner/student access note on the sign-in screen', () => {
  render(<AuthScreen busy={false} run={async action => action()} proof={null} consumeProof={vi.fn()} onLogin={vi.fn()} />)
  expect(screen.queryByText(/Веб-приложение доступно только владельцу/)).not.toBeInTheDocument()
})

it('styles the saved answer by correctness while keeping the explanation readable', () => {
  const state = { state: 'in_progress' as const, status: 'ok', session: { session_id: 1 } }
  const props = { state, feedbackQuestion: null, selected: null, pending: null, busy: false,
    onSelect: vi.fn(), onAnswer: vi.fn(), onNext: vi.fn(), onSetup: vi.fn(), onRefresh: vi.fn() }
  const feedback = { selected_option_index: 0, selected_option_text: 'Первый вариант', is_correct: false,
    correct_option_index: 1, correct_option_text: 'Второй вариант', explanation: 'Разбор ответа' }
  const { container, rerender } = render(<QuizView {...props} feedback={feedback} />)
  expect(container.querySelector('.question-panel-incorrect .your-answer.incorrect')).toHaveTextContent('Первый вариант')
  expect(screen.getByText('Разбор ответа')).toBeVisible()
  rerender(<QuizView {...props} feedback={{ ...feedback, is_correct: true }} />)
  expect(container.querySelector('.question-panel-correct .your-answer.correct')).toHaveTextContent('Первый вариант')
})

it('saves a private display name through the profile action', async () => {
  const account = { ok: true as const, email: 'owner@example.test', display_name: null, csrf_token: 'test',
    needs_identity: false, telegram_linked: true, link_pending: false, link_confirmed: false, link_target: null }
  const save = vi.spyOn(api, 'setDisplayName').mockResolvedValue({ ok: true, display_name: 'Владимир' })
  render(<AccountView account={account} busy={false} run={async action => action()} onAccount={vi.fn()} onLearn={vi.fn()} onReset={vi.fn()} />)
  await userEvent.type(screen.getByLabelText('Имя в приложении'), 'Владимир')
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить имя' }))
  expect(save).toHaveBeenCalledWith('Владимир')
  expect(await screen.findByText('Имя сохранено.')).toBeVisible()
})

it('offers browser-specific installation instructions when prompt API is absent', async () => {
  render(<InstallButton />)
  await userEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
  expect(screen.getByRole('status')).toHaveTextContent('Safari')
})

it('clears private account UI if the session expires during initial quiz hydration', async () => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', display_name: null, csrf_token: 'test', needs_identity: false, telegram_linked: false, link_pending: false, link_confirmed: false, link_target: null })
  vi.spyOn(api, 'options').mockRejectedValue(new ApiError('unauthorized', 401))
  vi.spyOn(api, 'state').mockRejectedValue(new ApiError('unauthorized', 401))
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Войти в пространство' })).toBeVisible()
  expect(screen.queryByText('Мой аккаунт')).not.toBeInTheDocument()
})

it('groups exact curriculum topics by module without hiding unmapped categories', () => {
  render(<QuizSetup options={{ categories: [
    { id: 1, name: 'Теория', module: 'module1', topic_id: 'theory' },
    { id: 2, name: 'Кейсы', module: 'module3', topic_id: 'cases' },
    { id: 3, name: 'Новая категория', module: null, topic_id: null },
  ], question_count_choices: [5], difficulty_choices: ['any'] }} busy={false} activeSessionId={null} onStart={vi.fn()} onResume={vi.fn()} />)
  expect(screen.getByRole('heading', { name: 'Модуль 1' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Модуль 3' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Без подтверждённого модуля' })).toBeVisible()
  expect(screen.getByRole('radio', { name: 'Новая категория' })).toBeVisible()
})

it('restores the answered question instead of labeling its feedback with the next question', async () => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', display_name: null, csrf_token: 'test', needs_identity: false, telegram_linked: false, link_pending: false, link_confirmed: false, link_target: null })
  vi.spyOn(api, 'options').mockResolvedValue({ ok: true, setup_options: { categories: [{ id: 1, name: 'Тема' }], question_count_choices: [5], difficulty_choices: ['any'] } })
  vi.spyOn(api, 'state').mockResolvedValue({ ok: true,
    runner_state: { state: 'in_progress', status: 'ok', session: { session_id: 10 },
      current_question: { session_id: 10, question_id: 21, question_text: 'Следующий вопрос?', order_index: 2, total_questions: 2, options: [] },
      progress: { current_question_number: 2, total_questions: 2, answered_count: 1 } },
    recent_answer_feedback: { question_id: 20, selected_option_index: 0, selected_option_text: 'Ответ',
      is_correct: true, correct_option_index: 0, correct_option_text: 'Ответ', explanation: 'Пояснение' },
    recent_answer_question: { session_id: 10, question_id: 20, question_text: 'Сохранённый вопрос?',
      order_index: 1, total_questions: 2, options: [] } })
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Сохранённый вопрос?' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Следующий вопрос?' })).not.toBeInTheDocument()
})
