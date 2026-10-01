import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { UpdateButton } from '../src/UpdateButton'
import { activateUpdate } from '../src/pwaUpdate'
vi.mock('../src/pwaUpdate', async importOriginal => ({ ...await importOriginal<typeof import('../src/pwaUpdate')>(), useWaitingUpdate: () => worker, activateUpdate: vi.fn() }))
const worker = { postMessage: vi.fn() } as unknown as ServiceWorker
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })
it('defers and blocks active attempts and failed state checks', async () => {
  const user = userEvent.setup(), check = vi.fn().mockResolvedValue(true)
  render(<UpdateButton busy={false} checkActive={check} />)
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Позже' }))
  expect(check).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Сначала завершите')
  expect(activateUpdate).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Продолжить занятие' }))
  check.mockRejectedValue(new Error('offline'))
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getByRole('button', { name: 'Обновить сейчас' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Не удалось проверить')
  expect(activateUpdate).not.toHaveBeenCalled()
})
it('activates only after confirmation and no current attempt', async () => {
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
