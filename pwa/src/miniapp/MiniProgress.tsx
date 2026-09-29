import type { ProgressOverview } from '../types'

export function MiniProgress({ data, busy, onRefresh }: { data: ProgressOverview; busy: boolean; onRefresh: () => void }) {
  return <section className="page-width progress-page"><span className="eyebrow">ЛИЧНЫЕ РЕЗУЛЬТАТЫ</span><h1>Мой прогресс</h1>
    <button className="button secondary" disabled={busy} onClick={onRefresh}>Обновить</button>
    <div className="panel practice-section"><h2>Всего</h2><p>Квизы — завершено попыток: {data.summary.finished} · Ответов: {data.summary.answered} · Верных: {data.summary.correct}</p><p>«Не знаю» в квизах и глоссарии: {data.summary.knowledge_gaps}</p>{data.glossary && <p>Глоссарий отдельно — верно {data.glossary.correct} из {data.glossary.answered}</p>}
      <p className="hint">Точность ответов в квизах: {data.summary.accuracy == null ? 'пока нет данных' : `${data.summary.accuracy}%`}. Это не оценка освоения.</p></div>
    <section className="panel practice-section"><h2>Темы квизов</h2>{data.topics.length ? <ul>{data.topics.map(item => <li key={item.topic}>{item.topic}: {item.correct} из {item.answered} верных</li>)}</ul> : <p role="status">Истории квизов пока нет. Начните квиз.</p>}</section>
    {data.curriculum && <section className="panel practice-section"><h2>Дисциплины</h2>{data.curriculum.disciplines.length ? <ul>{data.curriculum.disciplines.map(item => <li key={item.scope}>{item.module ? `${item.module.replace(/^module/, 'Модуль ')} · ` : ''}{item.title}: {item.correct} из {item.answered} верных</li>)}</ul> : <p>Пока нет подтверждённой привязки истории к дисциплинам.</p>}</section>}
    {data.recommendations && <section className="panel practice-section"><h2>Что повторить</h2>{!data.recommendations.eligible
      ? <p>Рекомендации появятся после 50 разных вопросов. Сейчас: {data.recommendations.distinct_questions}.</p>
      : data.recommendations.items.length ? <ul>{data.recommendations.items.map(item => <li key={item.topic}>{item.topic}: {item.reason}</li>)}</ul>
        : <p>Тем с ошибками пока нет. Продолжайте занятия по расписанию.</p>}</section>}
  </section>
}
