import { useRef, type ReactNode } from 'react'
import { ChoiceMenu } from './ChoiceMenu'
import type { ReadingStatus } from './types'

export const readingStatuses: Record<ReadingStatus, string> = {
  not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', deferred: 'Отложено',
}

export type LiteratureSort = 'catalog' | 'title' | 'status'
const statusOrder: Record<ReadingStatus, number> = { in_progress: 0, not_started: 1, deferred: 2, read: 3 }

export function compareBooks(sort: LiteratureSort, a: { title?: string; status: ReadingStatus }, b: { title?: string; status: ReadingStatus }) {
  if (sort === 'catalog') return 0
  return (sort === 'status' ? statusOrder[a.status] - statusOrder[b.status] : 0)
    || (a.title ?? '').localeCompare(b.title ?? '', 'ru')
}

export function LiteratureControls({ query, onQuery, filters, onReset, sort, onSort, busy, children }: {
  query: string; onQuery: (value: string) => void; filters: string[]; onReset: () => void
  sort: LiteratureSort; onSort: (value: LiteratureSort) => void; busy: boolean; children: ReactNode
}) {
  const search = useRef<HTMLInputElement>(null)
  return <div className="literature-controls">
    <label className="field">Поиск по названию или автору
      <input ref={search} type="search" value={query} onChange={event => onQuery(event.target.value)} placeholder="Название или автор" />
    </label>
    <div className="literature-control-row">
      <details className="literature-filter-panel">
        <summary>Фильтры{filters.length ? ` · ${filters.length}` : ''}</summary>
        <div className="panel">{children}</div>
      </details>
      <ChoiceMenu label="Сортировка" value={sort} disabled={busy} onChange={value => onSort(value as LiteratureSort)}
        options={[{ value: 'catalog', label: 'По каталогу' }, { value: 'title', label: 'По названию' }, { value: 'status', label: 'По статусу чтения' }]} />
    </div>
    {(filters.length > 0 || query.trim()) && <div className="literature-active-filters">
      {filters.map((filter, index) => <span className="status-chip" key={index}>{filter}</span>)}
      <button type="button" className="text-button" onClick={() => { onReset(); search.current?.focus() }}>Сбросить фильтры</button>
    </div>}
  </div>
}

export function LiteratureEmpty({ filtered, onReset }: { filtered: boolean; onReset: () => void }) {
  return <div className="panel empty-state">
    <h2>{filtered ? 'Нет совпадений' : 'В каталоге пока нет материалов'}</h2>
    {filtered && <button type="button" className="button secondary" onClick={onReset}>Очистить поиск и фильтры</button>}
  </div>
}
