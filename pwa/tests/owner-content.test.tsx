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


it('shows dated lesson coverage, unresolved source holds and unknown notes independently', () => {
  const data: OwnerContent = { ok: true, topics: [], unmapped_questions: 0,
    sources: { state: 'PARTIAL', captured_at: '2026-09-30T00:00:00Z', files: 425, folders: 93, processing_records: 6, known_holds: 2, processing: { pending_review: 6, new_unprocessed: 419 },
      coverage: { tracked_sources: 66, untracked_files: 359, source_metadata: { current: 66 }, unmapped_published_questions: 83,
        lessons: [{ id: 'lesson', title: 'Проверенная учебная тема', discipline: 'Дисциплина', kinds: { theory: 0, glossary: 0, case: 0 }, source_metadata_current: false, processing_state: 'pending_review', known_hold: true, glossary_terms: null, notes: null, notes_state: 'UNSET' }] } } }
  render(<OwnerContentView data={data} busy={false} onRefresh={() => {}} />)
  expect(screen.getByText(/Редакция источника требует сверки/)).toBeVisible()
  expect(screen.getByText('Есть неразрешённое возражение к источнику.')).toBeVisible()
  expect(screen.getByText('Нет опубликованных вопросов с подтверждённой привязкой к этой теме.')).toBeVisible()
  expect(screen.getByText(/Отдельные термины и личные заметки: покрытие по этой теме не подтверждено/)).toBeVisible()
  expect(screen.getByText(/не подтверждает полное покрытие корпуса/)).toBeVisible()
})


it('shows prepared note counts without claiming Vault publication or complete coverage', () => {
  const data: OwnerContent = { ok: true, topics: [], unmapped_questions: 0,
    sources: { state: 'PARTIAL', captured_at: '2026-09-30T00:00:00Z',
      coverage: { tracked_sources: 1, untracked_files: 0, source_metadata: { current: 1 },
        unmapped_published_questions: 0, prepared_notes_unmapped: 2,
        lessons: [{ id: 'lesson', title: 'Тема', discipline: 'Дисциплина',
          kinds: { theory: 0, glossary: 0, case: 0 }, source_metadata_current: true,
          processing_state: 'processed', known_hold: false, glossary_terms: null,
          notes: 3, notes_state: 'PREPARED' }] } } }
  render(<OwnerContentView data={data} busy={false} onRefresh={() => {}} />)
  expect(screen.getByText('Подготовлено заметок в переданном снимке: 3.')).toBeVisible()
  expect(screen.getByText(/Подготовленных заметок без подтверждённой привязки к учебной теме: 2/)).toBeVisible()
  expect(screen.getByText(/не подтверждение публикации в Obsidian/)).toBeVisible()
})
