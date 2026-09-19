import { Icon } from './Icon'
import type { Answer, Feedback, Question, RunnerState } from './types'

export function QuizView({ state, feedback, feedbackQuestion, selected, pending, busy, onSelect, onAnswer, onNext, onSetup, onRefresh }: {
  state: RunnerState; feedback: Feedback | null; feedbackQuestion: Question | null
  selected: number | null; pending: Answer | null; busy: boolean
  onSelect: (choice: number) => void; onAnswer: () => void; onNext: () => void; onSetup: () => void; onRefresh: () => void
}) {
  const question = feedback ? feedbackQuestion : state.current_question
  const total = question?.total_questions ?? state.result?.total_questions ?? state.progress?.total_questions ?? 0
  const answered = state.progress?.answered_count ?? (state.state === 'completed' ? total : 0)
  if (!feedback && state.state === 'completed' && state.result) {
    const result = state.result
    return <section className="result-page page-width"><span className="eyebrow">ЕЩЁ ОДИН ШАГ ВПЕРЁД</span><h1>Квиз завершён</h1><p className="lead">Хорошая работа. Вопросы помогают увидеть, что уже знакомо и к чему стоит вернуться.</p>
      <div className="panel result-card"><div className="score-ring" style={{ background: `conic-gradient(var(--green) ${result.percent}%, var(--line) 0)` }}><div><strong>{result.score}<span> / {result.total_questions}</span></strong><small>правильных ответов</small></div></div><h2>{result.percent}% верных ответов</h2><p className="muted">Результат сохранён в вашем аккаунте.</p><button className="button primary" disabled={busy} onClick={onSetup}>Выбрать следующий квиз<Icon name="arrow" /></button></div>
    </section>
  }
  return <section className="quiz-page page-width"><div className="quiz-toolbar"><button className="text-button" disabled={busy} onClick={onSetup}>← К темам</button><span className="eyebrow">КВИЗ ПО ПСИХОЛОГИИ</span><span className="question-counter">{question ? `Вопрос ${question.order_index} из ${question.total_questions}` : 'Последний ответ'}</span></div>
    <progress className="quiz-progress" value={answered} max={Math.max(total, 1)} aria-label="Отвечено вопросов" />
    <article className="panel question-panel">
      {feedback ? <><div className={`feedback-label ${feedback.is_correct ? 'correct' : 'incorrect'}`} role="status"><Icon name={feedback.is_correct ? 'check' : 'close'} />{feedback.is_correct ? 'Верно' : 'Разберём этот ответ'}</div>
        <h1 className="question-heading">{question?.question_text ?? 'Продолжим с сохранённого ответа'}</h1>
        <div className="feedback-answers"><p><span>Ваш ответ</span><strong>{feedback.selected_option_text ?? 'В старой попытке вариант ответа не сохранён'}</strong></p>{!feedback.is_correct && <p className="correct-answer"><span>Правильный ответ</span><strong>{feedback.correct_option_text}</strong></p>}</div>
        {feedback.explanation && <div className="explanation"><span className="eyebrow">ПОЧЕМУ ТАК</span><p>{feedback.explanation}</p></div>}
        <div className="question-actions"><span className="saved-label"><Icon name="check" size={16} />Ответ сохранён</span><button className="button primary" disabled={busy} onClick={onNext}>{state.state === 'completed' ? 'Посмотреть результат' : 'Следующий вопрос'}<Icon name="arrow" /></button></div>
      </> : question ? <><span className="eyebrow">ВЫБЕРИТЕ ОДИН ОТВЕТ</span><h1 className="question-heading">{question.question_text}</h1>
        <fieldset className="answer-options"><legend className="sr-only">Варианты ответа</legend>{question.options.map((option, index) => <label key={option.option_index} className={`answer-option ${selected === option.option_index ? 'selected' : ''}`}><input type="radio" name="answer" checked={selected === option.option_index} disabled={busy || pending !== null} onChange={() => onSelect(option.option_index)} /><span className="answer-letter">{index + 1}</span><span>{option.option_text}</span><span className="selection-indicator">{selected === option.option_index && <Icon name="check" size={14} />}</span></label>)}</fieldset>
        {pending && !busy && <div className="notice" role="status"><span>Подтверждение не получено. Повторим тот же ответ — второй раз он не засчитается.</span></div>}
        <div className="question-actions"><span className="hint">Можно обдумать ответ — время не ограничено.</span><button className="button primary" disabled={busy || selected === null} onClick={onAnswer}>{busy ? 'Сохраняем…' : pending ? 'Повторить отправку' : 'Проверить ответ'}<Icon name="arrow" /></button></div>
        {pending && !busy && <button className="text-button check-state" onClick={onRefresh}>Проверить сохранённое состояние</button>}
      </> : <div className="empty-state"><h2>Восстановим состояние квиза</h2><p className="muted">Запросите актуальный шаг с сервера.</p><button className="button primary" disabled={busy} onClick={onRefresh}>Обновить состояние<Icon name="refresh" /></button></div>}
    </article>
  </section>
}
