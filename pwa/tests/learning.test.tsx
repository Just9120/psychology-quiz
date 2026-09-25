import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { LearningView } from '../src/LearningView'
import { QuizView } from '../src/QuizView'
import { QuizSetup } from '../src/QuizSetup'
import type { AchievementsOverview, GoalsOverview, MasteryOverview, ReviewQueue } from '../src/types'

const queue: ReviewQueue = { ok: true, today: '2026-09-25', due_count: 2, items: [
  { kind: 'quiz', question_id: 7, topic: 'Кейсы', due_on: '2026-09-25', is_due: true, correct_streak: 0, reason: 'error' },
  { kind: 'glossary', topic_id: 'general', term_id: 'attention', topic: 'Общая психология', due_on: '2026-09-25', is_due: true, correct_streak: 1, reason: 'scheduled' },
] }
const mastery: MasteryOverview = { ok: true, questions: { ok: true, items: [], mastered_count: 0, assessed_count: 1 }, terms: { ok: true, items: [], mastered_count: 0, assessed_count: 1 } }
const goals: GoalsOverview = { ok: true, week_start: '2026-09-21', week_end_exclusive: '2026-09-28', goals: [
  { goal_kind: 'study', weekly_target: 2, completed: 1, reached: false },
  { goal_kind: 'review', weekly_target: null, completed: 1, reached: null },
  { goal_kind: 'reading', weekly_target: null, completed: 0, reached: null },
] }
const achievements: AchievementsOverview = { ok: true, achievements: [] }

it('shows personal due work and requires explicit replacement', async () => {
  const quiz = vi.fn(), glossary = vi.fn(), user = userEvent.setup()
  render(<LearningView review={queue} mastery={mastery} goals={goals} achievements={achievements} busy={false} onRefresh={vi.fn()} onSaveGoal={vi.fn()} onStartQuiz={quiz} onStartGlossary={glossary} />)
  expect(screen.getByText(/Сегодня к повторению · 2/)).toBeVisible()
  expect(screen.getByText(/недостаточно данных/)).toBeVisible()
  await user.click(screen.getByRole('button', { name: /Повторить вопросы/ }))
  expect(quiz).toHaveBeenCalledWith(false)
  expect(quiz).not.toHaveBeenCalledWith(true)
  await user.click(screen.getByRole('button', { name: 'Подтвердить замену попытки' }))
  expect(quiz).toHaveBeenCalledWith(true)
  await user.click(screen.getByRole('button', { name: /Термины: Общая психология/ }))
  expect(glossary).toHaveBeenCalledWith('general', false)
})

it('does not allow zero weekly target and saves a positive one', async () => {
  const save = vi.fn(), user = userEvent.setup()
  render(<LearningView review={{ ...queue, items: [], due_count: 0 }} mastery={mastery} goals={goals} achievements={achievements} busy={false} onRefresh={vi.fn()} onSaveGoal={save} onStartQuiz={vi.fn()} onStartGlossary={vi.fn()} />)
  const input = screen.getByLabelText('Завершённые попытки')
  await user.clear(input)
  await user.type(input, '0')
  expect(screen.getAllByRole('button', { name: 'Сохранить цель' })[0]).toBeDisabled()
  await user.clear(input)
  await user.type(input, '3')
  await user.click(screen.getAllByRole('button', { name: 'Сохранить цель' })[0])
  expect(save).toHaveBeenCalledWith('study', 3)
})

it('offers the standalone Cases topic and adaptive selection', async () => {
  const start = vi.fn(), user = userEvent.setup()
  render(<QuizSetup options={{ categories: [{ id: 9, name: 'Кейсы' }], question_count_choices: [5], difficulty_choices: ['any'], content_kind_choices: ['theory', 'glossary', 'case'] }} busy={false} hasAttempt={false} onStart={start} onResume={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Адаптивный' }))
  await user.click(screen.getByRole('button', { name: /Начать квиз/ }))
  expect(start).toHaveBeenCalledWith(expect.objectContaining({ quiz_mode: 'adaptive', category_ids: [], content_kinds: ['theory', 'glossary', 'case'] }))
})

it('explains every case alternative after an answer', () => {
  render(<QuizView state={{ state: 'completed', status: 'ok', session: { session_id: 1 }, result: { score: 1, total_questions: 1, percent: 100, summary: '' } }} feedback={{ selected_option_index: 0, selected_option_text: 'Уточнить запрос', is_correct: true, correct_option_index: 0, correct_option_text: 'Уточнить запрос', explanation: 'Контекст важен', case_review: { approach: 'Первая встреча', conditions: ['Нет срочной опасности'], ambiguity: 'При новых обстоятельствах пересмотреть.', option_rationales: ['Подходит', 'Преждевременно', 'Нет данных', 'Не диагностировать'] } }} feedbackQuestion={{ session_id: 1, question_id: 1, question_text: 'Что сделать?', order_index: 1, total_questions: 1, options: [] }} selected={null} pending={null} busy={false} onSelect={vi.fn()} onAnswer={vi.fn()} onNext={vi.fn()} onSetup={vi.fn()} onRefresh={vi.fn()} />)
  expect(screen.getByRole('region', { name: 'Разбор кейса' })).toHaveTextContent('При новых обстоятельствах пересмотреть.')
  expect(screen.getByText('Не диагностировать')).toBeVisible()
})
