import { useState } from 'react'
import { ReadingSummary } from '../ReadingSummary'
import type { ReadingStatus } from '../types'
import { miniApi, type MiniLiteratureItem, type MiniLiteratureTopic } from './api'

const labels: Record<ReadingStatus, string> = { not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', deferred: 'Отложено' }
const importanceLabels = { basic: 'Базовая', important: 'Важная', additional: 'Дополнительная', advanced: 'Углублённая' } as const
const importanceSources = { teacher: 'приоритет преподавателя', agent: 'рекомендация агента' } as const

export function MiniLiterature({ initial, topics, busy, run }: {
  initial: MiniLiteratureItem[]; topics: MiniLiteratureTopic[]; busy: boolean
  run: (action: () => Promise<void>) => Promise<void>
}) {
  const [items, setItems] = useState(initial)
  const [topic, setTopic] = useState('')
  const [module, setModule] = useState('')
  const [statusFilter, setStatusFilter] = useState<ReadingStatus | ''>('')
  const [selected, setSelected] = useState<string | null>(null)
  const [status, setStatus] = useState<ReadingStatus>('not_started')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const item = items.find(entry => entry.id === selected)
  const modules = [...new Set(topics.map(entry => entry.module).filter((value): value is string => !!value))]
  const scoped = items.filter(entry => (!topic || entry.topic_id === topic) && (!module || topics.some(link => link.topic_id === entry.topic_id && link.module === module)))
  const visible = items.filter(entry => (!topic || entry.topic_id === topic)
    && (!module || topics.some(link => link.topic_id === entry.topic_id && link.module === module))
    && (!statusFilter || (entry.user_state?.reading_status ?? 'not_started') === statusFilter))
  function choose(entry: MiniLiteratureItem) {
    setSelected(entry.id); setStatus(entry.user_state?.reading_status ?? 'not_started')
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
      await miniApi.literatureProgress(item.id, status, null)
      await refresh(); setSaved(true)
    } catch (failure) { setUncertain(true); throw failure }
  }
  return <section className="page-width literature-page"><span className="eyebrow">СПИСКИ ЛИТЕРАТУРЫ</span><h1>Литература</h1>
    <p className="lead">Учебные списки и ваши личные отметки чтения.</p>
    <p className="muted">Библиографические записи проверены; содержание полных текстов не подтверждено.</p>
    <button className="button secondary" disabled={busy} onClick={() => void run(refresh)}>Обновить каталог</button>
    {item ? <article className="panel literature-detail"><button className="text-button" onClick={() => setSelected(null)}>← К списку</button>
      <h2>{item.title}</h2><p>{item.authors?.join(', ') || 'Автор не указан'} · {item.year ?? 'год не указан'}</p>
      <p>Значимость: {item.importance ? `${importanceLabels[item.importance]} · ${item.importance_source ? importanceSources[item.importance_source] : 'источник оценки не указан'}` : 'не определена'}</p>
      {item.access_links?.length ? <div className="literature-access"><h3>Внешние версии</h3><p className="muted">Доступ и совпадение издания уточняются у провайдера.</p>
        {item.access_links.map(link => <p key={link.url}><a href={link.url} target="_blank" rel="noopener noreferrer">{link.format === 'text' ? 'Текст' : 'Аудио'} · {link.provider}</a></p>)}
      </div> : <p className="muted">Проверенных ссылок на текст или аудио пока нет.</p>}
      <p>{item.why_read}</p>{item.source?.citation && <details><summary>Библиографическая запись</summary><blockquote>{item.source.citation}</blockquote></details>}
      <form className="reading-form" onSubmit={event => { event.preventDefault(); if (!uncertain) void run(save) }}>
        <label className="field">Статус<select value={status} disabled={busy || uncertain} onChange={event => { setStatus(event.target.value as ReadingStatus); setSaved(false) }}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {uncertain && <p role="status">Сохранение не подтверждено. Сначала обновите каталог.</p>}
        <button className="button primary" type="submit" disabled={busy || uncertain}>Сохранить чтение</button>{saved && <p role="status">Отметка сохранена.</p>}
      </form></article> : <>
      <label className="field">Модуль литературы<select value={module} disabled={busy} onChange={event => { setModule(event.target.value); setTopic('') }}><option value="">Все модули</option>{modules.map(value => <option key={value} value={value}>{value.replace('module', 'Модуль ')}</option>)}</select></label>
      <label className="field">Тема<select value={topic} disabled={busy} onChange={event => setTopic(event.target.value)}><option value="">Все темы</option>{topics.filter(entry => !module || entry.module === module).map(entry => <option key={entry.topic_id} value={entry.topic_id}>{entry.title}</option>)}</select></label>
      <label className="field">Фильтр статуса чтения<select value={statusFilter} disabled={busy} onChange={event => setStatusFilter(event.target.value as ReadingStatus | '')}><option value="">Все статусы</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <ReadingSummary allItems={items} items={scoped} busy={busy} onSelect={id => choose(items.find(entry => entry.id === id)!)} />
      {visible.length ? <div className="literature-list">{visible.map(entry => <article className="panel literature-card" key={entry.id}><h2><button className="text-button literature-title" onClick={() => choose(entry)}>{entry.title}</button></h2><p>{entry.authors?.join(', ') || 'Автор не указан'}</p><p className="muted">{labels[entry.user_state?.reading_status ?? 'not_started']}</p></article>)}</div> : <p role="status">По этой теме список пока пуст.</p>}
    </>}
  </section>
}
