import { useEffect, useState } from 'react'
import { api, errorMessage } from './api'
import { Icon } from './Icon'
import type { DemoAnswer, DemoItem } from './types'

export function DemoView({ onExit }: { onExit: () => void }) {
  const [items, setItems] = useState<DemoItem[] | null>(null)
  const [step, setStep] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [answer, setAnswer] = useState<DemoAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setBusy(true); setError('')
    try { setItems((await api.demoItems()).items) }
    catch (failure) { setError(errorMessage(failure)) }
    finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [])

  async function submit() {
    if (selected === null || !items?.[step]) return
    setBusy(true); setError('')
    try { setAnswer(await api.demoAnswer(items[step].id, selected)) }
    catch (failure) { setError(errorMessage(failure)) }
    finally { setBusy(false) }
  }

  const item = items?.[step]
  return <main className="workspace-main"><section className="page-width quiz-page"><button className="text-button" onClick={onExit}>← Ко входу</button><div className="page-heading"><div><span className="eyebrow">ЗНАКОМСТВО С АТЛАСОМ</span><h1>Три задания</h1><p className="lead">Теория, термин и кейс. Ответы этой демонстрации не сохраняются; аккаунт не нужен.</p></div></div>
    {error && <div className="app-alert" role="alert">{error}</div>}
    {!items ? <div className="panel empty-state"><p>{busy ? 'Загружаем задания…' : 'Не удалось открыть демонстрацию.'}</p>{!busy && <button className="button secondary" onClick={() => void load()}>Повторить загрузку</button>}</div>
      : !item ? <div className="panel empty-state"><h2>Демонстрация завершена</h2><p>Здесь ответы не сохранялись.</p><button className="button primary" onClick={onExit}>Ко входу</button></div>
        : <article className="panel quiz-card"><span className="eyebrow">{step + 1} из {items.length} · {{ theory: 'Теория', glossary: 'Термин', case: 'Кейс' }[item.kind]}</span><h2 className="question-heading" style={{ whiteSpace: 'pre-line' }}>{item.prompt}</h2>
          <fieldset className="answer-options"><legend className="sr-only">Варианты ответа</legend>{item.options.map((option, index) => <label className={`answer-option ${selected === index ? 'selected' : ''}`} key={index}><input type="radio" name="demo-answer" checked={selected === index} disabled={busy || answer !== null} onChange={() => setSelected(index)} /><span className="answer-letter">{index + 1}</span><span>{option}</span></label>)}</fieldset>
          {answer ? <div className="explanation" role="status"><h3>{answer.is_correct ? 'Верно' : 'Разберём ответ'}</h3><p>Верный вариант: {item.options[answer.correct_option_index]}</p><p>{answer.explanation}</p>{answer.case_review && <><h3>Условия и альтернативы</h3><p>{answer.case_review.approach}</p><ul>{answer.case_review.conditions.map((condition, index) => <li key={index}>{condition}</li>)}</ul><ol>{answer.case_review.option_rationales.map((reason, index) => <li key={index}>{reason}</li>)}</ol><p>{answer.case_review.ambiguity}</p></>}</div> : null}
          <div className="question-actions">{answer ? <button className="button primary" onClick={() => { setStep(step + 1); setSelected(null); setAnswer(null) }}>{step + 1 === items.length ? 'Завершить' : 'Следующее задание'}<Icon name="arrow" /></button> : <button className="button primary" disabled={busy || selected === null} onClick={() => void submit()}>{busy ? 'Проверяем…' : 'Проверить ответ'}<Icon name="arrow" /></button>}</div>
        </article>}
  </section></main>
}
