import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { HomeworkView } from '../src/HomeworkView'
import type { HomeworkAssignment } from '../src/types'

it('filters concrete homework topics without module labels and recovers after catalogue changes', async () => {
  const first: HomeworkAssignment = { id: 'one', title: 'Первое задание', module: 'Модуль 1', discipline: 'Психология', topic: 'Память', description: 'Описание', question_count: 5, completed: false, finished_attempts: 0, best_score: null, best_total: null, active_session_id: null }
  const second = { ...first, id: 'two', title: 'Второе задание', module: 'Модуль 2', discipline: 'Физиология', topic: 'Движение' }
  const onStart = vi.fn()
  const props = { busy: false, confirmId: null, onStart, onConfirm: vi.fn(), onResume: vi.fn(), onRefresh: vi.fn() }
  const { rerender } = render(<HomeworkView {...props} catalog={{ ok: true, assignments: [first, second] }} />)
  const user = userEvent.setup()
  expect(screen.queryByText(/Модуль/)).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Тема домашних заданий'), JSON.stringify(['Психология', 'Память']))
  expect(screen.queryByRole('heading', { name: 'Второе задание' })).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Тема домашних заданий'), JSON.stringify(['Физиология', 'Движение']))
  await user.click(screen.getByRole('button', { name: 'Начать тест · 5 вопросов' }))
  expect(onStart).toHaveBeenCalledExactlyOnceWith('two')
  rerender(<HomeworkView {...props} catalog={{ ok: true, assignments: [first] }} />)
  expect(screen.getByLabelText('Тема домашних заданий')).toHaveValue('')
  expect(screen.getByRole('heading', { name: 'Первое задание' })).toBeVisible()
  rerender(<HomeworkView {...props} catalog={{ ok: true, assignments: [] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Домашних заданий пока нет.')
})
