import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { OwnerContentView } from '../src/OwnerContentView'
import type { OwnerContent } from '../src/types'

it('distinguishes unknown coverage from empty kinds and filters modules without inventing notes', async () => {
  const topic = { id: 'one', title: 'Первая тема', module: 'module1', questions: 1, kinds: { theory: 0, glossary: 0, case: 1 }, glossary_terms: null, literature_works: 1, notes_state: 'UNSET' as const, notes: null, gaps: ['theory', 'glossary'] }
  const data: OwnerContent = { ok: true, topics: [topic, { ...topic, id: 'two', title: 'Вторая тема', module: 'module2' }], sources: { state: 'UNSET' }, unmapped_questions: 2 }
  const refresh = vi.fn()
  render(<OwnerContentView data={data} busy={false} onRefresh={refresh} />)
  expect(screen.getByText(/Текущее покрытие неизвестно/)).toBeVisible()
  expect(screen.getAllByText('Нет опубликованных заданий: теория, глоссарий.')).toHaveLength(2)
  await userEvent.setup().selectOptions(screen.getByLabelText('Модуль обзора'), 'module2')
  expect(screen.queryByRole('heading', { name: 'Первая тема' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Вторая тема' })).toBeVisible()
  expect(screen.getByText(/Личные заметки Obsidian: покрытие не подтверждено/)).toBeVisible()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Обновить обзор' }))
  expect(refresh).toHaveBeenCalledOnce()
})
