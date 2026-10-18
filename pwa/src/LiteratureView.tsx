import { BookOffers } from './BookOffers'
import { ChoiceMenu } from './ChoiceMenu'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { materialType } from './materialType'
import { readRoute, writeRoute } from './navigation'
import { ReadingOrder } from './ReadingOrder'
import { ReadingSummary } from './ReadingSummary'
import { BookSearch } from './BookSearch'
import { api, ApiError } from './api'
import type { LiteratureCatalog, LiteratureEntry, ReadingStatus } from './types'

const statuses: Record<ReadingStatus, string> = {
  not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', deferred: 'Отложено',
}
const importanceLabels = { basic: 'Базовая', important: 'Важная', additional: 'Дополнительная', advanced: 'Углублённая' } as const
const importanceSources = { teacher: 'приоритет преподавателя', agent: 'рекомендация агента' } as const

export function LiteratureView({ initial, busy, run, locationVersion = 0, onCatalog, onUncertain }: { initial: LiteratureCatalog; busy: boolean; locationVersion?: number; onCatalog?: (catalog: LiteratureCatalog) => void; onUncertain?: () => void; run: (operation: () => Promise<void>) => Promise<void> }) {
  const [catalog, setCatalog] = useState(initial)
  const initialParams = readRoute()?.view === 'literature' ? readRoute()!.params : new URLSearchParams()
  const [query, setQuery] = useState(initialParams.get('q') ?? '')
  const heading = useRef<HTMLHeadingElement>(null)
  const returnTo = useRef<{ y: number; element: HTMLElement | null } | null>(null)
  const [topic, setTopic] = useState(initialParams.get('topic') ?? '')
  const [statusFilter, setStatusFilter] = useState<ReadingStatus | ''>((['not_started', 'in_progress', 'read', 'deferred'].includes(initialParams.get('status') ?? '') ? initialParams.get('status') : '') as ReadingStatus | '')
  const [workId, setWorkId] = useState<string | null>(initialParams.get('book'))
  const [entryId, setEntryId] = useState<string | null>(initialParams.get('entry'))
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const work = catalog.works.find(item => item.work_id === workId)
  const entry = work?.entries.find(item => item.id === entryId) ?? work?.entries[0]
  const readingTopics = catalog.reading_topics ?? catalog.topics
  const inScope = (link: LiteratureEntry) => !topic || (link.reading_topics
    ? link.reading_topics.some(item => item.id === topic) : link.topic_id === topic)
  const matches = (link: LiteratureEntry) => inScope(link)
    && (!statusFilter || (link.user_state?.reading_status ?? 'not_started') === statusFilter)
  const visible = catalog.works.filter(item => item.entries.some(matches) && `${item.title} ${item.authors.join(' ')}`.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')))
  const summaryItems = catalog.works.flatMap(item => item.entries.filter(inScope).map(link => ({ ...link, work_id: item.work_id, title: item.title, authors: item.authors, type: item.type })))

  function route(overrides: Record<string, string | null> = {}, replace = false) {
    const params = new URLSearchParams()
    const values = { book: workId, entry: entryId, topic, status: statusFilter, q: query, ...overrides }
    Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value) })
    if (readRoute()?.view === 'literature') writeRoute('literature', params, replace)
  }
  useEffect(() => {
    const current = readRoute()
    if (current?.view !== 'literature') return
    setWorkId(current.params.get('book')); setEntryId(current.params.get('entry'))
    setTopic(current.params.get('topic') ?? ''); setQuery(current.params.get('q') ?? '')
    const filter = current.params.get('status') ?? ''
    setStatusFilter((['not_started', 'in_progress', 'read', 'deferred'].includes(filter) ? filter : '') as ReadingStatus | '')
  }, [locationVersion])
  useEffect(() => { if (entry) setStatus(entry.user_state?.reading_status ?? 'not_started') }, [entry?.id])
  useLayoutEffect(() => {
    if (workId && entry) { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView?.({ block: 'start' }) }
    else if (returnTo.current) {
      const previous = returnTo.current
      previous.element?.isConnected && previous.element.focus({ preventScroll: true })
      // The source button may have been remounted; use its stable entry ID instead.
      document.getElementById(`literature-${previous.element?.dataset.entry ?? ''}`)?.focus({ preventScroll: true })
      window.scrollTo?.(0, previous.y)
    }
  }, [workId])
  function backToList() { setWorkId(null); setEntryId(null); setSaved(false); route({ book: null, entry: null }) }
  function openEntry(id: string) {
    const selectedWork = catalog.works.find(item => item.entries.some(link => link.id === id))
    if (selectedWork) { returnTo.current = { y: window.scrollY, element: document.activeElement as HTMLElement }; setWorkId(selectedWork.work_id); select(selectedWork.entries.find(link => link.id === id)!); route({ book: selectedWork.work_id, entry: id }) }
  }
  function select(link: LiteratureEntry) {
    setEntryId(link.id); setStatus(link.user_state?.reading_status ?? 'not_started')
    setSaved(false)
  }
  async function refresh() {
    const result = await api.literature()
    setCatalog(result); onCatalog?.(result); setUncertain(false); setSaved(false)
    const link = result.works.flatMap(item => item.entries).find(item => item.id === entryId)
    if (link) select(link)
    else { setWorkId(null); setEntryId(null) }
  }
  async function save() {
    if (!entry) return
    try {
      const result = await api.readingProgress(entry.id, status, null)
      const next = { ...entry, user_state: result.literature_progress }
      const updated = { ...catalog, works: catalog.works.map(item => item.work_id === work?.work_id ? { ...item, entries: item.entries.map(link => ({ ...link, user_state: { ...result.literature_progress, literature_id: link.id } })) } : item) }; setCatalog(updated); onCatalog?.(updated)
      select(next); setSaved(true)
    } catch (failure) {
      // An unconfirmed write must be read back before another edit, never replayed automatically.
      if (!(failure instanceof ApiError) || !failure.status || failure.status >= 500) { setUncertain(true); onUncertain?.() }
      throw failure
    }
  }
  return <section className="page-width literature-page">
    <span className="eyebrow">ЧИТАТЬ И ОСМЫСЛЯТЬ</span><h1>Литература</h1>
    <p className="lead">Книги и другие материалы по темам и ваш прогресс чтения.</p>
    <p className="muted">Выберите тему или откройте рекомендуемую последовательность чтения.</p>
    <button className="text-button" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог и прогресс</button>
    {work && entry && <article className="panel literature-detail">
      <button className="text-button" disabled={busy || uncertain} onClick={backToList}>← К списку литературы</button>
      <header className="book-heading"><span className="book-kicker">{materialType(work.type)}</span><h2 ref={heading} tabIndex={-1}>{work.title}</h2><p className="book-authors">{work.authors.length ? work.authors.join(', ') : 'Автор не указан в источнике'}</p></header>
      <p className="eyebrow">{entry.reading_topics?.map(item => item.title).join(' · ') ?? entry.topic_title}</p>
      <p className="book-purpose">{entry.why_read}</p>
      <div className="book-metadata"><span>Значимость: {entry.importance ? `${importanceLabels[entry.importance]} · ${entry.importance_source ? importanceSources[entry.importance_source] : 'источник оценки не указан'}` : 'не определена'}</span><span>Год: {entry.year ?? 'не указан'}</span></div>
      <BookOffers links={work.access_links} />
      <BookSearch search={work.book_search} />
      <details className="source-details"><summary>Библиографическая запись</summary><blockquote>{entry.source.citation}</blockquote>
        {entry.metadata_warnings.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}
      </details>
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (!busy && !uncertain) void run(save) }}>
        <h3>Моё чтение</h3>
        <ChoiceMenu label="Статус чтения" value={status} disabled={busy || uncertain} onChange={value => { setStatus(value as ReadingStatus); setSaved(false) }} options={Object.entries(statuses).map(([value, label]) => ({ value, label }))} />
        {uncertain ? <p role="status" className="notice">Подтверждение не получено. Обновите каталог и прогресс перед следующим изменением.</p> : <button className="button primary" type="submit" disabled={busy}>Сохранить чтение</button>}
        {saved && <p role="status">Прогресс чтения сохранён.</p>}
      </form>
    </article>}<div hidden={Boolean(work && entry)}>
      <label className="field">Поиск по названию или автору<input type="search" value={query} onChange={event => { setQuery(event.target.value); route({ q: event.target.value }, true) }} placeholder="Название или автор" /></label>
      <div className="literature-filters"><ChoiceMenu label="Тема" value={topic} disabled={busy} onChange={value => { setTopic(value); route({ topic: value }, true) }} options={[{ value: '', label: 'Все темы' }, ...readingTopics.map(item => ({ value: item.topic_id, label: item.title }))]} />
        <ChoiceMenu label="Фильтр статуса чтения" value={statusFilter} disabled={busy} onChange={value => { setStatusFilter(value as ReadingStatus | ''); route({ status: value }, true) }} options={[{ value: '', label: 'Все статусы' }, ...Object.entries(statuses).map(([value, label]) => ({ value, label }))]} /></div>
      {!query.trim() && <><ReadingSummary showActions={!statusFilter} allItems={catalog.works.flatMap(work => work.entries.map(link => ({ ...link, work_id: work.work_id, title: work.title, authors: work.authors, type: work.type })))} items={summaryItems} busy={busy} onSelect={openEntry} />
      <ReadingOrder items={summaryItems} allItems={catalog.works.flatMap(item => item.entries.map(link => ({ ...link, work_id: item.work_id, title: item.title, authors: item.authors, type: item.type })))} busy={busy} onSelect={openEntry} /></>}
      <p className="muted" role="status">Работ по фильтру: {visible.length}</p>
      {visible.length ? <div className="literature-list">{visible.map(item => {
        const links = item.entries.filter(matches)
        return <article className="panel literature-card" key={item.work_id}><h2><button className="text-button literature-title" disabled={busy} id={`literature-${links[0].id}`} data-entry={links[0].id} onClick={() => openEntry(links[0].id)}>{item.title}</button></h2>
          <p>{item.authors.length ? item.authors.join(', ') : 'Автор не указан в источнике'}</p>
          <p className="muted">{statuses[links[0].user_state?.reading_status ?? 'not_started']}</p>
          <p className="muted">{links[0].reading_topics?.map(link => link.title).join(' · ')}</p>
        </article>
      })}</div> : <div className="panel empty-state"><h2>Список пока пуст</h2><p>Измените запрос или фильтры, либо обновите каталог.</p></div>}
    </div>
  </section>
}
