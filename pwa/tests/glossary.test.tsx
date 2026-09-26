import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { GlossaryView } from '../src/GlossaryView'
import { api, ApiError } from '../src/api'
import type { GlossaryState } from '../src/types'

const initial: GlossaryState = { state: 'in_progress', session_id: 'one', topic_id: 'memory', current_question: {
  session_id: 'one', step_id: 1, topic_id: 'memory', topic_title: 'Память', order_index: 1, total_questions: 5,
  term: 'Воспроизведение', options: [{ option_index: 0, option_text: 'Восстановление материала' }, { option_index: 1, option_text: 'Другой ответ' }],
} }
const topics = [{ topic_id: 'memory', title: 'Память', available_count: 5 }]
const run = async (operation: () => Promise<void>) => { try { await operation() } catch { /* App shows an error. */ } }

it('locks a lost answer to the original choice and resumes persisted feedback', async () => {
  const user = userEvent.setup()
  const answer = vi.spyOn(api, 'glossaryAnswer').mockRejectedValueOnce(new ApiError('network')).mockResolvedValue({ ok: true, glossary_state: { state: 'feedback', feedback: { step_id: 1, is_correct: true, selected_option_index: 0, selected_option_text: 'Восстановление материала', correct_option_index: 0, correct_option_text: 'Восстановление материала', explanation: 'Объяснение', answered_count: 1, total_questions: 5, has_next: true } } })
  render(<GlossaryView initial={initial} topics={topics} busy={false} run={run} />)
  await user.click(screen.getByRole('radio', { name: /Восстановление материала/ }))
  await user.click(screen.getByRole('button', { name: 'Проверить определение' }))
  expect(screen.getByRole('radio', { name: /Другой ответ/ })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Повторить тот же ответ' }))
  expect(answer).toHaveBeenNthCalledWith(1, 'one', 1, 0)
  expect(answer).toHaveBeenNthCalledWith(2, 'one', 1, 0)
  expect(screen.getByText('Ответ сохранён · 1 из 5')).toBeVisible()
  vi.restoreAllMocks()
})

it('requires replacement confirmation and disarms uncertain setup until readback', async () => {
  const user = userEvent.setup()
  const start = vi.spyOn(api, 'glossaryStart').mockRejectedValue(new ApiError('network'))
  vi.spyOn(api, 'glossaryState').mockResolvedValue({ ok: true, glossary_state: initial })
  render(<GlossaryView initial={initial} topics={topics} busy={false} run={run} />)
  await user.click(screen.getByRole('button', { name: '← К темам глоссария' }))
  expect(screen.getByRole('button', { name: 'Начать тест по терминам' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'К сохранённому тесту' }))
  expect(start).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '← К темам глоссария' }))
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: 'Начать тест по терминам' }))
  expect(start).toHaveBeenCalledWith('memory', 5, 'one', true)
  expect(screen.queryByRole('button', { name: 'Начать тест по терминам' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Восстановить глоссарий' }))
  expect(screen.getByRole('button', { name: 'Проверить определение' })).toBeVisible()
  vi.restoreAllMocks()
})

it('starts a mixed topic attempt with the selected topic IDs', async () => {
  const user = userEvent.setup()
  const start = vi.spyOn(api, 'glossaryStart').mockResolvedValue({ ok: true, glossary_state: initial })
  render(<GlossaryView initial={{ state: 'idle' }} topics={[...topics,
    { topic_id: 'attention', title: 'Внимание', available_count: 5 }]} busy={false} run={run} />)
  await user.selectOptions(screen.getByLabelText('Режим'), 'mix')
  expect(screen.getByRole('button', { name: 'Начать тест по терминам' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: /Память/ }))
  await user.click(screen.getByRole('checkbox', { name: /Внимание/ }))
  await user.click(screen.getByRole('button', { name: 'Начать тест по терминам' }))
  expect(start).toHaveBeenCalledWith(['memory', 'attention'], 5, null, false)
  vi.restoreAllMocks()
})
