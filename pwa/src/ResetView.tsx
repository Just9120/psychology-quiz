import { useState } from 'react'
import { api } from './api'
import type { ResetPreview } from './types'

export function ResetView({ initial, busy, run, onCancel, onComplete }: {
  initial: ResetPreview; busy: boolean; run: (operation: () => Promise<void>) => Promise<void>
  onCancel: () => void; onComplete: () => Promise<void>
}) {
  const [topic, setTopic] = useState<string | null>(null)
  const [preview, setPreview] = useState<ResetPreview | null>(initial)
  const [topics, setTopics] = useState(initial.topics)
  const [confirmed, setConfirmed] = useState(false)

  async function refresh(selected = topic) {
    setConfirmed(false); setPreview(null)
    const current = await api.resetPreview(selected)
    setPreview(current); setTopics(current.topics)
  }
  async function confirm() {
    if (!confirmed || !preview) return
    const current = preview
    setConfirmed(false); setPreview(null)
    try { await api.resetLearning(current) }
    catch (failure) { setTopic(null); throw failure }
    await onComplete()
  }
  return <section className="page-width progress-page"><span className="eyebrow">УПРАВЛЕНИЕ ОБУЧЕНИЕМ</span><h1>Сброс прогресса квиза</h1>
    <p className="lead">Начните выбранную тему заново или очистите всю историю квизов в PWA и связанном Telegram.</p>
    <div className="panel practice-section">
      <label className="field">Что сбросить?<select value={topic === null ? 'all' : `topic:${topic}`} disabled={busy} onChange={event => { const value = event.target.value === 'all' ? null : event.target.value.slice(6); setTopic(value); void run(() => refresh(value)) }}><option value="all">Все темы квиза</option>{topics.map(value => <option key={value} value={`topic:${value}`}>{value}</option>)}</select></label>
      <p>Литература, личные заметки, аккаунт и связь с Telegram сохранятся. Этот сброс относится к квизу вопросов.</p>
      {preview ? <>
        <h2>Предварительный просмотр</h2><p>Будет удалено ответов: <strong>{preview.answers}</strong>. Затронуто попыток: <strong>{preview.attempts}</strong>.</p>
        {preview.scope === 'topic' && <p className="notice">Тема определяется по сохранённой редакции вопроса. Ответы других тем в смешанных попытках останутся в истории.</p>}
        {preview.active_attempts > 0 && <p className="notice warning-text">Затронутые незавершённые попытки будут прекращены: {preview.active_attempts}.</p>}
        {preview.attempts > 0 ? <label className="reset-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} /><span>Понимаю, что выбранные ответы и ошибки будут удалены без возможности отмены.</span></label> : <p role="status">В выбранном разделе нет попыток для сброса.</p>}
      </> : <p role="status">Загрузите актуальный предварительный просмотр перед подтверждением.</p>}
      <div className="button-row"><button className="button secondary" disabled={busy} onClick={() => void run(() => refresh())}>Обновить просмотр</button><button className="button danger" disabled={busy || !confirmed || !preview?.attempts} onClick={() => void run(confirm)}>Подтвердить сброс</button><button className="button secondary" disabled={busy} onClick={onCancel}>Отмена</button></div>
    </div>
  </section>
}
