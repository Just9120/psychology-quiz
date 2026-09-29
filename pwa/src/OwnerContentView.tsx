import { useState } from 'react'
import type { OwnerContent } from './types'

const kinds = { theory: 'теория', glossary: 'глоссарий', case: 'кейсы' } as const
const states: Record<string, string> = { processed: 'Проверены в переданном снимке', pending_review: 'Ожидают проверки', conflict_review: 'Есть возражения', excluded: 'Исключены из обработки', new_unprocessed: 'Нет записи проверки', changed_unprocessed: 'Редакция изменилась', unreadable: 'Не прочитаны' }

export function OwnerContentView({ data, busy, onRefresh }: { data: OwnerContent; busy: boolean; onRefresh: () => void }) {
  const [module, setModule] = useState('')
  const topics = data.topics.filter(item => !module || item.module === module)
  const modules = [...new Set(data.topics.map(item => item.module))]
  return <section className="page-width progress-page">
    <span className="eyebrow">ДЛЯ ВЛАДЕЛЬЦА</span><h1>Содержание и пробелы</h1>
    <p className="lead">Опубликованные задания и материалы. Отсутствие заданий показано отдельно; достаточность банка требует содержательной проверки.</p>
    <button className="button secondary" disabled={busy} onClick={onRefresh}>Обновить обзор</button>
    <article className="panel"><h2>Источники</h2>
      {data.sources.state === 'UNSET' ? <p role="status">Снимок обработки источников не загружен или не прошёл проверку. Текущее покрытие неизвестно.</p> : <>
        <p>Снимок: {data.sources.captured_at}. Файлов: {data.sources.files}; папок: {data.sources.folders}.</p>
        <p>Записей проверки: {data.sources.processing_records}; известных удержаний: {data.sources.known_holds}.</p>
        <ul>{Object.entries(data.sources.processing ?? {}).map(([key, count]) => <li key={key}>{states[key] ?? key}: {count}</li>)}</ul>
        <p className="muted">Это состояние переданного снимка. Оно не подтверждает полное покрытие корпуса или отсутствие более поздних изменений.</p>
      </>}
    </article>
    <label className="field">Модуль обзора<select value={module} disabled={busy} onChange={event => setModule(event.target.value)}><option value="">Все модули</option>{modules.map(value => <option key={value} value={value}>{value.replace('module', 'Модуль ')}</option>)}</select></label>
    <p>Вопросов без привязки к текущим темам: {data.unmapped_questions}.</p>
    <div className="literature-list">{topics.map(topic => <article className="panel" key={topic.id}>
      <h2>{topic.title}</h2><p>{topic.module.replace('module', 'Модуль ')} · Вопросов: {topic.questions}</p>
      <p>Теория: {topic.kinds.theory}; глоссарий: {topic.kinds.glossary}; кейсы: {topic.kinds.case}.</p>
      <p>Терминов: {topic.glossary_terms ?? 'не подтверждено'}; произведений в списке чтения: {topic.literature_works}.</p>
      <p>Личные заметки Obsidian: покрытие не подтверждено.</p>
      {topic.gaps.length > 0 && <p className="notice">Нет опубликованных заданий: {topic.gaps.map(kind => kinds[kind as keyof typeof kinds]).join(', ')}.</p>}
    </article>)}</div>
    <p className="hint">Редактирование и публикация остаются в репозитории. Обзор не изменяет банк и не показывает данные учащихся.</p>
  </section>
}
