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
