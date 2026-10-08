import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ReadingOrder, readingOrder } from '../src/ReadingOrder'

it('orders prerequisites before an easier dependent, deduplicates works and excludes missing/cyclic preparation', () => {
  const base = { reading_level: 'core', importance: 'basic', importance_source: 'agent', why_read: 'Confirmed purpose', prerequisites: [] as string[] }
  const foundation = { ...base, id: 'z', work_id: 'foundation', reading_level: 'advanced' }
  const alias = { ...foundation, id: 'alias' }
  const dependent = { ...base, id: 'a', work_id: 'dependent', prerequisites: ['alias'] }
  const items = [dependent, foundation, alias, { ...base, id: 'missing', prerequisites: ['unknown'] }, { ...base, id: 'cycle1', prerequisites: ['cycle2'] }, { ...base, id: 'cycle2', prerequisites: ['cycle1'] }]
  const before = structuredClone(items)
  const order = readingOrder(items)
  expect(order.map(row => row.item.id)).toEqual(['z', 'a'])
  expect(order[1].prerequisites).toEqual([alias])
  expect(readingOrder([dependent], items)[0].prerequisites).toEqual([alias])
  expect(items).toEqual(before)
})

it('shows the route, reasons, status and external-topic preparation with working actions', async () => {
  const preparation = { id: 'prep', title: 'Основы', user_state: { reading_status: 'read' as const } }
  const book = { id: 'book', title: 'Практическая книга', reading_level: 'applied', importance: 'important', importance_source: 'teacher', why_read: 'Для освоения практики', prerequisites: ['prep'] }
  const select = vi.fn()
  render(<ReadingOrder items={[book]} allItems={[preparation, book]} busy={false} onSelect={select} />)
  const user = userEvent.setup()
  await user.click(screen.getByText('Рекомендуемая последовательность чтения'))
  const row = screen.getByRole('listitem')
  expect(within(row).getByText(/Применение · приоритет преподавателя/)).toBeVisible()
  await user.click(within(row).getByText('Зачем читать и что прочитать до этого'))
  expect(within(row).getByText('Для освоения практики')).toBeVisible()
  expect(within(row).getByText(/Подготовка/)).toHaveTextContent('Основы ✓')
  await user.click(within(row).getByRole('button', { name: 'Основы' }))
  expect(select).toHaveBeenCalledWith('prep')
  await user.click(within(row).getByRole('button', { name: 'Практическая книга' }))
  expect(select).toHaveBeenLastCalledWith('book')
})
