import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { App } from '../src/App'
import { api, ApiError } from '../src/api'
import { UpdateButton } from '../src/UpdateButton'
import { activateUpdate } from '../src/pwaUpdate'
vi.mock('../src/pwaUpdate', async importOriginal => ({ ...await importOriginal<typeof import('../src/pwaUpdate')>(), useWaitingUpdate: () => worker, activateUpdate: vi.fn() }))
const worker = { postMessage: vi.fn() } as unknown as ServiceWorker
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); vi.restoreAllMocks() })
it('defers and blocks unconfirmed operations and failed state checks', async () => {
  const user = userEvent.setup(), check = vi.fn().mockResolvedValue(true)
  render(<UpdateButton busy={false} checkActive={check} />)
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Позже' }))
  expect(check).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Сначала подтвердите')
  expect(activateUpdate).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Вернуться' }))
  check.mockRejectedValue(new Error('offline'))
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Не удалось проверить')
  expect(activateUpdate).not.toHaveBeenCalled()
})
it('activates only after confirmation and no unconfirmed operation', async () => {
  const user = userEvent.setup()
  render(<UpdateButton busy={false} checkActive={vi.fn().mockResolvedValue(false)} />)
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  expect(activateUpdate).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  await waitFor(() => expect(activateUpdate).toHaveBeenCalledWith(worker))
})
it('discovery does not activate; explicit activation reloads just once', async () => {
  vi.useFakeTimers()
  const actual = await vi.importActual<typeof import('../src/pwaUpdate')>('../src/pwaUpdate')
  const sw = Object.assign(new EventTarget(), { controller: worker })
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: sw })
  const registration = Object.assign(new EventTarget(), { waiting: worker, update: vi.fn().mockResolvedValue(undefined) })
  actual.watchUpdates(registration as unknown as ServiceWorkerRegistration)
  sw.dispatchEvent(new Event('controllerchange'))
  expect(worker.postMessage).not.toHaveBeenCalled()
  const reload = vi.fn()
  actual.activateUpdate(worker, reload)
  expect(worker.postMessage).toHaveBeenCalledWith({ type: 'APPLY_UPDATE' })
  expect(reload).not.toHaveBeenCalled()
  sw.dispatchEvent(new Event('controllerchange'))
  vi.advanceTimersByTime(6000)
  expect(reload).toHaveBeenCalledTimes(1)
  delete (navigator as unknown as { serviceWorker?: unknown }).serviceWorker
})

it('actual worker activates only for explicit update messages', () => {
  const handlers: Record<string, (event: any) => void> = {}
  const skipWaiting = vi.fn().mockResolvedValue(undefined)
  runInNewContext(readFileSync('public/sw.js', 'utf8'), {
    self: { addEventListener: (name: string, handler: (event: any) => void) => { handlers[name] = handler }, skipWaiting },
    caches: { open: async () => ({ add: async () => undefined }) },
    Request: class extends Request { constructor(input: string, init?: RequestInit) { super(new URL(input, 'https://example.test'), init) } },
  })
  const waitUntil = vi.fn()
  handlers.install({ waitUntil })
  handlers.message({ data: { type: 'OTHER' }, waitUntil })
  expect(skipWaiting).not.toHaveBeenCalled()
  handlers.message({ data: { type: 'APPLY_UPDATE' }, waitUntil })
  expect(skipWaiting).toHaveBeenCalledTimes(1)
})

it.each(['completed', 'in_progress'] as const)('allows explicit update with a persisted %s quiz without checking unrelated glossary activity', async status => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', display_name: null, csrf_token: 'synthetic', needs_identity: false, telegram_linked: true, link_pending: false, link_confirmed: true, link_target: null })
  vi.spyOn(api, 'options').mockResolvedValue({ ok: true, setup_options: { categories: [], question_count_choices: [5], difficulty_choices: ['any'] } })
  const state = vi.spyOn(api, 'state').mockResolvedValue({ ok: true, runner_state: {
    state: status, status: 'ok', session: { session_id: 1 },
    current_question: status === 'in_progress' ? { session_id: 1, question_id: 1, question_text: 'Saved question', order_index: 1, total_questions: 5, options: [{ option_index: 0, option_text: 'Answer' }] } : undefined,
    result: status === 'completed' ? { score: 5, total_questions: 5, percent: 100, summary: 'Saved result' } : undefined,
  } })
  const glossary = vi.spyOn(api, 'glossaryState')
  const user = userEvent.setup()
  render(<App />)
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Обновить' })[0]).toBeEnabled())
  await user.click(screen.getAllByRole('button', { name: 'Обновить' })[0])
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  await waitFor(() => expect(activateUpdate).toHaveBeenCalledWith(worker))
  expect(state).toHaveBeenCalledTimes(1)
  expect(glossary).not.toHaveBeenCalled()
})

it('keeps an unacknowledged quiz answer protected until reconciliation', async () => {
  vi.spyOn(api, 'me').mockResolvedValue({ ok: true, email: 'owner@example.test', display_name: null, csrf_token: 'synthetic', needs_identity: false, telegram_linked: true, link_pending: false, link_confirmed: true, link_target: null })
  vi.spyOn(api, 'options').mockResolvedValue({ ok: true, setup_options: { categories: [], question_count_choices: [5], difficulty_choices: ['any'] } })
  vi.spyOn(api, 'state').mockResolvedValue({ ok: true, runner_state: { state: 'in_progress', status: 'ok', session: { session_id: 1 }, current_question: { session_id: 1, question_id: 1, question_text: 'Saved question', order_index: 1, total_questions: 5, options: [{ option_index: 0, option_text: 'Answer' }] } } })
  vi.spyOn(api, 'answer').mockRejectedValue(new ApiError('network'))
  const user = userEvent.setup()
  render(<App />)
  await user.click(await screen.findByRole('radio', { name: /Answer/ }))
  await user.click(screen.getByRole('button', { name: 'Проверить ответ' }))
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Обновить' })[0]).toBeEnabled())
  await user.click(screen.getAllByRole('button', { name: 'Обновить' })[0])
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  expect(await screen.findByText(/Сначала подтвердите сохранение/)).toBeVisible()
  expect(activateUpdate).not.toHaveBeenCalled()
})
