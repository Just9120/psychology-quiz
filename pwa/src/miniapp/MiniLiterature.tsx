import { compareBooks, LiteratureControls, LiteratureEmpty, readingStatuses as labels, type LiteratureSort } from '../LiteratureControls'
import { BookOffers } from '../BookOffers'
import { ChoiceMenu } from '../ChoiceMenu'
import { useLayoutEffect, useRef, useState } from 'react'
import { materialType } from '../materialType'
import { ReadingOrder } from '../ReadingOrder'
import { ReadingSummary } from '../ReadingSummary'
import { BookSearch } from '../BookSearch'
import { StudyFilters } from '../StudyFilters'
import { emptyStudyScope, literaturePaths, literatureSubjectLabel, matchesStudy, studyChoices } from '../studyScope'
import type { ReadingStatus } from '../types'
import { miniApi, type MiniLiteratureItem, type MiniLiteratureTopic } from './api'

const importanceLabels = { basic: 'Базовая', important: 'Важная', additional: 'Дополнительная', advanced: 'Углублённая' } as const
const importanceSources = { teacher: 'приоритет преподавателя', agent: 'рекомендация агента' } as const

export function MiniLiterature({ initial, topics, studyTopics = [], busy, run, onItems, onInvalidate }: {
  initial: MiniLiteratureItem[]; topics: MiniLiteratureTopic[]; busy: boolean
  studyTopics?: MiniLiteratureTopic[]
  run: (action: () => Promise<void>) => Promise<void>
  onItems?: (items: MiniLiteratureItem[], disciplines?: MiniLiteratureTopic[]) => void
  onInvalidate?: () => void
}) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<LiteratureSort>('catalog')
  const search = useRef<HTMLInputElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const returnTo = useRef<{ y: number; id: string; element: HTMLElement | null } | null>(null)
  const [items, setItems] = useState(initial)
  const [disciplines, setDisciplines] = useState(studyTopics.length ? studyTopics : topics)
  const [topic, setTopic] = useState('')
  const [studyScope, setStudyScope] = useState(emptyStudyScope)
  const [statusFilter, setStatusFilter] = useState<ReadingStatus | ''>('')
  const [selected, setSelected] = useState<string | null>(null)
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const item = items.find(entry => entry.id === selected)
  const readingTopics = [...new Map(items.flatMap(entry => entry.reading_topics ?? []).map(link => [link.id, { topic_id: link.id, title: link.title }])).values()]
  const navigationTopics = topics.some(entry => entry.topic_id.startsWith('reading_')) ? topics : readingTopics.length ? readingTopics : topics
  const study = studyChoices(items.flatMap(entry => literaturePaths(entry, disciplines)), studyScope)
  const scoped = items.filter(entry => matchesStudy(literaturePaths(entry, disciplines), study.scope)
    && (!topic || (entry.reading_topics ? entry.reading_topics.some(link => link.id === topic) : entry.topic_id === topic)))
  const visibleWorks = new Map<string, MiniLiteratureItem>()
  for (const entry of scoped) {
    if (statusFilter && (entry.user_state?.reading_status ?? 'not_started') !== statusFilter) continue
    if (![entry.title ?? '', ...(entry.authors ?? [])].join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'))) continue
    const key = entry.work_id ?? entry.id
    if (!visibleWorks.has(key)) visibleWorks.set(key, entry)
  }
  const visible = [...visibleWorks.values()].sort((a, b) => compareBooks(sort, { title: a.title, status: a.user_state?.reading_status ?? 'not_started' }, { title: b.title, status: b.user_state?.reading_status ?? 'not_started' }))
  const activeFilters = [
    study.modules.find(item => item.value === study.scope.module)?.label,
    study.disciplines.find(item => item.value === study.scope.discipline)?.label,
    study.topics.find(item => item.value === study.scope.topic)?.label,
    navigationTopics.find(item => item.topic_id === topic)?.title,
    statusFilter ? labels[statusFilter] : undefined,
  ].filter((label): label is string => Boolean(label))
  function resetFilters() {
    setQuery(''); setTopic(''); setStudyScope(emptyStudyScope); setStatusFilter('')
    search.current?.focus()
  }
  useLayoutEffect(() => {
    if (selected) { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView?.({ block: 'start' }) }
    else if (returnTo.current) { if (returnTo.current.element?.isConnected) returnTo.current.element.focus({ preventScroll: true }); else document.getElementById(`mini-literature-${returnTo.current.id}`)?.focus({ preventScroll: true }); window.scrollTo?.(0, returnTo.current.y) }
  }, [selected])
  function choose(entry: MiniLiteratureItem) {
    if (!selected) returnTo.current = { y: window.scrollY, id: entry.id, element: document.activeElement as HTMLElement }
    setSelected(entry.id); setStatus(entry.user_state?.reading_status ?? 'not_started')
    setUncertain(false); setSaved(false)
  }
  async function refresh() {
    const result = await miniApi.literatureItems()
    if (result.literature_topics) setDisciplines(result.literature_topics)
    setItems(result.literature_items); onItems?.(result.literature_items, result.literature_topics); setUncertain(false)
    const updated = result.literature_items.find(entry => entry.id === selected)
    if (updated) choose(updated)
  }
  async function save() {
    if (!item) return
    try {
      const result = await miniApi.literatureProgress(item.id, status, null)
      const updated = items.map(entry => (item.work_id ? entry.work_id === item.work_id : entry.id === item.id)
        ? { ...entry, user_state: { ...result.literature_progress, literature_id: entry.id } } : entry)
      setItems(updated); onItems?.(updated); setSaved(true)
    } catch (failure) { setUncertain(true); onInvalidate?.(); throw failure }
  }
  return <section className="page-width literature-page"><span className="eyebrow">СПИСКИ ЛИТЕРАТУРЫ</span><h1>Литература</h1>
    <p className="lead">Книги и другие материалы по темам и ваши личные отметки чтения.</p>
    <button className="button secondary" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог</button>
    {item && <article className="panel literature-detail"><button className="text-button" disabled={busy || uncertain} onClick={() => setSelected(null)}>← К списку</button>
      <header className="book-heading"><span className="book-kicker">{materialType(item.type)}</span><h2 ref={heading} tabIndex={-1}>{item.title}</h2><p className="book-authors">{item.authors?.join(', ') || 'Автор не указан'} · {item.year ?? 'год не указан'}</p></header>
      <p className="eyebrow">{literatureSubjectLabel(item, study.scope.topic || topic)}</p>
      <p className="book-purpose">{item.why_read}</p>
      <p className="book-metadata">Значимость: {item.importance ? `${importanceLabels[item.importance]} · ${item.importance_source ? importanceSources[item.importance_source] : 'источник оценки не указан'}` : 'не определена'}</p>
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (!uncertain) void run(save) }}>
        <h3>Моё чтение</h3><ChoiceMenu label="Статус" value={status} disabled={busy || uncertain} onChange={value => { setStatus(value as ReadingStatus); setSaved(false) }} options={Object.entries(labels).map(([value, label]) => ({ value, label }))} />
        {uncertain && <p role="status">Сохранение не подтверждено. Сначала обновите каталог.</p>}
        <button className="button primary" type="submit" disabled={busy || uncertain}>Сохранить чтение</button>{saved && <p role="status">Отметка сохранена.</p>}
      </form>
      <BookOffers links={item.access_links} description="Доступ и совпадение издания уточняются у провайдера." />
      {item.book_search && <details className="book-search-disclosure"><summary><span aria-hidden="true">⋮</span> Другие способы найти книгу</summary>
        <BookSearch search={item.book_search} />
      </details>}
      {(item.source?.citation || item.metadata_warnings?.length) && <details className="source-details"><summary>Библиографическая запись</summary>
        {item.source?.citation && <blockquote>{item.source.citation}</blockquote>}
        {item.metadata_warnings?.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}
      </details>}
</article>}<div hidden={Boolean(item)}>
      <LiteratureControls search={search} query={query} onQuery={setQuery} filters={activeFilters} onReset={resetFilters} sort={sort} onSort={setSort} busy={busy}>
      <StudyFilters choices={study} busy={busy} topicLabel="Предметная тема" onChange={setStudyScope} />
      <div className="literature-filters"><ChoiceMenu label="Направление чтения" value={topic} disabled={busy} onChange={setTopic} options={[{ value: '', label: 'Все направления' }, ...navigationTopics.map(entry => ({ value: entry.topic_id, label: entry.title }))]} />
        <ChoiceMenu label="Фильтр статуса чтения" value={statusFilter} disabled={busy} onChange={value => setStatusFilter(value as ReadingStatus | '')} options={[{ value: '', label: 'Все статусы' }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))]} /></div>
      </LiteratureControls>
      {!query.trim() && <><details className="reading-progress-disclosure"><summary>Прогресс чтения</summary><ReadingSummary showActions={!statusFilter} allItems={items} items={scoped} busy={busy} onSelect={id => choose(items.find(entry => entry.id === id)!)} />
      </details><ReadingOrder items={scoped} allItems={items} busy={busy} onSelect={id => choose(items.find(entry => entry.id === id)!)} /></>}
      <p className="muted" role="status">Работ по фильтру: {visible.length}</p>
      {visible.length ? <div className="literature-list">{visible.map(entry => <article className="panel literature-card" key={entry.id}><h2><button className="text-button literature-title" id={`mini-literature-${entry.id}`} disabled={busy} onClick={() => choose(entry)}>{entry.title}</button></h2><p>{entry.authors?.join(', ') || 'Автор не указан'}</p><span className="status-chip" data-status={entry.user_state?.reading_status ?? 'not_started'}>{labels[entry.user_state?.reading_status ?? 'not_started']}</span></article>)}</div> : <LiteratureEmpty filtered={Boolean(query.trim() || activeFilters.length)} onReset={resetFilters} />}
    </div>
  </section>
}
