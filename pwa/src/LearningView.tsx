import { useState } from 'react'
import { api } from './api'
import { Icon } from './Icon'
import type { AchievementsOverview, GoalsOverview, GoalKind, MasteryOverview, ReviewQueue } from './types'

const goalNames: Record<GoalKind, string> = { study: 'Завершённые попытки', review: 'Ответы в очереди повторения', reading: 'Прочитанные материалы' }
const achievementNames: Record<string, string> = { new_topic: 'Новая тема', corrected_error: 'Исправленная ошибка', regularity: 'Регулярно занимаюсь' }
const date = (value: string) => new Date(`${value}T12:00:00Z`).toLocaleDateString('ru-RU', { timeZone: 'UTC', day: 'numeric', month: 'long' })

export function LearningView({ review, mastery, goals, achievements, busy, onRefresh, onSaveGoal, onStartQuiz, onStartGlossary }: {
  review: ReviewQueue; mastery: MasteryOverview; goals: GoalsOverview; achievements: AchievementsOverview; busy: boolean
  onRefresh: () => void; onSaveGoal: (kind: GoalKind, target: number) => void
  onStartQuiz: (replace: boolean) => void; onStartGlossary: (topicId: string, replace: boolean) => void
}) {
  const [targets, setTargets] = useState<Record<GoalKind, string>>({
    study: String(goals.goals.find(item => item.goal_kind === 'study')?.weekly_target ?? ''),
    review: String(goals.goals.find(item => item.goal_kind === 'review')?.weekly_target ?? ''),
    reading: String(goals.goals.find(item => item.goal_kind === 'reading')?.weekly_target ?? ''),
  })
  const [replace, setReplace] = useState<'quiz' | string | null>(null)
  const dueQuiz = review.items.filter(item => item.kind === 'quiz' && item.is_due)
  const dueGlossary = review.items.filter(item => item.kind === 'glossary' && item.is_due)
  const glossaryTopics = [...new Map(dueGlossary.map(item => [item.topic_id!, item.topic])).entries()]
  return <section className="page-width progress-page"><div className="practice-heading"><div><span className="eyebrow">ЛИЧНЫЙ РИТМ</span><h1>Повторение и цели</h1></div><button className="button secondary" disabled={busy} onClick={onRefresh}><Icon name="refresh" />Обновить</button></div>
    <p className="lead">Повторяйте изученное в своём темпе. Даты рассчитываются по UTC; освоение требует нескольких ответов на одну редакцию с интервалами.</p>
    <section className="panel practice-section"><h2>Сегодня к повторению · {review.due_count}</h2>
      {review.items.length === 0 ? <p className="muted">Пока нет ответов, по которым можно составить очередь. Начните квиз или глоссарий.</p> : !review.due_count ? <p className="muted">На сегодня всё повторено. Следующие даты показаны ниже.</p> : <><p>{dueQuiz.length} вопросов · {dueGlossary.length} терминов</p>
        {dueQuiz.length > 0 && <button className="button primary" disabled={busy} onClick={() => { setReplace('quiz'); onStartQuiz(false) }}>Повторить вопросы<Icon name="arrow" /></button>}
        {glossaryTopics.map(([id, title]) => <button className="button secondary" key={id} disabled={busy} onClick={() => { setReplace(id); onStartGlossary(id, false) }}>Термины: {title}<Icon name="arrow" /></button>)}
        {replace && <div className="notice" role="status">Если есть незавершённая попытка, её замена требует подтверждения. <button className="text-button" disabled={busy} onClick={() => replace === 'quiz' ? onStartQuiz(true) : onStartGlossary(replace, true)}>Подтвердить замену попытки</button> <button className="text-button" onClick={() => setReplace(null)}>Отмена</button></div>}
      </>}
      {review.items.length > 0 && <details><summary>Все запланированные повторения</summary><ul>{review.items.slice(0, 30).map((item, index) => <li key={`${item.kind}:${item.question_id ?? item.term_id}:${index}`}>{item.topic} · {item.kind === 'quiz' ? 'вопрос' : 'термин'} · {item.is_due ? 'пора повторить' : date(item.due_on)}{item.reason === 'new_edition' ? ' · новая редакция' : ''}</li>)}</ul>{review.items.length > 30 && <p className="hint">Показаны первые 30 из {review.items.length}; обновите список после тренировки.</p>}</details>}
    </section>
    <section className="panel practice-section"><h2>Освоение</h2><p>{mastery.questions.mastered_count} из {mastery.questions.assessed_count} изученных вопросов · {mastery.terms.mastered_count} из {mastery.terms.assessed_count} изученных терминов</p><p className="hint">«Освоено» — три верных ответа на одну редакцию: интервалы не меньше 1 и 3 дней, общий период не меньше 7 дней. Ошибка или новая редакция сбрасывает статус. Остальное — недостаточно данных; процент верных ответов сам по себе не означает освоение.</p></section>
    <section className="panel practice-section"><h2>Цели на неделю</h2><p className="hint">Неделя с {date(goals.week_start)}, UTC. Цели и достижения видны только вам.</p><div className="goal-list">{goals.goals.map(item => <form key={item.goal_kind} onSubmit={event => { event.preventDefault(); const target = Number(targets[item.goal_kind]); if (Number.isSafeInteger(target) && target > 0) onSaveGoal(item.goal_kind, target) }}><label className="field">{goalNames[item.goal_kind]}<input type="number" min="1" step="1" value={targets[item.goal_kind]} disabled={busy} onChange={event => setTargets(current => ({ ...current, [item.goal_kind]: event.target.value }))} /></label><span>{item.completed}{item.weekly_target === null ? ' выполнено' : ` из ${item.weekly_target}${item.reached ? ' · цель достигнута' : ''}`}</span><button className="button secondary" type="submit" disabled={busy || !Number.isSafeInteger(Number(targets[item.goal_kind])) || Number(targets[item.goal_kind]) < 1}>Сохранить цель</button></form>)}</div></section>
    <section className="panel practice-section"><h2>Достижения</h2>{achievements.achievements.length ? <ul>{achievements.achievements.map(item => <li key={`${item.kind}:${item.evidence_key}`}>{achievementNames[item.kind] ?? item.kind} · {date(item.earned_at.slice(0, 10))}</li>)}</ul> : <p className="muted">Достижений пока нет. Они появятся после занятий и повторений.</p>}</section>
  </section>
}

export async function loadLearning() {
  const [review, mastery, goals, achievements] = await Promise.all([api.review(), api.mastery(), api.goals(), api.achievements()])
  return { review, mastery, goals, achievements }
}
