import { BookOffers } from './BookOffers'
import { useState } from 'react'
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

export function LiteratureView({ initial, busy, run }: { initial: LiteratureCatalog; busy: boolean; run: (operation: () => Promise<void>) => Promise<void> }) {
  const [catalog, setCatalog] = useState(initial)
  const [topic, setTopic] = useState('')
  const [statusFilter, setStatusFilter] = useState<ReadingStatus | ''>('')
  const [workId, setWorkId] = useState<string | null>(null)
  const [entryId, setEntryId] = useState<string | null>(null)
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const work = catalog.works.find(item => item.work_id === workId)
  const entry = work?.entries.find(item => item.id === entryId)
  const readingTopics = catalog.reading_topics ?? catalog.topics
  const inScope = (link: LiteratureEntry) => !topic || (link.reading_topics
    ? link.reading_topics.some(item => item.id === topic) : link.topic_id === topic)
  const matches = (link: LiteratureEntry) => inScope(link)
    && (!statusFilter || (link.user_state?.reading_status ?? 'not_started') === statusFilter)
  const visible = catalog.works.filter(item => item.entries.some(matches))
  const summaryItems = catalog.works.flatMap(item => item.entries.filter(inScope).map(link => ({ ...link, work_id: item.work_id, title: item.title })))

  function openEntry(id: string) {
    const selectedWork = catalog.works.find(item => item.entries.some(link => link.id === id))
    if (selectedWork) { setWorkId(selectedWork.work_id); select(selectedWork.entries.find(link => link.id === id)!) }
  }
  function select(link: LiteratureEntry) {
    setEntryId(link.id); setStatus(link.user_state?.reading_status ?? 'not_started')
    setSaved(false)
  }
  async function refresh() {
    const result = await api.literature()
    setCatalog(result); setUncertain(false); setSaved(false)
    const link = result.works.flatMap(item => item.entries).find(item => item.id === entryId)
    if (link) select(link)
    else { setWorkId(null); setEntryId(null) }
  }
  async function save() {
    if (!entry) return
    try {
      const result = await api.readingProgress(entry.id, status, null)
      const next = { ...entry, user_state: result.literature_progress }
      setCatalog(current => ({ ...current, works: current.works.map(item => item.work_id === work?.work_id ? { ...item, entries: item.entries.map(link => ({ ...link, user_state: { ...result.literature_progress, literature_id: link.id } })) } : item) }))
      select(next); setSaved(true)
    } catch (failure) {
      // An unconfirmed write must be read back before another edit, never replayed automatically.
      if (!(failure instanceof ApiError) || !failure.status || failure.status >= 500) setUncertain(true)
      throw failure
    }
  }
  return <section className="page-width literature-page">
    <span className="eyebrow">ЧИТАТЬ И ОСМЫСЛЯТЬ</span><h1>Литература</h1>
    <p className="lead">Книги по темам и ваш прогресс чтения.</p>
    <p className="muted">Выберите тему или откройте рекомендуемую последовательность чтения.</p>
    <button className="text-button" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог и прогресс</button>
    {work && entry ? <article className="panel literature-detail">
      <button className="text-button" disabled={busy || uncertain} onClick={() => { setWorkId(null); setSaved(false) }}>← К списку литературы</button>
      <h2>{work.title}</h2><p>{work.authors.length ? work.authors.join(', ') : 'Автор не указан в источнике'}</p>
      <p className="eyebrow">{entry.reading_topics?.map(item => item.title).join(' · ') ?? entry.topic_title}</p>
      <p>{entry.why_read}</p>
      <p>Значимость: {entry.importance ? `${importanceLabels[entry.importance]} · ${entry.importance_source ? importanceSources[entry.importance_source] : 'источник оценки не указан'}` : 'не определена'}</p>
      <p>Год: {entry.year ?? 'не указан'}</p>
      <BookOffers links={work.access_links} />
      <BookSearch search={work.book_search} />
      <details className="source-details"><summary>Библиографическая запись</summary><blockquote>{entry.source.citation}</blockquote>
        {entry.metadata_warnings.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}
      </details>
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (!busy && !uncertain) void run(save) }}>
        <h3>Моё чтение</h3>
        <label className="field">Статус чтения<select value={status} disabled={busy || uncertain} onChange={event => { setStatus(event.target.value as ReadingStatus); setSaved(false) }}>
          {Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        {uncertain ? <p role="status" className="notice">Подтверждение не получено. Обновите каталог и прогресс перед следующим изменением.</p> : <button className="button primary" type="submit" disabled={busy}>Сохранить чтение</button>}
        {saved && <p role="status">Прогресс чтения сохранён.</p>}
      </form>
    </article> : <>
      <label className="field literature-filter">Тема<select aria-label="Тема" value={topic} disabled={busy} onChange={event => setTopic(event.target.value)}><option value="">Все темы</option>{readingTopics.map(item => <option key={item.topic_id} value={item.topic_id}>{item.title}</option>)}</select></label>
      <label className="field literature-filter">Фильтр статуса чтения<select value={statusFilter} disabled={busy} onChange={event => setStatusFilter(event.target.value as ReadingStatus | '')}><option value="">Все статусы</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <ReadingSummary showActions={!statusFilter} allItems={catalog.works.flatMap(work => work.entries)} items={summaryItems} busy={busy} onSelect={openEntry} />
      <ReadingOrder items={summaryItems} allItems={catalog.works.flatMap(item => item.entries.map(link => ({ ...link, work_id: item.work_id, title: item.title })))} busy={busy} onSelect={openEntry} />
      <p className="muted" role="status">Работ по фильтру: {visible.length}</p>
      {visible.length ? <div className="literature-list">{visible.map(item => {
        const links = item.entries.filter(matches)
        return <article className="panel literature-card" key={item.work_id}><h2><button className="text-button literature-title" disabled={busy} onClick={() => { setWorkId(item.work_id); select(links[0]) }}>{item.title}</button></h2>
          <p>{item.authors.length ? item.authors.join(', ') : 'Автор не указан в источнике'}</p>
          <p className="muted">{statuses[links[0].user_state?.reading_status ?? 'not_started']}</p>
          <p className="muted">{links[0].reading_topics?.map(link => link.title).join(' · ')}</p>
        </article>
      })}</div> : <div className="panel empty-state"><h2>Список пока пуст</h2><p>Попробуйте выбрать другую тему или обновить каталог.</p></div>}
    </>}
  </section>
}
