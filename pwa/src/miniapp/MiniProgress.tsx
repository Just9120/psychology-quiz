import type { ProgressOverview } from '../types'

export function MiniProgress({ data, busy, onRefresh }: { data: ProgressOverview; busy: boolean; onRefresh: () => void }) {
  return <section className="page-width progress-page"><span className="eyebrow">ЛИЧНЫЕ РЕЗУЛЬТАТЫ</span><h1>Мой прогресс</h1>
    <button className="button secondary" disabled={busy} onClick={onRefresh}>Обновить</button>
    <div className="panel practice-section"><h2>Всего</h2><p>Завершено попыток: {data.summary.finished} · Ответов: {data.summary.answered} · Верных: {data.summary.correct}</p>
      <p className="hint">Точность по сохранённым ответам: {data.summary.accuracy == null ? 'пока нет данных' : `${data.summary.accuracy}%`}. Это не оценка освоения.</p></div>
    <section className="panel practice-section"><h2>Темы</h2>{data.topics.length ? <ul>{data.topics.map(item => <li key={item.topic}>{item.topic}: {item.correct} из {item.answered} верных</li>)}</ul> : <p role="status">Истории ответов пока нет. Начните квиз.</p>}</section>
    {data.curriculum && <section className="panel practice-section"><h2>Дисциплины</h2>{data.curriculum.disciplines.length ? <ul>{data.curriculum.disciplines.map(item => <li key={item.scope}>{item.module ? `${item.module.replace(/^module/, 'Модуль ')} · ` : ''}{item.title}: {item.correct} из {item.answered} верных</li>)}</ul> : <p>Пока нет подтверждённой привязки истории к дисциплинам.</p>}</section>}
  </section>
}
