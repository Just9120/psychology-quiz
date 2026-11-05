import { useState } from 'react'
import { StudyFilters } from './StudyFilters'
import { emptyStudyScope, matchesStudy, moduleId, moduleLabel, studyChoices, type StudyPath } from './studyScope'
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
  const [scope, setScope] = useState(emptyStudyScope)
  const path = (item: HomeworkAssignment): StudyPath[] => [{ module: moduleId(item.module),
    discipline_id: item.discipline_id ?? item.discipline, discipline: item.discipline,
    topic_id: item.curriculum_topic?.id ?? JSON.stringify([item.discipline, item.topic]),
    topic: item.curriculum_topic?.title ?? item.topic }]
  const choices = studyChoices(catalog.assignments.flatMap(path), scope)
  const assignments = catalog.assignments.filter(item => matchesStudy(path(item), choices.scope))

  return <section className="page-width homework-page">
    <span className="eyebrow">МОЁ ОБУЧЕНИЕ</span><h1>Домашние задания</h1>
    <p className="lead">Здесь проверяются знания по материалам заданий. Тест не подтверждает выполнение эссе, наблюдения или практического упражнения.</p>
    <p className="muted">Задание считается выполненным при 80% верных ответов в одной завершённой попытке. Можно попробовать снова.</p>
    <button className="text-button" disabled={busy} onClick={onRefresh}>Обновить результаты</button>
    <StudyFilters choices={choices} busy={busy} onChange={setScope} topicLabel="Тема домашних заданий" />
    {!assignments.length && <p role="status">Домашних заданий пока нет.</p>}
    {assignments.map(item => <article className="panel homework-card" key={item.id}>
      <p className="eyebrow">{moduleLabel(moduleId(item.module))} · {item.discipline}</p>
      <h2>{item.title}</h2>{item.topic.trim().toLocaleLowerCase('ru') !== item.title.trim().toLocaleLowerCase('ru') && <p className="muted">{item.topic}</p>}<p>{item.description}</p>
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
