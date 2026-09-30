import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { LiteratureView } from '../src/LiteratureView'
import { MiniLiterature } from '../src/miniapp/MiniLiterature'
import { api, ApiError } from '../src/api'
import type { LiteratureCatalog } from '../src/types'

const catalog: LiteratureCatalog = { ok: true, topics: [{ topic_id: 'one', title: 'Первая тема', module: 'module1' }], works: [{ work_id: 'book', title: 'Учебная книга', authors: [], type: 'book', access_links: [], entries: [{ id: 'book', topic_id: 'one', topic_title: 'Первая тема', module: 'module1', year: null, importance: null, importance_source: null, source: { title: 'Учебный список', locator: 'Позиция 1', citation: 'Исходная запись' }, metadata_warnings: ['Год неизвестен'], user_state: null }] }] }

it.each(['pwa', 'miniapp'])('combines module/topic/status filters without borrowing another association in %s', async client => {
  const first = { ...catalog.works[0].entries[0], title: 'Учебная книга' }
  const second = { ...first, id: 'book-two', topic_id: 'two', topic_title: 'Вторая тема', module: 'module2',
    user_state: { literature_id: 'book-two', reading_status: 'read' as const, progress_percent: 100, updated_at: '2026-09-29' } }
  const topics = [...catalog.topics, { topic_id: 'two', title: 'Вторая тема', module: 'module2' }]
  if (client === 'pwa') render(<LiteratureView initial={{ ...catalog, topics, works: [{ ...catalog.works[0], entries: [first, second] }] }} busy={false} run={async op => op()} />)
  else render(<MiniLiterature initial={[first, second]} topics={topics} busy={false} run={async op => op()} />)
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('Модуль литературы'), 'module1')
  await user.selectOptions(screen.getByLabelText('Фильтр статуса чтения'), 'read')
  expect(screen.queryByRole('button', { name: 'Учебная книга' })).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Фильтр статуса чтения'), 'not_started')
  expect(screen.getByRole('button', { name: 'Учебная книга' })).toBeVisible()
  await user.selectOptions(screen.getByLabelText(client === 'pwa' ? 'Тема литературы' : 'Тема'), 'one')
  await user.selectOptions(screen.getByLabelText('Модуль литературы'), 'module2')
  expect(screen.getByLabelText(client === 'pwa' ? 'Тема литературы' : 'Тема')).toHaveValue('')
  await user.selectOptions(screen.getByLabelText('Фильтр статуса чтения'), 'read')
  expect(screen.getByRole('button', { name: 'Учебная книга' })).toBeVisible()
})

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


it.each(['pwa', 'miniapp'])('shows scoped work totals and current reading independently of the status filter in %s', async client => {
  const first = { ...catalog.works[0].entries[0], work_id: 'book', title: 'Учебная книга', user_state: { literature_id: 'book', reading_status: 'read' as const, progress_percent: 100, updated_at: '2026-09-30' } }
  const second = { ...first, id: 'book-two', topic_id: 'two', topic_title: 'Вторая тема', module: 'module2', user_state: { ...first.user_state, literature_id: 'book-two', reading_status: 'in_progress' as const } }
  const topics = [...catalog.topics, { topic_id: 'two', title: 'Вторая тема', module: 'module2' }]
  if (client === 'pwa') render(<LiteratureView initial={{ ...catalog, topics, works: [{ ...catalog.works[0], entries: [first, second] }] }} busy={false} run={async op => op()} />)
  else render(<MiniLiterature initial={[first, second]} topics={topics} busy={false} run={async op => op()} />)
  expect(screen.getByText('Прочитано 0 из 1')).toBeVisible()
  expect(screen.getByText(/У 1 работ отметки/)).toBeVisible()
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('Фильтр статуса чтения'), 'read')
  expect(screen.getByText('Прочитано 0 из 1')).toBeVisible()
  await user.selectOptions(screen.getByLabelText('Модуль литературы'), 'module1')
  expect(screen.getByText('Прочитано 1 из 1')).toBeVisible()
  expect(screen.queryByText(/У 1 работ отметки/)).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Модуль литературы'), 'module2')
  const current = screen.getByRole('complementary', { name: 'Прогресс списка чтения' })
  await user.click(current.querySelector('button')!)
  expect(screen.getByLabelText(client === 'pwa' ? 'Статус чтения' : 'Статус')).toHaveValue('in_progress')
})


it('shares a saved work status across reading lists and exposes exactly four choices', async () => {
  const second = { ...catalog.works[0].entries[0], id: 'book-two', topic_title: 'Вторая тема' }
  const current = { ...catalog, works: [{ ...catalog.works[0], entries: [...catalog.works[0].entries, second] }] }
  vi.spyOn(api, 'readingProgress').mockResolvedValue({ ok: true, literature_progress: {
    literature_id: 'book', work_id: 'book', reading_status: 'deferred', progress_percent: null, updated_at: '2026-09-30T08:00:00Z',
  } })
  render(<LiteratureView initial={current} busy={false} run={async op => op()} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Учебная книга' }))
  const select = screen.getByLabelText('Статус чтения')
  expect([...select.querySelectorAll('option')].map(option => option.textContent)).toEqual(['Не начато', 'Читаю', 'Прочитано', 'Отложено'])
  await user.selectOptions(select, 'deferred')
  await user.click(screen.getByRole('button', { name: 'Сохранить чтение' }))
  await user.selectOptions(screen.getByLabelText('Учебный список'), 'book-two')
  expect(screen.getByLabelText('Статус чтения')).toHaveValue('deferred')
  await user.click(screen.getByRole('button', { name: '← К списку литературы' }))
  await user.selectOptions(screen.getByLabelText('Фильтр статуса чтения'), 'deferred')
  expect(screen.getByText('Первая тема · Отложено')).toBeVisible()
  expect(screen.getByText('Вторая тема · Отложено')).toBeVisible()
})
