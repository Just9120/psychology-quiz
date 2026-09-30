import { useState } from 'react'
import type { HomeworkAssignment, HomeworkCatalog } from './types'

export function HomeworkView({ catalog, busy, confirmId, onStart, onConfirm, onResume, onRefresh }: {
  catalog: HomeworkCatalog
  busy: boolean
  confirmId: string | null
  onStart: (id: string) => void
  onConfirm: (id: string) => void
  onResume: (item: HomeworkAssignment) => void
  onRefresh: () => void
}) {
  const [module, setModule] = useState('')
  const [discipline, setDiscipline] = useState('')
  const [topic, setTopic] = useState('')
  const unique = (values: string[]) => [...new Set(values)].sort((a, b) => a.localeCompare(b, 'ru'))
  const modules = unique(catalog.assignments.map(item => item.module))
  const activeModule = modules.includes(module) ? module : ''
  const inModule = catalog.assignments.filter(item => !activeModule || item.module === activeModule)
  const disciplines = unique(inModule.map(item => item.discipline))
  const activeDiscipline = disciplines.includes(discipline) ? discipline : ''
  const inDiscipline = inModule.filter(item => !activeDiscipline || item.discipline === activeDiscipline)
  const topics = unique(inDiscipline.map(item => item.topic))
  const activeTopic = topics.includes(topic) ? topic : ''
  const assignments = inDiscipline.filter(item => !activeTopic || item.topic === activeTopic)

  return <section className="page-width homework-page">
    <span className="eyebrow">МОЁ ОБУЧЕНИЕ</span><h1>Домашние задания</h1>
    <p className="lead">Здесь проверяются знания по материалам заданий. Тест не подтверждает выполнение эссе, наблюдения или практического упражнения.</p>
    <p className="muted">Задание считается выполненным при 80% верных ответов в одной завершённой попытке. Можно попробовать снова.</p>
    <button className="text-button" disabled={busy} onClick={onRefresh}>Обновить результаты</button>
    <div className="homework-actions">
      <label>Модуль домашних заданий<select value={activeModule} onChange={event => { setModule(event.target.value); setDiscipline(''); setTopic('') }}>
        <option value="">Все модули</option>{modules.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>Дисциплина домашних заданий<select value={activeDiscipline} onChange={event => { setDiscipline(event.target.value); setTopic('') }}>
        <option value="">Все дисциплины</option>{disciplines.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>Тема домашних заданий<select value={activeTopic} onChange={event => setTopic(event.target.value)}>
        <option value="">Все темы</option>{topics.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
    </div>
    {!assignments.length && <p role="status">Домашних заданий пока нет.</p>}
    {assignments.map(item => <article className="panel homework-card" key={item.id}>
      <p className="eyebrow">{item.module} · {item.discipline}</p>
      <h2>{item.title}</h2><p className="muted">{item.topic}</p><p>{item.description}</p>
      <p className="homework-status" role="status">{item.completed ? 'Выполнено' : item.finished_attempts ? 'Пока не выполнено' : 'Не начато'}
        {item.best_score !== null && item.best_total !== null ? ` · лучший результат ${item.best_score} из ${item.best_total}` : ''}</p>
      <div className="homework-actions">
        {item.active_session_id && <button className="button secondary" disabled={busy} onClick={() => onResume(item)}>Продолжить попытку</button>}
        <button className="button primary" disabled={busy} onClick={() => onStart(item.id)}>{item.finished_attempts ? 'Пройти ещё раз' : 'Начать тест'} · {item.question_count} вопросов</button>
      </div>
      {confirmId === item.id && <div className="notice" role="alert"><p>Новая попытка заменит незавершённый квиз. Его ответы останутся в истории, но задание не зачтётся.</p><button className="button secondary" disabled={busy} onClick={() => onConfirm(item.id)}>Подтвердить замену</button></div>}
    </article>)}
  </section>
}
