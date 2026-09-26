import { useState } from 'react'
import { api } from './api'
import type { GlossaryState, GlossaryTopic } from './types'

export function GlossaryView({ initial, topics, busy, run, client = api }: {
  initial: GlossaryState; topics: GlossaryTopic[]; busy: boolean
  run: (operation: () => Promise<void>) => Promise<void>
  client?: Pick<typeof api, 'glossaryState' | 'glossaryStart' | 'glossaryAnswer' | 'glossaryNext'>
}) {
  const [saved, setSaved] = useState(initial)
  const [setup, setSetup] = useState(initial.state === 'idle')
  const [mode, setMode] = useState<'single' | 'mix' | 'all'>('single')
  const [topic, setTopic] = useState(topics.some(item => item.topic_id === initial.topic_id)
    ? initial.topic_id! : topics.find(item => item.available_count >= 4)?.topic_id ?? topics[0]?.topic_id ?? '')
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [count, setCount] = useState<number | 'all'>(5)
  const [replace, setReplace] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const active = saved.state === 'in_progress' || saved.state === 'feedback'
  const eligible = topics.filter(item => item.available_count >= 4)
  const setupTopics = mode === 'single' ? topic : mode === 'all' ? eligible.map(item => item.topic_id) : selectedTopics
  const validSelection = mode === 'single' ? eligible.some(item => item.topic_id === topic)
    : mode === 'all' ? eligible.length >= 1 : selectedTopics.length >= 2
  const q = saved.current_question, f = saved.feedback

  function apply(state: GlossaryState) {
    setSaved(state); setSetup(state.state === 'idle'); setSelected(null); setPending(null)
    setReplace(false); setUncertain(false)
  }
  async function refresh() { apply((await client.glossaryState()).glossary_state) }
  async function start() {
    setUncertain(true); setReplace(false)
    apply((await client.glossaryStart(setupTopics, count, active ? saved.session_id! : null, replace)).glossary_state)
  }
  async function answer() {
    if (!q || selected === null) return
    const choice = pending ?? selected
    setPending(choice)
    const result = await client.glossaryAnswer(q.session_id, q.step_id, choice)
    apply({ ...saved, ...result.glossary_state })
  }
  return <section className="page-width glossary-page"><span className="eyebrow">ТЕРМИНЫ И СМЫСЛЫ</span><h1>Глоссарий</h1>
    <p className="lead">Вспоминайте определения и разбирайте ответы. Сохранённый тест привязан к вашему учебному профилю.</p>
    {uncertain ? <div className="panel"><h2>Проверим сохранённое состояние</h2><p>Ответ сервера не получен. Восстановите тест перед новым запуском.</p><button className="button primary" disabled={busy} onClick={() => void run(refresh)}>Восстановить глоссарий</button></div>
      : setup ? <div className="panel practice-section"><h2>Тест по терминам</h2>
        {topics.length ? <><label className="field">Режим<select value={mode} disabled={busy} onChange={e => { setMode(e.target.value as 'single' | 'mix' | 'all'); setReplace(false) }}><option value="single">Одна тема</option><option value="mix">Несколько тем</option><option value="all">Случайно из всех тем</option></select></label>
          {mode === 'single' ? <label className="field">Тема глоссария<select value={topic} disabled={busy} onChange={e => { setTopic(e.target.value); setReplace(false) }}>{topics.map(item => <option value={item.topic_id} key={item.topic_id} disabled={item.available_count < 4}>{item.title} · {item.available_count} терминов</option>)}</select></label>
            : mode === 'mix' ? <fieldset className="practice-section"><legend>Выберите не меньше двух тем</legend>{topics.map(item => <label className="reset-confirm" key={item.topic_id}><input type="checkbox" disabled={busy || item.available_count < 4} checked={selectedTopics.includes(item.topic_id)} onChange={e => { setSelectedTopics(previous => e.target.checked ? [...previous, item.topic_id] : previous.filter(id => id !== item.topic_id)); setReplace(false) }} /><span>{item.title} · {item.available_count} терминов</span></label>)}</fieldset>
              : <p className="muted">Случайные термины из всех доступных тем ({eligible.length}).</p>}
          <label className="field">Количество терминов<select value={count} disabled={busy} onChange={e => { setCount(e.target.value === 'all' ? 'all' : Number(e.target.value)); setReplace(false) }}><option value={5}>5</option><option value={10}>10</option><option value="all">Все доступные</option></select></label>
          {active && <label className="reset-confirm"><input type="checkbox" checked={replace} disabled={busy} onChange={e => setReplace(e.target.checked)} /><span>Прервать незавершённый тест по терминам и начать новый. Уже сохранённые ответы останутся.</span></label>}
          <div className="button-row"><button className="button primary" disabled={busy || !validSelection || (active && !replace)} onClick={() => void run(start)}>Начать тест по терминам</button>{saved.state !== 'idle' && <button className="button secondary" disabled={busy} onClick={() => void run(refresh)}>К сохранённому тесту</button>}</div>
        </> : <p role="status">Темы глоссария пока недоступны.</p>}
      </div>
        : saved.state === 'completed' && saved.result ? <div className="panel result-card"><h2>Тест по терминам завершён</h2><p className="lead">{saved.result.score} из {saved.result.total_questions} верных ответов</p><p className="muted">Результат сохранён в вашем аккаунте.</p><button className="button primary" disabled={busy} onClick={() => setSetup(true)}>Выбрать следующий тест</button></div>
          : q ? <article className="panel question-card"><div className="quiz-toolbar"><button className="text-button" disabled={busy} onClick={() => { setSetup(true); setReplace(false) }}>← К темам глоссария</button><span>{q.order_index} из {q.total_questions}</span></div>
            <p className="eyebrow">{q.topic_title}</p><h2>Что означает «{q.term}»?</h2>
            {f && saved.state === 'feedback' ? <div className="answer-feedback"><h3>{f.is_correct ? 'Верно' : 'Разберём этот ответ'}</h3><dl className="answer-review"><dt>Ваш ответ</dt><dd>{f.selected_option_text}</dd>{!f.is_correct && <><dt>Правильный ответ</dt><dd>{f.correct_option_text}</dd></>}<dt>Объяснение</dt><dd>{f.explanation}</dd></dl><p className="muted">Ответ сохранён · {f.answered_count} из {f.total_questions}</p><button className="button primary" disabled={busy} onClick={() => void run(async () => apply((await client.glossaryNext(q.session_id, f.step_id)).glossary_state))}>{f.has_next ? 'Следующий термин' : 'Показать результат'}</button></div>
              : <><fieldset className="answer-options"><legend className="sr-only">Определение термина</legend>{q.options.map((option, index) => <label className={`answer-option ${selected === option.option_index ? 'selected' : ''}`} key={option.option_index}><input type="radio" name="term-answer" checked={selected === option.option_index} disabled={busy || pending !== null} onChange={() => setSelected(option.option_index)} /><span className="answer-letter">{index + 1}</span><span>{option.option_text}</span></label>)}</fieldset>
                {pending !== null && <p className="notice" role="status">Подтверждение не получено. Можно повторить тот же ответ или восстановить состояние.</p>}
                <button className="button primary" disabled={busy || selected === null} onClick={() => void run(answer)}>{pending !== null ? 'Повторить тот же ответ' : 'Проверить определение'}</button></>}
          </article> : <p>Восстановите сохранённый тест.</p>}
    {!uncertain && <button className="text-button check-state" disabled={busy} onClick={() => void run(refresh)}>Восстановить глоссарий</button>}
  </section>
}
