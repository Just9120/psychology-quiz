import { chooseMenu } from './choose-menu'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { HomeworkView } from '../src/HomeworkView'
import type { HomeworkAssignment } from '../src/types'

it('filters module, discipline and concrete homework topic and recovers after catalogue changes', async () => {
  const first: HomeworkAssignment = { id: 'one', title: 'Первое задание', module: 'Модуль 1', discipline: 'Психология', topic: 'Память', description: 'Описание', question_count: 5, completed: false, finished_attempts: 0, best_score: null, best_total: null, active_session_id: null }
  const second = { ...first, id: 'two', title: 'Второе задание', module: 'Модуль 2', discipline: 'Физиология', topic: 'Движение' }
  const onStart = vi.fn()
  const props = { busy: false, confirmId: null, onStart, onConfirm: vi.fn(), onResume: vi.fn(), onRefresh: vi.fn() }
  const { rerender } = render(<HomeworkView {...props} catalog={{ ok: true, assignments: [first, second] }} />)
  const user = userEvent.setup()
  await chooseMenu(user, screen.getByLabelText('Модуль обучения'), 'module2')
  expect(screen.queryByRole('heading', { name: 'Первое задание' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Второе задание' })).toBeVisible()
  await chooseMenu(user, screen.getByLabelText('Модуль обучения'), '')
  await chooseMenu(user, screen.getByLabelText('Тема домашних заданий'), JSON.stringify(['Психология', 'Память']))
  expect(screen.queryByRole('heading', { name: 'Второе задание' })).not.toBeInTheDocument()
  await chooseMenu(user, screen.getByLabelText('Тема домашних заданий'), JSON.stringify(['Физиология', 'Движение']))
  await user.click(screen.getByRole('button', { name: 'Начать тест · 5 вопросов' }))
  expect(onStart).toHaveBeenCalledExactlyOnceWith('two')
  rerender(<HomeworkView {...props} catalog={{ ok: true, assignments: [first] }} />)
  expect(screen.getByLabelText('Тема домашних заданий')).toHaveValue('')
  expect(screen.getByRole('heading', { name: 'Первое задание' })).toBeVisible()
  rerender(<HomeworkView {...props} catalog={{ ok: true, assignments: [] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Домашних заданий пока нет.')
})

it('groups different assignments under the reviewed curriculum topic instead of their titles', async () => {
  const first: HomeworkAssignment = { id: 'one', title: 'Дневник', module: 'Модуль 1', discipline: 'Введение в профессию',
    discipline_id: 'intro', curriculum_topic: { id: 't_reviewed', title: 'Профессиональная рефлексия' },
    topic: 'Дневник', description: 'Описание', question_count: 5, completed: false, finished_attempts: 0,
    best_score: null, best_total: null, active_session_id: null }
  render(<HomeworkView catalog={{ ok: true, assignments: [first, { ...first, id: 'two', title: 'Наблюдение', topic: 'Наблюдение' }] }}
    busy={false} confirmId={null} onStart={vi.fn()} onConfirm={vi.fn()} onResume={vi.fn()} onRefresh={vi.fn()} />)
  const user = userEvent.setup()
  await chooseMenu(user, screen.getByLabelText('Дисциплина'), 'intro')
  await chooseMenu(user, screen.getByLabelText('Тема домашних заданий'), 't_reviewed')
  expect(screen.getByRole('heading', { name: 'Дневник' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Наблюдение' })).toBeVisible()
})
