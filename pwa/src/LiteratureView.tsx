import { useState } from 'react'
import { api, ApiError } from './api'
import type { LiteratureCatalog, LiteratureEntry, ReadingStatus } from './types'

const statuses: Record<ReadingStatus, string> = {
  not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', revisit: 'Вернуться', skipped: 'Пропущено',
}

export function LiteratureView({ initial, busy, run }: { initial: LiteratureCatalog; busy: boolean; run: (operation: () => Promise<void>) => Promise<void> }) {
  const [catalog, setCatalog] = useState(initial)
  const [topic, setTopic] = useState('')
  const [workId, setWorkId] = useState<string | null>(null)
  const [entryId, setEntryId] = useState<string | null>(null)
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [percent, setPercent] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const work = catalog.works.find(item => item.work_id === workId)
  const entry = work?.entries.find(item => item.id === entryId)
  const visible = catalog.works.filter(item => !topic || item.entries.some(link => link.topic_id === topic))

  function select(link: LiteratureEntry) {
    setEntryId(link.id); setStatus(link.user_state?.reading_status ?? 'not_started')
    setPercent(link.user_state?.progress_percent == null ? '' : String(link.user_state.progress_percent))
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
      const result = await api.readingProgress(entry.id, status, status === 'read' ? 100 : status === 'not_started' ? 0 : percent === '' ? null : Number(percent))
      const next = { ...entry, user_state: result.literature_progress }
      setCatalog(current => ({ ...current, works: current.works.map(item => ({ ...item, entries: item.entries.map(link => link.id === entry.id ? next : link) })) }))
      select(next); setSaved(true)
    } catch (failure) {
      // An unconfirmed write must be read back before another edit, never replayed automatically.
      if (!(failure instanceof ApiError) || !failure.status || failure.status >= 500) setUncertain(true)
      throw failure
    }
  }
  const validPercent = status === 'read' || status === 'not_started' || percent === '' || (/^\d{1,3}$/.test(percent) && Number(percent) <= 100)
  return <section className="page-width literature-page">
    <span className="eyebrow">ЧИТАТЬ И ОСМЫСЛЯТЬ</span><h1>Литература</h1>
    <p className="lead">Учебные списки и ваш прогресс чтения.</p>
    <p className="muted">Проверены библиографические записи. Доступность полных текстов и содержание работ пока не проверены.</p>
    <button className="text-button" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог и прогресс</button>
    {work && entry ? <article className="panel literature-detail">
      <button className="text-button" disabled={busy || uncertain} onClick={() => { setWorkId(null); setSaved(false) }}>← К списку литературы</button>
      <h2>{work.title}</h2><p>{work.authors.length ? work.authors.join(', ') : 'Автор не указан в источнике'}</p>
      <label className="field">Учебный список<select value={entry.id} disabled={busy || uncertain} onChange={event => select(work.entries.find(link => link.id === event.target.value)!)}>
        {work.entries.map(link => <option key={link.id} value={link.id}>{link.topic_title} · {link.source.title}</option>)}
      </select></label>
      {work.entries.length > 1 && <p className="muted">Эта работа встречается в нескольких списках. Отметки чтения сохраняются отдельно для выбранного списка.</p>}
      <p className="eyebrow">{entry.module.replace('module', 'Модуль ')} · {entry.topic_title}</p>
      <p>Год: {entry.year ?? 'не указан'}</p>
      <details className="source-details"><summary>Источник и библиографическая запись</summary><p>{entry.source.title}</p><p>{entry.source.locator}</p><blockquote>{entry.source.citation}</blockquote>
        {entry.metadata_warnings.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}
      </details>
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (validPercent && !busy && !uncertain) void run(save) }}>
        <h3>Моё чтение</h3>
        <label className="field">Статус чтения<select value={status} disabled={busy || uncertain} onChange={event => { setStatus(event.target.value as ReadingStatus); setSaved(false) }}>
          {Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label className="field">Прочитано, %<input type="number" min="0" max="100" step="1" value={status === 'read' ? '100' : status === 'not_started' ? '0' : percent} disabled={busy || uncertain || status === 'read' || status === 'not_started'} onChange={event => { setPercent(event.target.value); setSaved(false) }} /></label>
        {uncertain ? <p role="status" className="notice">Подтверждение не получено. Обновите каталог и прогресс перед следующим изменением.</p> : <button className="button primary" type="submit" disabled={busy || !validPercent}>Сохранить чтение</button>}
        {saved && <p role="status">Прогресс чтения сохранён.</p>}
      </form>
    </article> : <>
      <label className="field literature-filter">Тема литературы<select value={topic} disabled={busy} onChange={event => setTopic(event.target.value)}><option value="">Все темы</option>{catalog.topics.map(item => <option key={item.topic_id} value={item.topic_id}>{item.title}</option>)}</select></label>
      <p className="muted" role="status">Работ: {visible.length}</p>
      {visible.length ? <div className="literature-list">{visible.map(item => {
        const links = item.entries.filter(link => !topic || link.topic_id === topic)
        return <article className="panel literature-card" key={item.work_id}><h2><button className="text-button literature-title" disabled={busy} onClick={() => { setWorkId(item.work_id); select(links[0]) }}>{item.title}</button></h2>
          <p>{item.authors.length ? item.authors.join(', ') : 'Автор не указан в источнике'}</p>
          {links.map(link => <p className="muted reading-association" key={link.id}>{link.topic_title} · {statuses[link.user_state?.reading_status ?? 'not_started']}{link.user_state?.progress_percent != null ? ` · ${link.user_state.progress_percent}%` : ''}</p>)}
        </article>
      })}</div> : <div className="panel empty-state"><h2>Список пока пуст</h2><p>Попробуйте выбрать другую тему или обновить каталог.</p></div>}
    </>}
  </section>
}
