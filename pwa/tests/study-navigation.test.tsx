import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { QuizSetup } from '../src/QuizSetup'
import type { SetupOptions } from '../src/types'

const options: SetupOptions = {
  categories: [{ id: 1, name: 'Общая психология' }, { id: 2, name: 'Консультирование' }],
  question_count_choices: [5, 10], difficulty_choices: ['any'],
  study_navigation: [
    { category_id: 1, discipline_id: 'general', title: 'Общая психология', modules: ['module1'], topics: [
      { id: 't_000000000001', title: 'Внимание', question_count: 6 },
      { id: 't_000000000002', title: 'Память', question_count: 4 }] },
    { category_id: 2, discipline_id: 'counseling', title: 'Консультирование', modules: ['module2', 'module3'], topics: [
      { id: 't_000000000003', title: 'Первичная встреча', question_count: 5 }] },
  ],
}

function setup() {
  const start = vi.fn(), user = userEvent.setup()
  render(<QuizSetup options={options} busy={false} activeSessionId={null} onStart={start} onResume={vi.fn()} />)
  return { start, user }
}

async function module(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('combobox', { name: 'Модуль обучения' }))
  await user.click(screen.getByRole('option', { name }))
}

it('filters a shared discipline through each of its modules and starts only the chosen topic', async () => {
  const { start, user } = setup()
  await module(user, 'Модуль 3')
  expect(screen.queryByRole('radio', { name: 'Общая психология' })).not.toBeInTheDocument()
  const group = screen.getByRole('radio', { name: 'Консультирование' }).closest('.study-discipline')!
  await user.click(within(group as HTMLElement).getByText('Темы дисциплины · 1'))
  await user.click(screen.getByRole('radio', { name: 'Первичная встреча · 5 вопр.' }))
  await module(user, 'Модуль 2')
  expect(screen.getByRole('radio', { name: 'Первичная встреча · 5 вопр.' })).toBeChecked()
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start).toHaveBeenCalledWith(expect.objectContaining({
    quiz_mode: 'single', category_ids: [2], topic_ids: ['t_000000000003'],
  }), false)
})

it('preserves a topic across module filters and combines it with a whole second discipline', async () => {
  const { start, user } = setup()
  await user.click(screen.getByRole('button', { name: 'Микс тем' }))
  await module(user, 'Модуль 1')
  await user.click(screen.getByText('Темы дисциплины · 2'))
  await user.click(screen.getByRole('checkbox', { name: 'Внимание · 6 вопр.' }))
  await module(user, 'Модуль 3')
  await user.click(screen.getByRole('checkbox', { name: 'Консультирование' }))
  expect(screen.getByRole('status')).toHaveTextContent('Выбрано дисциплин: 2')
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  const result = start.mock.calls[0][0]
  expect(result.quiz_mode).toBe('selected_mix')
  expect(new Set(result.category_ids)).toEqual(new Set([1, 2]))
  expect(new Set(result.topic_ids)).toEqual(new Set(['t_000000000001', 't_000000000003']))
})

it('choosing a whole discipline clears its partial topic scope; all mode has no hidden filter', async () => {
  const { start, user } = setup()
  await user.click(screen.getByText('Темы дисциплины · 2'))
  await user.click(screen.getByRole('radio', { name: 'Память · 4 вопр.' }))
  await user.click(screen.getByRole('radio', { name: 'Общая психология' }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start.mock.calls[0][0]).not.toHaveProperty('topic_ids')
  await module(user, 'Модуль 3')
  await user.click(screen.getByRole('button', { name: 'Все темы' }))
  await user.click(screen.getByRole('button', { name: 'Начать квиз' }))
  expect(start.mock.calls[1][0]).toMatchObject({ quiz_mode: 'all', category_ids: [] })
  expect(start.mock.calls[1][0]).not.toHaveProperty('topic_ids')
})
