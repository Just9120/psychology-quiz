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
      coverage: { unreleased_lessons: { total: 3, processing: { pending_review: 3 }, metadata_current: 3, known_holds: 3 }, tracked_sources: 66, untracked_files: 359, source_metadata: { current: 66 }, unmapped_published_questions: 83,
        lessons: [{ id: 'lesson', title: 'Проверенная учебная тема', discipline: 'Дисциплина', kinds: { theory: 0, glossary: 0, case: 0 }, source_metadata_current: false, processing_state: 'pending_review', known_hold: true, glossary_terms: null, notes: null, notes_state: 'UNSET' }] } } }
  render(<OwnerContentView data={data} busy={false} onRefresh={() => {}} />)
  expect(screen.getByText("\u0415\u0449\u0451 \u043d\u0435 \u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u043d\u043d\u044b\u0435 \u0443\u0447\u0435\u0431\u043d\u044b\u0435 \u0442\u0435\u043c\u044b: 3. \u0410\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0435 \u043c\u0435\u0442\u0430\u0434\u0430\u043d\u043d\u044b\u0435: 3; \u0442\u0435\u043c\u044b \u0441 \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f\u043c\u0438: 3." )).toBeVisible()
  expect(screen.getByText(/Редакция источника требует сверки/)).toBeVisible()
  expect(screen.getByText('Есть неразрешённое возражение к источнику.')).toBeVisible()
  expect(screen.getByText('Нет опубликованных вопросов с подтверждённой привязкой к этой теме.')).toBeVisible()
  expect(screen.getByText(/Отдельные термины: покрытие по этой теме не подтверждено/)).toBeVisible()
  expect(screen.getByText(/не подтверждает полное покрытие корпуса/)).toBeVisible()
})


it('shows prepared note counts without claiming Vault publication or complete coverage', () => {
  const data: OwnerContent = { ok: true, topics: [], unmapped_questions: 0,
    sources: { state: 'PARTIAL', captured_at: '2026-09-30T00:00:00Z',
      coverage: { tracked_sources: 1, untracked_files: 0, source_metadata: { current: 1 },
        unmapped_published_questions: 0, prepared_notes_unmapped: 2, unmapped_published_glossary: 1,
        lessons: [{ id: 'lesson', title: 'Тема', discipline: 'Дисциплина',
          kinds: { theory: 0, glossary: 0, case: 0 }, source_metadata_current: true,
          processing_state: 'processed', known_hold: false, glossary_terms: 2,
          notes: 3, notes_state: 'PREPARED' }] } } }
  render(<OwnerContentView data={data} busy={false} onRefresh={() => {}} />)
  expect(screen.getByText('Подготовлено заметок в переданном снимке: 3.')).toBeVisible()
  expect(screen.getByText('Опубликованных терминов с подтверждённой привязкой к этой теме в снимке: 2.')).toBeVisible()
  expect(screen.getByText('Опубликованных терминов без подтверждённой привязки к учебной теме в снимке: 1.')).toBeVisible()
  expect(screen.queryByText('Отдельные термины: покрытие по этой теме не подтверждено.')).not.toBeInTheDocument()
  expect(screen.getByText(/Подготовленных заметок без подтверждённой привязки к учебной теме: 2/)).toBeVisible()
  expect(screen.getByText(/не подтверждение публикации в Obsidian/)).toBeVisible()
})
