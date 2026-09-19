import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { QuizSetup } from '../src/QuizSetup'
import { AuthScreen } from '../src/AuthScreen'
import { api, ApiError } from '../src/api'
import { App } from '../src/App'
import { InstallButton } from '../src/install'

it('requires topics, confirms replacement and sends actual mix/all settings', async () => {
  const user = userEvent.setup(), start = vi.fn()
  render(<QuizSetup options={{ categories: [{ id: 1, name: 'Первая' }, { id: 2, name: 'Вторая' }], question_count_choices: [5, 10, 15, 'all'], difficulty_choices: ['any', 'easy'] }} busy={false} hasAttempt onStart={start} onResume={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Начать квиз' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Микс тем' }))
  await user.click(screen.getByRole('checkbox', { name: 'Первая' }))
  await user.click(screen.getByRole('checkbox', { name: 'Вторая' }))
  await user.click(screen.getByRole('button', { name: /^Все$/ }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Начать новый квиз' }))
  expect(start).toHaveBeenCalledWith({ quiz_mode: 'selected_mix', category_ids: [1, 2], question_count: null, difficulty: 'any' })
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

it('offers browser-specific installation instructions when prompt API is absent', async () => {
  render(<InstallButton />)
  await userEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
  expect(screen.getByRole('status')).toHaveTextContent('Safari')
})

it('clears private account UI if the session expires during initial quiz hydration', async () => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', csrf_token: 'test', needs_identity: false, telegram_linked: false, link_pending: false, link_confirmed: false, link_target: null })
  vi.spyOn(api, 'options').mockRejectedValue(new ApiError('unauthorized', 401))
  vi.spyOn(api, 'state').mockRejectedValue(new ApiError('unauthorized', 401))
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Войти в пространство' })).toBeVisible()
  expect(screen.queryByText('Мой аккаунт')).not.toBeInTheDocument()
})
