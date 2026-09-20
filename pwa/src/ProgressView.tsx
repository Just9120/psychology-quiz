import { useEffect, useState } from 'react'
import { Icon } from './Icon'
import type { AttemptPage, ErrorsPage, HistoryAttempt, HistoryPage, ProgressOverview, SavedAnswer } from './types'

const percent = (value: number | null) => value === null ? '—' : `${value.toLocaleString('ru-RU')}%`
const date = (value: string) => new Date(value.replace(' ', 'T') + 'Z').toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })
const day = (value: string) => new Date(value + 'T12:00:00Z').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const statuses: Record<string, string> = { finished: 'Завершена', in_progress: 'В процессе', abandoned: 'Прервана' }

function AttemptSummary({ item }: { item: HistoryAttempt }) {
  return <><span className="practice-badge">{statuses[item.status] ?? 'Сохранена'}</span><span>{date(item.started_at)}</span><strong>{percent(item.accuracy)} верных</strong><span className="muted">Верно {item.correct} из {item.answered} ответов · отвечено {item.answered} из {item.total_questions}</span></>
}

export function AnswerReview({ item }: { item: SavedAnswer }) {
  const legacy = item.snapshot_provenance !== 'captured'
  return <div className="answer-review">
    <p className={item.is_correct ? 'saved-label' : 'warning-text'}>{item.is_correct ? 'Ответ был верным' : 'Ответ был неверным'}</p>
    {legacy && <p className="notice">Редакция восстановлена из банка позже: исходный текст мог отличаться. Сохранённый результат ответа не пересчитан.</p>}
    <dl><dt>Ваш ответ</dt><dd>{item.selected_option_text ?? 'Вариант не сохранён'}</dd><dt>{legacy ? 'Правильный ответ восстановленной редакции' : 'Правильный ответ'}</dt><dd>{item.correct_option_text ?? 'Нет данных'}</dd><dt>Объяснение</dt><dd>{item.explanation || 'Для этой редакции объяснение не сохранено.'}</dd></dl>
  </div>
}

export function ProgressView({ data, history, detail, busy, onRefresh, onMore, onOpen, onBack, onMoreAnswers }: {
  data: ProgressOverview; history: HistoryPage; detail: AttemptPage | null; busy: boolean
  onRefresh: () => void; onMore: () => void; onOpen: (id: number) => void; onBack: () => void; onMoreAnswers: () => void
}) {
  const [topic, setTopic] = useState('')
  const days = data.topics.find(item => item.topic === topic)?.days ?? data.days
  if (detail) return <section className="page-width progress-page"><button className="text-button" disabled={busy} onClick={onBack}>← К прогрессу</button><h1>Разбор попытки</h1><div className="panel attempt-summary"><AttemptSummary item={detail.attempt} /></div>
    {detail.items.length === 0 && <p className="panel">В этой попытке пока нет сохранённых ответов.</p>}
    {detail.items.map(item => <article className="panel review-card" key={item.answer_id}><span className="eyebrow">{item.topic}</span><h2>{item.question_text}</h2><AnswerReview item={item} /></article>)}
    {detail.next_after !== null && <button className="button secondary" disabled={busy} onClick={onMoreAnswers}>Ещё ответы</button>}
  </section>
  return <section className="page-width progress-page"><div className="practice-heading"><div><span className="eyebrow">ВАША ПРАКТИКА</span><h1>Мой прогресс</h1></div><button className="button secondary" disabled={busy} onClick={onRefresh}><Icon name="refresh" />Обновить</button></div>
    <p className="lead">Каждый ответ — часть пути. Здесь результаты ваших квизов в приложении и связанном Telegram.</p>
    <div className="practice-metrics"><div className="panel"><span>Верных ответов</span><strong>{percent(data.summary.accuracy)}</strong><small>{data.summary.correct} из {data.summary.answered} ответов</small></div><div className="panel"><span>Завершённых квизов</span><strong>{data.summary.finished}</strong><small>Всего попыток: {data.summary.attempts}</small></div></div>
    <p className="hint">Учитываются все сохранённые ответы, в том числе из незавершённых и прерванных попыток. Процент отражает результат практики, а не уровень освоения темы.</p>
    {!data.summary.answered ? <div className="panel empty-state"><h2>История начинается с первого ответа</h2><p className="muted">Пройдите квиз — здесь появятся результаты и темы для повторения.</p></div> : <>
      <section className="panel practice-section"><h2>По темам</h2><p className="hint">Сначала темы с меньшей долей верных ответов. Количество ответов помогает оценить, сколько практики за результатом.</p><ul className="topic-results">{data.topics.map(item => <li key={item.topic}><button disabled={busy} onClick={() => setTopic(item.topic)} aria-label={`Динамика: ${item.topic}`}><span>{item.topic}</span><span><strong>{percent(item.accuracy)}</strong><small>{item.correct} из {item.answered} · ошибок {item.answered - item.correct}</small></span></button></li>)}</ul></section>
      <section className="panel practice-section"><div className="practice-heading"><h2>Динамика практики</h2><label className="field">Тема для динамики<select value={topic} onChange={event => setTopic(event.target.value)}><option value="">Все темы</option>{data.topics.map(item => <option key={item.topic}>{item.topic}</option>)}</select></label></div>
        <p className="hint">Последние 14 дней с ответами, даты по UTC. Состав и сложность вопросов могут отличаться.</p>
        {days.length < 2 && <p className="notice">Для сравнения нужны ответы хотя бы в два разных дня. Пока показан результат одного дня.</p>}
        <table className="practice-table"><caption className="sr-only">Доля верных ответов по дням</caption><thead><tr><th>День</th><th>Верно</th><th>Ответов</th></tr></thead><tbody>{days.map(item => <tr key={item.day}><th scope="row">{day(item.day)}</th><td><span>{percent(item.accuracy)}</span><progress aria-label={`Верных ответов за ${day(item.day)}`} max={100} value={item.accuracy ?? 0} /></td><td>{item.correct} / {item.answered}</td></tr>)}</tbody></table>
      </section>
    </>}
    <section className="practice-section"><h2>История попыток</h2>{history.items.length === 0 ? <p className="muted">Пока нет попыток.</p> : <ul className="attempt-list">{history.items.map(item => <li className="panel" key={item.session_id}><div className="attempt-summary"><AttemptSummary item={item} /></div><button className="button secondary" disabled={busy} aria-label={`Открыть попытку ${item.session_id}`} onClick={() => onOpen(item.session_id)}>Разобрать ответы<Icon name="arrow" /></button></li>)}</ul>}{history.next_before !== null && <button className="button secondary" disabled={busy} onClick={onMore}>Ещё попытки</button>}</section>
  </section>
}

export function ErrorsView({ data, busy, onRefresh, onMore, onTrain, onResume }: {
  data: ErrorsPage; busy: boolean; onRefresh: () => void; onMore: () => void; onTrain: (replace: boolean, count: number | null) => void; onResume: () => void
}) {
  const [count, setCount] = useState<number | null>(5)
  const [confirm, setConfirm] = useState(false)
  useEffect(() => setConfirm(false), [data.latest_session_id])
  return <section className="page-width progress-page"><div className="practice-heading"><div><span className="eyebrow">ПОВТОРИТЬ И ПОНЯТЬ</span><h1>Мои ошибки</h1></div><button className="button secondary" disabled={busy} onClick={() => { setConfirm(false); onRefresh() }}><Icon name="refresh" />Обновить</button></div>
    <p className="lead">Здесь вопросы, на редакцию которых вы в последний раз ответили неверно. Правильный повтор убирает ошибку этой редакции, сохраняя историю.</p>
    <div className="panel practice-section"><h2>{data.trainable_count ? `Для тренировки: ${data.trainable_count}` : 'Сейчас нет вопросов для тренировки'}</h2>
      {data.trainable_count ? <><p className="muted">Используем актуальные вопросы. Если текст обновлён, объяснение прежней ошибки остаётся ниже.</p><fieldset className="plain-fieldset"><legend>Сколько вопросов повторим?</legend><div className="count-options">{[5, 10, 15, null].map(value => <button key={value ?? 'all'} disabled={busy} aria-pressed={count === value} className={count === value ? 'active' : ''} onClick={() => setCount(value)}>{value ?? 'Все'}</button>)}</div></fieldset>
        {data.has_active_attempt && <p className="notice">Есть незавершённый квиз. <button className="text-button" disabled={busy} onClick={onResume}>Продолжить квиз</button></p>}
        {confirm && <p className="notice warning-text" role="status">Тренировка завершит текущую попытку. Уже сохранённые ответы останутся в истории.</p>}
        <div className="button-row"><button className="button primary" disabled={busy} onClick={() => { if (data.has_active_attempt && !confirm) setConfirm(true); else onTrain(confirm, count) }}>{confirm ? 'Заменить квиз и начать' : 'Начать тренировку'}<Icon name="arrow" /></button>{confirm && <button className="button secondary" disabled={busy} onClick={() => setConfirm(false)}>Отмена</button>}</div>
      </> : <p className="muted">{data.total ? 'Остались исторические ошибки: текущие редакции уже решены верно или вопросы выведены из банка.' : 'Ошибок пока нет. Они появятся после неверного ответа; верно решённые редакции сюда не попадают.'}</p>}
    </div>
    {data.items.length > 0 && <h2>Разбор ошибок · {data.total}</h2>}
    {data.items.map(item => <article className="panel review-card" key={item.answer_id}><span className="eyebrow">{item.topic}</span><h2>{item.question_text}</h2><p className="hint">{date(item.answered_at)}{item.edition_state === 'changed' && ' · Предыдущая редакция'}{item.edition_state === 'retired' && ' · Вопрос выведен из банка'}{item.edition_state === 'changed' && !item.trainable && ' · Текущая редакция уже решена верно'}</p><details><summary>Разобрать ответ</summary><AnswerReview item={item} /></details></article>)}
    {data.next_before !== null && <button className="button secondary" disabled={busy} onClick={onMore}>Ещё ошибки</button>}
  </section>
}
