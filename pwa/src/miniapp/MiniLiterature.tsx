import { useState } from 'react'
import type { ReadingStatus } from '../types'
import { readingChecklistLabel, suggestedReadingOrder } from '../readingPlan'
import { miniApi, type MiniLiteratureItem, type MiniLiteratureTopic } from './api'

const labels: Record<ReadingStatus, string> = { not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', revisit: 'Вернуться', skipped: 'Пропущено' }

export function MiniLiterature({ initial, topics, busy, run }: {
  initial: MiniLiteratureItem[]; topics: MiniLiteratureTopic[]; busy: boolean
  run: (action: () => Promise<void>) => Promise<void>
}) {
  const [items, setItems] = useState(initial)
  const [topic, setTopic] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [percent, setPercent] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const item = items.find(entry => entry.id === selected)
  const visible = topic ? suggestedReadingOrder(items.filter(entry => entry.topic_id === topic)) : items
  function choose(entry: MiniLiteratureItem) {
    setSelected(entry.id); setStatus(entry.user_state?.reading_status ?? 'not_started')
    setPercent(entry.user_state?.progress_percent == null ? '' : String(entry.user_state.progress_percent))
    setUncertain(false); setSaved(false)
  }
  async function refresh() {
    const result = await miniApi.literatureItems()
    setItems(result.literature_items); setUncertain(false)
    const updated = result.literature_items.find(entry => entry.id === selected)
    if (updated) choose(updated)
  }
  async function save() {
    if (!item) return
    try {
      await miniApi.literatureProgress(item.id, status, status === 'read' ? 100 : status === 'not_started' ? 0 : percent === '' ? null : Number(percent))
      await refresh(); setSaved(true)
    } catch (failure) { setUncertain(true); throw failure }
  }
  const valid = status === 'read' || status === 'not_started' || percent === '' || (/^\d{1,3}$/.test(percent) && Number(percent) <= 100)
  return <section className="page-width literature-page"><span className="eyebrow">СПИСКИ ЛИТЕРАТУРЫ</span><h1>Литература</h1>
    <p className="lead">Учебные списки и ваши личные отметки чтения.</p>
    <p className="muted">Библиографические записи проверены; содержание полных текстов не подтверждено.</p>
    <button className="button secondary" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог</button>
    {item ? <article className="panel literature-detail"><button className="text-button" onClick={() => setSelected(null)}>← К списку</button>
      <h2>{item.title}</h2><p>{item.authors?.join(', ') || 'Автор не указан'} · {item.year ?? 'год не указан'}</p>
      <p className="muted">Приоритет преподавателя: {item.priority || 'не указан в доступном источнике'}.</p>
      <p>{item.why_read}</p>{item.source?.citation && <details><summary>Библиографическая запись</summary><blockquote>{item.source.citation}</blockquote></details>}
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (valid && !uncertain) void run(save) }}>
        <label className="field">Статус<select value={status} disabled={busy || uncertain} onChange={event => { setStatus(event.target.value as ReadingStatus); setSaved(false) }}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field">Прочитано, %<input type="number" min="0" max="100" step="1" disabled={busy || uncertain || status === 'read' || status === 'not_started'} value={status === 'read' ? '100' : status === 'not_started' ? '0' : percent} onChange={event => { setPercent(event.target.value); setSaved(false) }} /></label>
        {uncertain && <p role="status">Сохранение не подтверждено. Сначала обновите каталог.</p>}
        <button className="button primary" type="submit" disabled={busy || uncertain || !valid}>Сохранить чтение</button>{saved && <p role="status">Отметка сохранена.</p>}
      </form></article> : <>
      <label className="field">Тема<select value={topic} onChange={event => setTopic(event.target.value)}><option value="">Все темы</option>{topics.map(entry => <option key={entry.topic_id} value={entry.topic_id}>{entry.title}</option>)}</select></label>
      {topic && <p className="muted">Личный чек-лист в предложенном приложением порядке: сначала незавершённое по учебному списку, затем прочитанное. Это не приоритет преподавателя.</p>}
      {visible.length ? <div className="literature-list">{visible.map(entry => <article className="panel literature-card" key={entry.id}><h2><button className="text-button literature-title" onClick={() => choose(entry)}>{entry.title}</button></h2><p>{entry.authors?.join(', ') || 'Автор не указан'}</p><p className="muted">{labels[entry.user_state?.reading_status ?? 'not_started']}{topic ? ` · ${readingChecklistLabel(entry)}` : ''}{entry.priority ? ` · Приоритет преподавателя: ${entry.priority}` : ''}</p></article>)}</div> : <p role="status">По этой теме список пока пуст.</p>}
    </>}
  </section>
}
