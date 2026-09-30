import type { OwnerStats } from './types'

const periods: { id: OwnerStats['period']; label: string }[] = [
  { id: '24h', label: '24 часа' },
  { id: '7d', label: '7 дней' },
  { id: '30d', label: '30 дней' },
]

export function OwnerStatsView({ data, busy, onPeriod }: {
  data: OwnerStats
  busy: boolean
  onPeriod: (period: OwnerStats['period']) => void
}) {
  return <section className="page-width progress-page">
    <div className="practice-heading"><div><span className="eyebrow">ОБЗОР ОБУЧЕНИЯ</span><h1>Статистика</h1></div></div>
    <p className="lead">Сводные показатели без имён и результатов отдельных пользователей.</p>
    <div className="owner-stats-periods" role="group" aria-label="Период статистики">
      {periods.map(item => <button key={item.id} type="button" className={data.period === item.id ? 'button primary' : 'button secondary'}
        aria-pressed={data.period === item.id} disabled={busy} onClick={() => onPeriod(item.id)}>{item.label}</button>)}
    </div>
    <div className="practice-metrics">
      <div className="panel"><span>Активных пользователей</span><strong>{data.active_users}</strong></div>
      <div className="panel"><span>Квизы</span><strong>{data.quiz_completed}</strong><small>Завершено; начато {data.quiz_started}</small></div>
      <div className="panel"><span>Ответы на вопросы</span><strong>{data.quiz_answers}</strong></div>
      <div className="panel"><span>Глоссарий</span><strong>{data.glossary_completed}</strong><small>Завершено; начато {data.glossary_started}</small></div>
      <div className="panel"><span>Книжные отметки</span><strong>{data.reading_items_updated}</strong><small>Обновлено за выбранный период</small></div>
    </div>
    <p className="hint">Активность считается по квизам, глоссарию, ответам при повторении и книжным отметкам. Повторные действия одного человека не увеличивают число активных пользователей.</p>
  </section>
}
