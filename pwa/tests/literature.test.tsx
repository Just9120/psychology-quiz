import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { LiteratureView } from '../src/LiteratureView'
import { api, ApiError } from '../src/api'
import type { LiteratureCatalog } from '../src/types'

const catalog: LiteratureCatalog = { ok: true, topics: [{ topic_id: 'one', title: 'Первая тема', module: 'module1' }], works: [{ work_id: 'book', title: 'Учебная книга', authors: [], type: 'book', access_links: [], entries: [{ id: 'book', topic_id: 'one', topic_title: 'Первая тема', module: 'module1', year: null, importance: null, importance_source: null, source: { title: 'Учебный список', locator: 'Позиция 1', citation: 'Исходная запись' }, metadata_warnings: ['Год неизвестен'], user_state: null }] }] }

it('shows an empty catalog without inventing reading entries', () => {
  render(<LiteratureView initial={{ ...catalog, works: [], topics: [] }} busy={false} run={async op => op()} />)
  expect(screen.getByRole('heading', { name: 'Список пока пуст' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Сохранить чтение' })).not.toBeInTheDocument()
})

it.each([
  ['basic', 'Базовая', 'teacher', 'приоритет преподавателя'],
  ['important', 'Важная', 'agent', 'рекомендация агента'],
  ['additional', 'Дополнительная', 'teacher', 'приоритет преподавателя'],
  ['advanced', 'Углублённая', 'agent', 'рекомендация агента'],
] as const)('shows reviewed importance %s with its provenance', async (importance, label, source, sourceLabel) => {
  const entry = { ...catalog.works[0].entries[0], importance, importance_source: source }
  const current = { ...catalog, works: [{ ...catalog.works[0], entries: [entry] }] }
  render(<LiteratureView initial={current} busy={false} run={async op => op()} />)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Учебная книга' }))
  expect(screen.getByText(`Значимость: ${label} · ${sourceLabel}`)).toBeVisible()
})

it('opens reviewed text and audio offers externally without promising a subscription', async () => {
  const access_links = [
    { format: 'text' as const, provider: 'Литрес', url: 'https://www.litres.ru/book/exact/', access: 'provider_terms' as const, checked_at: '2026-09-29' },
    { format: 'audio' as const, provider: 'Литрес', url: 'https://www.litres.ru/audiobook/exact/', access: 'provider_terms' as const, checked_at: '2026-09-29' },
  ]
  const current = { ...catalog, works: [{ ...catalog.works[0], access_links }] }
  render(<LiteratureView initial={current} busy={false} run={async op => op()} />)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Учебная книга' }))
  expect(screen.getByText(/Наличие доступа, цена и совпадение издания проверяются там/)).toBeVisible()
  for (const label of ['Текст · Литрес', 'Аудио · Литрес']) {
    const link = screen.getByRole('link', { name: label })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  }
})

it('blocks another reading write after lost confirmation until successful readback', async () => {
  const save = vi.spyOn(api, 'readingProgress').mockRejectedValue(new ApiError('network'))
  const reload = vi.spyOn(api, 'literature').mockRejectedValueOnce(new ApiError('network')).mockResolvedValue(catalog)
  const run = async (op: () => Promise<void>) => { try { await op() } catch { /* App displays the error. */ } }
  render(<LiteratureView initial={catalog} busy={false} run={run} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Учебная книга' }))
  expect(screen.getByText('Автор не указан в источнике')).toBeVisible()
  expect(screen.getByText('Значимость: не определена')).toBeVisible()
  expect(screen.queryByLabelText('Прочитано, %')).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Статус чтения'), 'in_progress')
  await user.click(screen.getByRole('button', { name: 'Сохранить чтение' }))
  expect(save).toHaveBeenCalledWith('book', 'in_progress', null)
  expect(screen.getByLabelText('Статус чтения')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Обновить каталог и прогресс' }))
  expect(screen.getByLabelText('Статус чтения')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Обновить каталог и прогресс' }))
  expect(reload).toHaveBeenCalledTimes(2)
  expect(screen.getByLabelText('Статус чтения')).toHaveValue('not_started')
  expect(screen.getByLabelText('Статус чтения')).toBeEnabled()
  expect(save).toHaveBeenCalledTimes(1)
})
