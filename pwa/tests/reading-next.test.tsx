import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ReadingSummary, readingNextStep } from '../src/ReadingSummary'

const state = (updated_at: string) => ({ reading_status: 'in_progress' as const, updated_at })

it('continues recent reading in the selected scope and opens that association', async () => {
  const items = [{ id: 'a', title: 'Earlier', user_state: state('2026-09-01T12:00:00Z') },
    { id: 'b', title: 'Later', user_state: state('2026-09-29T12:00:00Z') }]
  expect(readingNextStep(items)?.id).toBe('b')
  expect(readingNextStep(items.slice(0, 1))?.id).toBe('a')
  const onSelect = vi.fn()
  render(<ReadingSummary items={items} busy={false} onSelect={onSelect} />)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Продолжить «Later»' }))
  expect(onSelect).toHaveBeenCalledWith('b')
  expect(screen.getByText('Вы уже начали эту книгу. Продолжите чтение перед выбором следующей.')).toBeVisible()
})

it('does not recommend conflicts, finished books or invalid date priority', () => {
  const items = [{ id: 'a', work_id: 'conflict', user_state: state('2026-09-30T12:00:00Z') },
    { id: 'b', work_id: 'conflict', user_state: { reading_status: 'read' as const } },
    { id: 'c', user_state: state('2026-02-30T12:00:00Z') },
    { id: 'd', user_state: state('2026-09-01T12:00:00Z') }]
  expect(readingNextStep(items)?.id).toBe('d')
  expect(readingNextStep(items.slice(0, 2))).toBeNull()
  expect(readingNextStep(items.slice(0, 1))?.id).toBe('a')
  expect(readingNextStep([])).toBeNull()
})


it('starts reviewed reading only after prerequisites across topics and labels its origin', async () => {
  const item = { id: 'next', title: 'Intro', importance: 'basic', importance_source: 'agent', reading_level: 'foundation', why_read: 'Вводный курс.', prerequisites: ['previous'] }
  const previous = { id: 'previous', work_id: 'previous', user_state: { reading_status: 'read' as const } }
  expect(readingNextStep([item])).toBeNull()
  expect(readingNextStep([item], [item, previous])?.id).toBe('next')
  expect(readingNextStep([{ ...item, reading_level: null }], [item, previous])).toBeNull()
  expect(readingNextStep([item], [item, previous, { id: 'alias', work_id: 'previous' }])).toBeNull()
  expect(readingNextStep([{ ...item, user_state: { reading_status: 'deferred' as const } }])).toBeNull()
  const onSelect = vi.fn()
  render(<ReadingSummary items={[item]} allItems={[item, previous]} busy={false} onSelect={onSelect} />)
  expect(screen.getByText('Рекомендация агента. Вводный курс.')).toBeVisible()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Начать «Intro»' }))
  expect(onSelect).toHaveBeenCalledWith('next')
})


it('distinguishes agent sequence from the teacher priority', () => {
  const item = { id: 'classic', title: 'Classic', importance: 'additional', importance_source: 'teacher', reading_level: 'deepening', why_read: 'После вводного курса.', prerequisites: [] }
  render(<ReadingSummary items={[item]} busy={false} onSelect={vi.fn()} />)
  expect(screen.getByText('Рекомендация агента. После вводного курса. Приоритет книги — из учебного списка.')).toBeVisible()
})


it('continues a video by viewing and keeps its exact selection callback', async () => {
  const onSelect = vi.fn()
  const film = { id: 'film', type: 'video', title: 'Отец', user_state: state('2026-09-30T12:00:00Z') }
  render(<ReadingSummary items={[film]} busy={false} onSelect={onSelect} />)
  expect(screen.getByText('Вы уже начали этот видеоматериал. Продолжите просмотр перед выбором следующего.')).toBeVisible()
  expect(screen.queryByText('Вы уже начали эту книгу. Продолжите чтение перед выбором следующей.')).not.toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Продолжить «Отец»' }))
  expect(onSelect).toHaveBeenCalledWith('film')
})

it('labels teacher priority of an article as material while retaining agent recommendation', () => {
  const article = { id: 'article', type: 'article', title: 'Методология', importance: 'additional',
    importance_source: 'teacher', reading_level: 'deepening', why_read: 'Сопоставьте подходы.', prerequisites: [] }
  render(<ReadingSummary items={[article]} busy={false} onSelect={vi.fn()} />)
  expect(screen.getByText('Рекомендация агента. Сопоставьте подходы. Приоритет материала — из учебного списка.')).toBeVisible()
})


it.each([
  ['foundation', 'core'], ['core', 'applied'], ['applied', 'deepening'],
  ['deepening', 'advanced'], ['advanced', 'reference'],
])('follows the reviewed %s stage before %s rather than association ID', (earlier, later) => {
  const common = { importance: 'additional', importance_source: 'agent',
    why_read: 'Проверенный этап чтения.', prerequisites: [] }
  const first = { ...common, id: 'z', reading_level: earlier }
  const second = { ...common, id: 'a', reading_level: later }
  expect(readingNextStep([second, first])?.id).toBe('z')
  expect(readingNextStep([second, { ...first, user_state: { reading_status: 'read' as const } }])?.id).toBe('a')
  expect(readingNextStep([{ ...second, user_state: state('2026-10-03T16:00:00Z') }, first])?.id).toBe('a')
})

it('preserves reviewed book priority ahead of reading stage and excludes missing prerequisites', () => {
  const common = { importance_source: 'teacher', why_read: 'Приоритет курса.', prerequisites: [] }
  const foundation = { ...common, id: 'z', importance: 'additional', reading_level: 'foundation' }
  const required = { ...common, id: 'a', importance: 'basic', reading_level: 'applied' }
  expect(readingNextStep([foundation, required])?.id).toBe('a')
  expect(readingNextStep([foundation, { ...required, prerequisites: ['missing'] }])?.id).toBe('z')
})
