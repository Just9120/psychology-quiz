import { Fragment, useState } from 'react'
import { Icon } from './Icon'
import type { Setup, SetupOptions } from './types'

const difficultyNames = { any: 'Любая', easy: 'Базовые', medium: 'Средние', hard: 'Сложные' }

export function QuizSetup({ options, busy, hasAttempt, onStart, onResume }: {
  options: SetupOptions; busy: boolean; hasAttempt: boolean; onStart: (setup: Setup) => void; onResume: () => void
}) {
  const [mode, setMode] = useState<Setup['quiz_mode']>('single')
  const [categories, setCategories] = useState<number[]>([])
  const [count, setCount] = useState<Setup['question_count']>(10)
  const [difficulty, setDifficulty] = useState<Setup['difficulty']>('any')
  const [kinds, setKinds] = useState<NonNullable<Setup['content_kinds']>>(options.content_kind_choices ?? ['theory', 'glossary', 'case'])
  const [confirmReplace, setConfirmReplace] = useState(false)
  const canStart = options.categories.length > 0 && kinds.length > 0 && (mode === 'all' || mode === 'adaptive' || categories.length > 0)
  const modules = [...new Set(options.categories.map(category => category.module || ''))].sort((a, b) => a.localeCompare(b))
  function start() {
    if (hasAttempt && !confirmReplace) { setConfirmReplace(true); return }
    onStart({ quiz_mode: mode, category_ids: mode === 'all' ? [] : categories, question_count: count, difficulty,
      ...(options.content_kind_choices ? { content_kinds: kinds } : {}) })
  }
  return <section className="page-width setup-page"><div className="page-heading"><div><span className="eyebrow">УЧИТЬСЯ ЧЕРЕЗ ВОПРОСЫ</span><h1>Что изучим сегодня?</h1><p className="lead">Выберите тему и подходящий объём. После каждого ответа — короткое объяснение.</p></div><span className="heading-decoration" aria-hidden="true"><Icon name="spark" size={34} /></span></div>
    {hasAttempt && <div className="resume-strip"><Icon name="book" /><span>У вас есть незавершённый квиз.</span><button disabled={busy} onClick={onResume}>Продолжить<Icon name="arrow" size={16} /></button></div>}
    <fieldset className="plain-fieldset"><legend className="section-label">01 <span>Выберите темы</span></legend>
      <div className="segmented" aria-label="Режим квиза">{([['single','Одна тема'],['selected_mix','Микс тем'],['all','Все темы'],['adaptive','Адаптивный']] as const).map(([value,label]) => <button type="button" key={value} className={mode === value ? 'active' : ''} aria-pressed={mode === value} disabled={busy} onClick={() => { setMode(value); setCategories([]); setConfirmReplace(false) }}>{label}</button>)}</div>
      {mode === 'adaptive' && <p className="hint">Сначала вопросы для повторения и слабые темы, с частью новых вопросов. Без выбора темы используются все доступные.</p>}
      {options.categories.length === 0 ? <div className="panel empty-state">Темы пока недоступны. Попробуйте обновить страницу позже.</div>
        : <div className="topic-grid">{modules.map(module => <Fragment key={module || 'unmapped'}><h2 className="topic-module-heading">{module ? module.replace(/^module/, 'Модуль ') : 'Без подтверждённого модуля'}</h2>{options.categories.filter(category => (category.module || '') === module).map((category, index) => {
          const selected = mode === 'all' || categories.includes(category.id)
          return <label key={category.id} className={`topic-card ${selected ? 'selected' : ''} ${mode === 'all' ? 'all-mode' : ''}`}><input type={mode === 'single' ? 'radio' : 'checkbox'} name={mode === 'single' ? 'topic' : undefined} checked={selected} disabled={busy || mode === 'all'} onChange={() => { setConfirmReplace(false); setCategories(current => mode === 'single' ? [category.id] : current.includes(category.id) ? current.filter(id => id !== category.id) : [...current,category.id]) }} /><span className={`topic-symbol hue-${index % 4}`}><Icon name={index % 2 ? 'spark' : 'book'} size={22} /></span><span className="topic-title">{category.name}</span><span className="selection-indicator">{selected && <Icon name="check" size={14} />}</span></label>
        })}</Fragment>)}</div>}
    </fieldset>
    <div className="setup-bottom"><fieldset className="plain-fieldset count-fieldset"><legend className="section-label">02 <span>Сколько вопросов?</span></legend><div className="count-options">{options.question_count_choices.map(value => <button key={value} type="button" className={count === (value === 'all' ? null : value) ? 'active' : ''} aria-pressed={count === (value === 'all' ? null : value)} disabled={busy} onClick={() => setCount(value === 'all' ? null : value)}>{value === 'all' ? 'Все' : value}</button>)}</div><p className="hint">Если вопросов меньше, включим все доступные.</p></fieldset>
      <details className="difficulty"><summary>Дополнительные настройки</summary><label className="field">Сложность<select value={difficulty} disabled={busy} onChange={event => setDifficulty(event.target.value as Setup['difficulty'])}>{options.difficulty_choices.map(value => <option key={value} value={value}>{difficultyNames[value]}</option>)}</select></label>{options.content_kind_choices && <fieldset className="plain-fieldset"><legend>Виды заданий</legend>{options.content_kind_choices.map(kind => <label className="field" key={kind}><input type="checkbox" checked={kinds.includes(kind)} disabled={busy} onChange={() => setKinds(current => current.includes(kind) ? current.filter(item => item !== kind) : [...current, kind])} />{{ theory: 'Теория', glossary: 'Термины', case: 'Кейсы' }[kind]}</label>)}</fieldset>}</details></div>
    {confirmReplace && <div className="notice warning-text" role="status">Новый квиз завершит текущую попытку. Уже сохранённые ответы останутся в истории.</div>}
    <div className="start-row"><p><Icon name="check" size={17} />Прогресс сохраняется после каждого ответа</p><button className="button primary start-button" disabled={busy || !canStart} onClick={start}>{busy ? 'Подготавливаем…' : confirmReplace ? 'Начать новый квиз' : 'Начать квиз'}<Icon name="arrow" /></button></div>
  </section>
}
