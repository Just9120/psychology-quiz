import { useState } from 'react'
import { Icon } from './Icon'
import { ChoiceMenu } from './ChoiceMenu'
import { moduleLabel } from './studyScope'
import type { Setup, SetupOptions } from './types'

const difficultyNames = { any: 'Любая', easy: 'Базовые', medium: 'Средние', hard: 'Сложные' }

export function QuizSetup({ options, busy, activeSessionId, onStart, onResume }: {
  options: SetupOptions; busy: boolean; activeSessionId: number | null; onStart: (setup: Setup, confirmed: boolean) => void; onResume: () => void
}) {
  const [mode, setMode] = useState<Setup['quiz_mode']>('single')
  const [categories, setCategories] = useState<number[]>([])
  const [topics, setTopics] = useState<string[]>([])
  const [module, setModule] = useState('')
  const navigation = options.study_navigation ?? []
  const modules = [...new Set(navigation.flatMap(item => item.modules))].sort((a, b) => a.localeCompare(b, 'en', { numeric: true }))
  const activeModule = modules.includes(module) ? module : ''
  const categoryIds = [...new Set([...categories, ...navigation.filter(item => item.topics.some(topic => topics.includes(topic.id))).map(item => item.category_id)])]
  const [count, setCount] = useState<Setup['question_count']>(10)
  const [difficulty, setDifficulty] = useState<Setup['difficulty']>('any')
  const [kinds, setKinds] = useState<NonNullable<Setup['content_kinds']>>(options.content_kind_choices ?? ['theory', 'glossary', 'case'])
  const [confirmReplaceFor, setConfirmReplaceFor] = useState<number | null>(null)
  const confirmReplace = activeSessionId !== null && confirmReplaceFor === activeSessionId
  const canStart = options.categories.length > 0 && kinds.length > 0 && (mode === 'all' || mode === 'adaptive' || categoryIds.length > 0)
  function chooseCategory(id: number) {
    setConfirmReplaceFor(null)
    setCategories(current => mode === 'single' ? [id] : current.includes(id) ? current.filter(value => value !== id) : [...current, id])
    const scoped = new Set(navigation.find(item => item.category_id === id)?.topics.map(topic => topic.id) ?? [])
    setTopics(current => mode === 'single' ? [] : current.filter(value => !scoped.has(value)))
  }
  function chooseTopic(id: number, topic: string) {
    setConfirmReplaceFor(null)
    setCategories(current => mode === 'single' ? [] : current.filter(value => value !== id))
    setTopics(current => mode === 'single' ? [topic] : current.includes(topic) ? current.filter(value => value !== topic) : [...current, topic])
  }
  function start() {
    if (activeSessionId !== null && !confirmReplace) { setConfirmReplaceFor(activeSessionId); return }
    const topicIds = [...new Set([...topics, ...navigation.filter(item => categories.includes(item.category_id)).flatMap(item => item.topics.map(topic => topic.id))])]
    onStart({ quiz_mode: mode, category_ids: mode === 'all' ? [] : categoryIds, question_count: count, difficulty,
      ...(mode !== 'all' && topics.length ? { topic_ids: topicIds } : {}),
      ...(options.content_kind_choices ? { content_kinds: kinds } : {}) }, confirmReplace)
  }
  return <section className="page-width setup-page"><div className="page-heading"><div><span className="eyebrow">УЧИТЬСЯ ЧЕРЕЗ ВОПРОСЫ</span><h1>Что изучим сегодня?</h1><p className="lead">Выберите тему и подходящий объём. После каждого ответа — короткое объяснение.</p></div><span className="heading-decoration" aria-hidden="true"><Icon name="spark" size={34} /></span></div>
    {activeSessionId !== null && <div className="resume-strip"><Icon name="book" /><span>У вас есть незавершённый квиз.</span><button disabled={busy} onClick={onResume}>Продолжить<Icon name="arrow" size={16} /></button></div>}
    <fieldset className="plain-fieldset"><legend className="section-label">01 <span>Выберите темы</span></legend>
      <div className="segmented" aria-label="Режим квиза">{([['single','Одна тема'],['selected_mix','Микс тем'],['all','Все темы'],['adaptive','Адаптивный']] as const).map(([value,label]) => <button type="button" key={value} className={mode === value ? 'active' : ''} aria-pressed={mode === value} disabled={busy} onClick={() => { setMode(value); setCategories([]); setTopics([]); if (value === 'all') setModule(''); setConfirmReplaceFor(null) }}>{label}</button>)}</div>
      {mode === 'adaptive' && <p className="hint">Сначала вопросы для повторения и слабые темы, с частью новых вопросов. Без выбора темы используются все доступные.</p>}
      {modules.length > 0 && <ChoiceMenu label="Модуль обучения" value={activeModule} disabled={busy || mode === 'all'} onChange={setModule} options={[{ value: '', label: 'Все модули' }, ...modules.map(value => ({ value, label: moduleLabel(value) }))]} />}
      {mode !== 'all' && categoryIds.length > 0 && <p className="hint" role="status">Выбрано дисциплин: {categoryIds.length}{topics.length ? ` · конкретных тем: ${topics.length}` : ''}. Выбор сохраняется при смене модуля.</p>}
      {options.categories.length === 0 ? <div className="panel empty-state">Темы пока недоступны. Попробуйте обновить страницу позже.</div>
        : <div className="topic-grid">{options.categories.filter(category => !activeModule || navigation.find(item => item.category_id === category.id)?.modules.includes(activeModule)).map((category, index) => {
          const selected = mode === 'all' || categories.includes(category.id)
          const branches = navigation.find(item => item.category_id === category.id)
          return <div className="study-discipline" key={category.id}><label className={`topic-card ${selected ? 'selected' : ''} ${mode === 'all' ? 'all-mode' : ''}`}><input type={mode === 'single' ? 'radio' : 'checkbox'} name={mode === 'single' ? 'topic' : undefined} checked={selected} disabled={busy || mode === 'all'} onChange={() => chooseCategory(category.id)} /><span className={`topic-symbol hue-${index % 4}`}><Icon name={index % 2 ? 'spark' : 'book'} size={22} /></span><span className="topic-title">{category.name}</span><span className="selection-indicator">{selected && <Icon name="check" size={14} />}</span></label>
            {branches && <details className="study-topics"><summary>Темы дисциплины · {branches.topics.length}</summary><fieldset className="plain-fieldset"><legend className="sr-only">Темы: {category.name}</legend>{branches.topics.map(topic => <label className="study-topic" key={topic.id}><input type={mode === 'single' ? 'radio' : 'checkbox'} value={topic.id} name={mode === 'single' ? 'topic' : undefined} checked={mode === 'all' || topics.includes(topic.id)} disabled={busy || mode === 'all'} onChange={() => chooseTopic(category.id, topic.id)} /><span>{topic.title} <small>· {topic.question_count} вопр.</small></span></label>)}</fieldset></details>}
          </div>
        })}</div>}
    </fieldset>
      <div className="setup-bottom"><fieldset className="plain-fieldset count-fieldset"><legend className="section-label">02 <span>Сколько вопросов?</span></legend><div className="count-options">{options.question_count_choices.map(value => <button key={value} type="button" className={count === (value === 'all' ? null : value) ? 'active' : ''} aria-pressed={count === (value === 'all' ? null : value)} disabled={busy} onClick={() => { setCount(value === 'all' ? null : value); setConfirmReplaceFor(null) }}>{value === 'all' ? 'Все' : value}</button>)}</div><p className="hint">Если вопросов меньше, включим все доступные.</p></fieldset>
      <details className="difficulty"><summary>Дополнительные настройки</summary><label className="field">Сложность<select value={difficulty} disabled={busy} onChange={event => { setDifficulty(event.target.value as Setup['difficulty']); setConfirmReplaceFor(null) }}>{options.difficulty_choices.map(value => <option key={value} value={value}>{difficultyNames[value]}</option>)}</select></label>{options.content_kind_choices && <fieldset className="plain-fieldset"><legend>Виды заданий</legend>{options.content_kind_choices.map(kind => <label className="field" key={kind}><input type="checkbox" checked={kinds.includes(kind)} disabled={busy} onChange={() => { setKinds(current => current.includes(kind) ? current.filter(item => item !== kind) : [...current, kind]); setConfirmReplaceFor(null) }} />{{ theory: 'Теория', glossary: 'Термины', case: 'Кейс' }[kind]}</label>)}</fieldset>}</details></div>
    {confirmReplace && <div className="notice warning-text" role="status">Новый квиз завершит текущую попытку. Уже сохранённые ответы останутся в истории.</div>}
    <div className="start-row"><p><Icon name="check" size={17} />Прогресс сохраняется после каждого ответа</p><button className="button primary start-button" disabled={busy || !canStart} onClick={start}>{busy ? 'Подготавливаем…' : confirmReplace ? 'Начать новый квиз' : 'Начать квиз'}<Icon name="arrow" /></button></div>
  </section>
}
