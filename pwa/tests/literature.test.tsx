import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { LiteratureView } from '../src/LiteratureView'
import { api, ApiError } from '../src/api'
import type { LiteratureCatalog } from '../src/types'

const catalog: LiteratureCatalog = { ok: true, topics: [{ topic_id: 'one', title: 'Первая тема', module: 'module1' }], works: [{ work_id: 'book', title: 'Учебная книга', authors: [], type: 'book', entries: [{ id: 'book', topic_id: 'one', topic_title: 'Первая тема', module: 'module1', year: null, source: { id: 'source', title: 'Учебный список', locator: 'Позиция 1', citation: 'Исходная запись' }, metadata_warnings: ['Год неизвестен'], user_state: null }] }] }

it('shows an empty catalog without inventing reading entries', () => {
  render(<LiteratureView initial={{ ...catalog, works: [], topics: [] }} busy={false} run={async op => op()} />)
  expect(screen.getByRole('heading', { name: 'Список пока пуст' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Сохранить чтение' })).not.toBeInTheDocument()
})

it('blocks another reading write after lost confirmation until successful readback', async () => {
  const save = vi.spyOn(api, 'readingProgress').mockRejectedValue(new ApiError('network'))
  const reload = vi.spyOn(api, 'literature').mockRejectedValueOnce(new ApiError('network')).mockResolvedValue(catalog)
  const run = async (op: () => Promise<void>) => { try { await op() } catch { /* App displays the error. */ } }
  render(<LiteratureView initial={catalog} busy={false} run={run} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Учебная книга' }))
  expect(screen.getByText('Автор не указан в источнике')).toBeVisible()
  await user.selectOptions(screen.getByLabelText('Статус чтения'), 'in_progress')
  await user.type(screen.getByLabelText('Прочитано, %'), '30')
  await user.click(screen.getByRole('button', { name: 'Сохранить чтение' }))
  expect(save).toHaveBeenCalledWith('book', 'in_progress', 30)
  expect(screen.getByLabelText('Статус чтения')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Обновить каталог и прогресс' }))
  expect(screen.getByLabelText('Статус чтения')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Обновить каталог и прогресс' }))
  expect(reload).toHaveBeenCalledTimes(2)
  expect(screen.getByLabelText('Статус чтения')).toHaveValue('not_started')
  expect(screen.getByLabelText('Статус чтения')).toBeEnabled()
  expect(save).toHaveBeenCalledTimes(1)
})
