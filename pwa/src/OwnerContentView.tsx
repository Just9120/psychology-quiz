import { useState } from 'react'
import { ChoiceMenu } from './ChoiceMenu'
import type { OwnerContent } from './types'

const kinds = { theory: 'теория', glossary: 'глоссарий', case: 'кейсы' } as const
const states: Record<string, string> = { processed: 'Проверены в переданном снимке', pending_review: 'Ожидают проверки', conflict_review: 'Есть возражения', excluded: 'Исключены из обработки', new_unprocessed: 'Нет записи проверки', changed_unprocessed: 'Редакция изменилась', unreadable: 'Не прочитаны' }

export function OwnerContentView({ data, busy, onRefresh }: { data: OwnerContent; busy: boolean; onRefresh: () => void }) {
  const [topicId, setTopicId] = useState('')
  const [discipline, setDiscipline] = useState('')
  const lessons = data.sources.coverage?.lessons ?? []
  const disciplines = [...new Set(lessons.map(lesson => lesson.discipline))]
  const topics = data.topics.filter(item => !topicId || item.id === topicId)
  const knowledge = data.knowledge?.state === 'PUBLISHED' ? data.knowledge : undefined
  return <section className="page-width progress-page">
    <span className="eyebrow">ДЛЯ ВЛАДЕЛЬЦА</span><h1>Содержание и пробелы</h1>
    <p className="lead">Опубликованные задания и материалы. Отсутствие заданий показано отдельно; достаточность банка требует содержательной проверки.</p>
    <button className="button secondary" disabled={busy} onClick={onRefresh}>Обновить обзор</button>
    <ChoiceMenu label="Тема обзора" value={topicId} disabled={busy} onChange={setTopicId} options={[{ value: '', label: 'Все темы' }, ...data.topics.map(item => ({ value: item.id, label: item.title }))]} />
    <article className="panel"><h2>Источники</h2>
      {data.sources.state === 'UNSET' ? <p role="status">Снимок обработки источников не загружен или не прошёл проверку. Текущее покрытие неизвестно.</p> : <>
        <p>{data.sources.observation_basis === 'saved_inputs' ? 'Сводка сохранённых данных' : 'Снимок'}: {data.sources.captured_at}. Файлов: {data.sources.files}; папок: {data.sources.folders}.</p>
        <p>Записей проверки: {data.sources.processing_records}; известных удержаний: {data.sources.known_holds}.</p>
        <ul>{Object.entries(data.sources.processing ?? {}).map(([key, count]) => <li key={key}>{states[key] ?? key}: {count}</li>)}</ul>
        <p className="muted">Это состояние переданного снимка. Оно не подтверждает полное покрытие корпуса или отсутствие более поздних изменений.</p>
        {data.sources.observation_basis === 'saved_inputs' && <p className="muted">Дата сводки — время расчёта. Актуальность папки Google Drive этим расчётом не проверялась.</p>}
      </>}
    </article>
    {knowledge && <article className="panel"><h2>Опубликованная база знаний</h2>
      <p>Пакет от {knowledge.published_at}: {knowledge.atomic_notes} самостоятельных заметок; тематических обзоров: {knowledge.sections?.length}.</p>
      <p>Заметок без подтверждённой связи с зарегистрированными занятиями: {knowledge.unmapped_notes}. Они остаются в базе знаний.</p>
      <p className="muted">Связь установлена по точным названиям источников опубликованного пакета. Подготовленные заметки не снимают возражения к источникам и не подтверждают актуальность их редакций или полноту личного Obsidian.</p>
      <details><summary>Разделы базы знаний</summary>{knowledge.sections?.map(section => <p key={section.title}>{section.title}: {section.notes}</p>)}</details>
    </article>}
    {data.sources.coverage && <article className="panel"><h2>Подготовка по учебным материалам</h2>
      <p>Зарегистрированных источников: {data.sources.coverage.tracked_sources}; файлов вне registry: {data.sources.coverage.untracked_files}.</p>
      <p>Опубликованных вопросов без подтверждённой привязки к учебной теме в снимке: {data.sources.coverage.unmapped_published_questions}.</p>
      {data.sources.coverage.unmapped_published_glossary !== undefined && <p>Опубликованных терминов без подтверждённой привязки к учебной теме в снимке: {data.sources.coverage.unmapped_published_glossary}.</p>}
      {!knowledge && data.sources.coverage.prepared_notes_unmapped !== undefined && <p>Подготовленных заметок без подтверждённой привязки к учебной теме: {data.sources.coverage.prepared_notes_unmapped}.</p>}
      <p className="muted">Привязка проверена по редакции вопроса. Цифры относятся к датированному снимку выше; пустой раздел не означает оценку достаточности.</p>
      {data.sources.coverage.unreleased_lessons && <div className="notice notice-vertical">
        <p>Ещё не опубликованные учебные темы: {data.sources.coverage.unreleased_lessons.total}. Актуальные метаданные: {data.sources.coverage.unreleased_lessons.metadata_current}; темы с возражениями: {data.sources.coverage.unreleased_lessons.known_holds}.</p>
        {Object.entries(data.sources.coverage.unreleased_lessons.processing).map(([state, count]) => <p key={state}>{states[state] ?? 'Источник отсутствует'}: {count}</p>)}
        <p>Это учёт подготовки материалов, а не подтверждение научной проверки или публикации.</p>
      </div>}
      <ChoiceMenu label="Дисциплина подготовки" value={discipline} disabled={busy} onChange={setDiscipline} options={[{ value: '', label: 'Все дисциплины' }, ...disciplines.map(title => ({ value: title, label: title }))]} />
      {disciplines.filter(title => !discipline || title === discipline).map(title => <details className="preparation-discipline" key={title}><summary>{title} · тем: {lessons.filter(lesson => lesson.discipline === title).length}</summary><div className="literature-list">{lessons.filter(lesson => lesson.discipline === title).map(lesson => <div key={lesson.id}>
        <h3>{lesson.title}</h3><p>{lesson.discipline}</p>
        <p>{lesson.source_metadata_current ? 'Редакция источника совпадала с registry' : 'Редакция источника требует сверки'} · {states[lesson.processing_state] ?? 'Нет записи проверки'}.</p>
        {lesson.known_hold && <p className="notice">Есть неразрешённое возражение к источнику.</p>}
        <p>Теория: {lesson.kinds.theory}; глоссарий: {lesson.kinds.glossary}; кейсы: {lesson.kinds.case}.</p>
        {Object.values(lesson.kinds).every(count => count === 0) && <p className="notice">Нет опубликованных вопросов с подтверждённой привязкой к этой теме.</p>}
        {lesson.glossary_terms !== null ? <p>Опубликованных терминов с подтверждённой привязкой к этой теме в снимке: {lesson.glossary_terms}.</p> : <p className="muted">Отдельные термины: покрытие по этой теме не подтверждено.</p>}
        {knowledge?.lessons?.[lesson.id] !== undefined ? <p>Заметок в опубликованном пакете по подтверждённым связям: {knowledge.lessons[lesson.id]}. Полнота покрытия занятия не установлена.</p> : lesson.notes_state === 'PREPARED' ? <><p>Подготовлено заметок в переданном снимке: {lesson.notes}.</p><p className="muted">Это проверка подготовки, а не подтверждение публикации в Obsidian или полноты личной базы. Полнота личной базы по этой теме не подтверждена.</p></> : <p className="muted">Личные заметки: покрытие по этой теме не подтверждено.</p>}
      </div>)}</div></details>)}
      <p className="muted">Количество терминов учитывает только проверенную привязку к редакции источника; отсутствие привязки не означает отсутствия термина в корпусе.</p>
    </article>}

    <p>Вопросов без привязки к текущим темам: {data.unmapped_questions}.</p>
    <div className="literature-list">{topics.map(topic => <article className="panel" key={topic.id}>
      <h2>{topic.title}</h2><p>Вопросов: {topic.questions}</p>
      <p>Теория: {topic.kinds.theory}; глоссарий: {topic.kinds.glossary}; кейсы: {topic.kinds.case}.</p>
      <p>Терминов: {topic.glossary_terms ?? 'не подтверждено'}; произведений в списке чтения: {topic.literature_works}.</p>
      {knowledge?.disciplines?.[topic.id] !== undefined ? <p>Заметок в опубликованном пакете по подтверждённым связям: {knowledge.disciplines[topic.id]}. Полнота личного Obsidian не установлена.</p> : <p>Личные заметки Obsidian: покрытие не подтверждено.</p>}
      {topic.gaps.length > 0 && <p className="notice">Нет опубликованных заданий: {topic.gaps.map(kind => kinds[kind as keyof typeof kinds]).join(', ')}.</p>}
    </article>)}</div>
    <p className="hint">Редактирование и публикация остаются в репозитории. Обзор не изменяет банк и не показывает данные учащихся.</p>
  </section>
}
