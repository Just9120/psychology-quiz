import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ResetView } from '../src/ResetView'
import { api, ApiError } from '../src/api'
import type { ResetPreview } from '../src/types'

const preview: ResetPreview = { ok: true, scope: 'all', topic: null, topics: ['Память'], revision: 'first', questions: 5, answers: 2, attempts: 1, active_attempts: 1 }
const run = async (operation: () => Promise<void>) => { try { await operation() } catch { /* App displays the error. */ } }

it('requires explicit confirmation, cancels without mutation, and disarms a lost response', async () => {
  const user = userEvent.setup(), cancel = vi.fn(), complete = vi.fn()
  const reset = vi.spyOn(api, 'resetLearning').mockRejectedValueOnce(new ApiError('network')).mockResolvedValue({ ok: true })
  vi.spyOn(api, 'resetPreview').mockResolvedValue({ ...preview, revision: 'new' })
  render(<ResetView initial={preview} busy={false} run={run} onCancel={cancel} onComplete={complete} />)
  const confirm = screen.getByRole('button', { name: 'Подтвердить сброс' })
  expect(confirm).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Отмена' }))
  expect(cancel).toHaveBeenCalledOnce(); expect(reset).not.toHaveBeenCalled()
  await user.click(screen.getByRole('checkbox'))
  await user.click(confirm)
  expect(reset).toHaveBeenCalledOnce(); expect(complete).not.toHaveBeenCalled()
  expect(confirm).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Обновить просмотр' }))
  expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(confirm).toBeDisabled()
  await user.click(screen.getByRole('checkbox'))
  await user.click(confirm)
  expect(reset).toHaveBeenLastCalledWith({ ...preview, revision: 'new' })
  expect(complete).toHaveBeenCalledOnce()
  vi.restoreAllMocks()
})

it('changing scope clears the previous confirmation and explains mixed-attempt preservation', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'resetPreview').mockResolvedValue({ ...preview, scope: 'topic', topic: 'Память', revision: 'topic' })
  render(<ResetView initial={preview} busy={false} run={run} onCancel={vi.fn()} onComplete={vi.fn()} />)
  await user.click(screen.getByRole('checkbox'))
  await user.selectOptions(screen.getByRole('combobox'), 'topic:Память')
  expect(api.resetPreview).toHaveBeenCalledWith('Память')
  expect(screen.getByRole('button', { name: 'Подтвердить сброс' })).toBeDisabled()
  expect(screen.getByText(/Ответы других тем/)).toBeVisible()
  vi.restoreAllMocks()
})
