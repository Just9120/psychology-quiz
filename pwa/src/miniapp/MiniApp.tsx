import { useCallback, useEffect, useRef, useState } from 'react'
import { Brand } from '../Icon'
import { QuizSetup } from '../QuizSetup'
import { QuizView } from '../QuizView'
import { HomeworkView } from '../HomeworkView'
import { GlossaryView } from '../GlossaryView'
import { LearningView } from '../LearningView'
import type { Answer, Feedback, GlossaryState, GlossaryTopic, GoalKind, HomeworkAssignment, HomeworkCatalog, Question, RunnerState, Setup, SetupOptions } from '../types'
import { miniApi, MiniAppError, type MiniLiteratureItem, type MiniLiteratureTopic } from './api'
import { MiniLiterature } from './MiniLiterature'
import { MiniProgress } from './MiniProgress'
import type { ProgressOverview } from '../types'

type Page = 'quiz' | 'setup' | 'homework' | 'homeworkQuiz' | 'glossary' | 'literature' | 'learning' | 'progress' | 'privacy'
type Learning = { review: Awaited<ReturnType<typeof miniApi.review>>; mastery: Awaited<ReturnType<typeof miniApi.mastery>>; goals: Awaited<ReturnType<typeof miniApi.goals>>; achievements: Awaited<ReturnType<typeof miniApi.achievements>> }

const errors: Record<string, string> = {
  telegram_required: 'Откройте Mini App из Telegram.',
  no_questions: 'Для выбранных условий пока нет вопросов.',
  homework_unavailable: 'Этот тест пока недоступен. Обновите список заданий.',
  invalid_homework: 'Выберите задание из актуального списка.',
  no_reviews: 'На сегодня нет материалов для повторения.',
  active_attempt: 'Незавершённую попытку можно заменить только после подтверждения.',
  active_attempt_confirmation_required: 'Есть незавершённый квиз. Продолжите его или подтвердите замену.',
  attempt_changed: 'Попытка изменилась. Восстановите актуальное состояние.',
  active_glossary: 'Незавершённый тест по терминам можно заменить только после подтверждения.',
  practice_changed: 'Состояние изменилось. Восстановите сохранённую попытку.',
  network: 'Ответ сервера не получен. Восстановите состояние перед следующим действием.',
  invalid_confirmation: 'Подтверждение устарело. Начните удаление заново.',
  confirmation_expired: 'Время подтверждения истекло. Начните удаление заново.',
  linked_owner_requires_separate_flow: 'Данные связаны с аккаунтом PWA. Для него нужен отдельный порядок удаления.',
}
function message(error: unknown) { return error instanceof MiniAppError ? errors[error.code] ?? (error.status === 401 ? 'Проверка Telegram не прошла. Откройте Mini App заново.' : 'Не удалось выполнить действие. Попробуйте ещё раз.') : 'Не удалось выполнить действие.' }

export function MiniApp() {
  const [page, setPage] = useState<Page>('setup')
  const [options, setOptions] = useState<SetupOptions | null>(null)
  const [state, setState] = useState<RunnerState | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [feedbackQuestion, setFeedbackQuestion] = useState<Question | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState<Answer | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const [homeworkCatalog, setHomeworkCatalog] = useState<HomeworkCatalog | null>(null)
  const [homeworkId, setHomeworkId] = useState<string | null>(null)
  const [homeworkConfirmId, setHomeworkConfirmId] = useState<string | null>(null)
  const [glossary, setGlossary] = useState<GlossaryState | null>(null)
  const [glossaryTopics, setGlossaryTopics] = useState<GlossaryTopic[]>([])
  const [literatureItems, setLiteratureItems] = useState<MiniLiteratureItem[] | null>(null)
  const [literatureTopics, setLiteratureTopics] = useState<MiniLiteratureTopic[]>([])
  const [learning, setLearning] = useState<Learning | null>(null)
  const [progress, setProgress] = useState<ProgressOverview | null>(null)
  const [deletionToken, setDeletionToken] = useState<string | null>(null)
  const [deletionAcknowledged, setDeletionAcknowledged] = useState(false)
  const [deletionCompleted, setDeletionCompleted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [booting, setBooting] = useState(true)
  const [error, setError] = useState('')
  const lock = useRef(false)
  const reviewQuizSession = useRef<number | null>(null)
  const reviewGlossarySession = useRef<string | null>(null)
  const authorized = Boolean(window.Telegram?.WebApp?.initData)

  const run = useCallback(async (action: () => Promise<void>) => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await action() } catch (failure) { setError(message(failure)) }
    finally { lock.current = false; setBusy(false); setBooting(false) }
  }, [])
  function applyState(next: RunnerState, recoveredFeedback: Feedback | null = null,
                      recoveredQuestion: Question | null = null) {
    setState(next); setFeedback(recoveredFeedback)
    setFeedbackQuestion(recoveredQuestion?.question_id === recoveredFeedback?.question_id ? recoveredQuestion : null)
    setSelected(null); setPending(null); setUncertain(false)
    setPage(next.state === 'setup' ? 'setup' : 'quiz')
  }
  async function refreshQuiz() {
    const saved = await miniApi.state()
    const sameHomework = page === 'homeworkQuiz' && homeworkId && saved.runner_state.session?.session_id === state?.session?.session_id
    applyState(saved.runner_state, saved.runner_state.state === 'in_progress' ? saved.recent_answer_feedback ?? null : null,
      saved.runner_state.state === 'in_progress' ? saved.recent_answer_question ?? null : null)
    if (sameHomework) setPage('homeworkQuiz')
    else setHomeworkId(null)
  }
  async function loadHomework() {
    setHomeworkCatalog(await miniApi.homework()); setHomeworkConfirmId(null); setPage('homework')
  }
  async function startHomework(id: string, replace: boolean) {
    const current = await miniApi.state()
    const active = current.runner_state.state === 'in_progress' ? current.runner_state.session?.session_id ?? null : null
    if (active && !replace) { setHomeworkConfirmId(id); return }
    const result = await miniApi.startHomework(id, active, Boolean(active && replace))
    applyState(result.runner_state); setHomeworkId(id); setHomeworkConfirmId(null); setPage('homeworkQuiz')
  }
  async function resumeHomework(item: HomeworkAssignment) {
    const current = await miniApi.state()
    if (current.runner_state.session?.session_id !== item.active_session_id || current.runner_state.state !== 'in_progress') {
      await loadHomework(); throw new MiniAppError('attempt_changed', 409)
    }
    applyState(current.runner_state, current.recent_answer_feedback ?? null, current.recent_answer_question ?? null)
    setHomeworkId(item.id); setPage('homeworkQuiz')
  }
  async function loadInitial() {
    const [available, saved] = await Promise.all([miniApi.options(), miniApi.state()])
    setOptions(available.setup_options)
    applyState(saved.runner_state, saved.runner_state.state === 'in_progress' ? saved.recent_answer_feedback ?? null : null,
      saved.runner_state.state === 'in_progress' ? saved.recent_answer_question ?? null : null)
  }
  useEffect(() => {
    window.Telegram?.WebApp?.ready?.(); window.Telegram?.WebApp?.expand?.()
    if (!authorized) { setBooting(false); return }
    void run(loadInitial)
  // Mount once: user state is refreshed explicitly after any uncertain write.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function start(setup: Setup, confirmed: boolean) {
    try { setHomeworkId(null); applyState((await miniApi.setup({ ...setup, replace_active: confirmed,
      expected_session_id: confirmed ? state?.session?.session_id ?? null : null })).runner_state) }
    catch (failure) {
      if (failure instanceof MiniAppError && !failure.status) setUncertain(true)
      else if (failure instanceof MiniAppError && failure.status === 409) await refreshQuiz()
      throw failure
    }
  }
  async function answer(choice?: number) {
    const question = state?.current_question
    if (!pending && (!question || (selected === null && choice === undefined))) return
    const payload = pending ?? { session_id: question!.session_id, question_id: question!.question_id, selected_option_index: choice ?? selected! }
    setPending(payload)
    let result
    try { result = await miniApi.answer(payload) }
    catch (failure) {
      if (failure instanceof MiniAppError && !failure.status) {
        try {
          const saved = await miniApi.state()
          if (saved.runner_state.session?.session_id === payload.session_id &&
              saved.recent_answer_feedback?.question_id === payload.question_id) {
            setState(saved.runner_state); setFeedback(saved.recent_answer_feedback)
            setFeedbackQuestion(saved.recent_answer_question ?? question ?? null); setPending(null)
            return
          }
        } catch { /* Uncertain write: keep the exact payload for an idempotent retry. */ }
      }
      throw failure
    }
    if (result.feedback && result.runner_state) {
      setState(result.runner_state); setFeedback(result.feedback); setFeedbackQuestion(question ?? null); setPending(null)
    } else if (result.runner_state) {
      applyState(result.runner_state)
      setError('Состояние изменилось в другом окне. Восстановлена сохранённая попытка.')
    }
  }
  async function loadGlossary() {
    const [available, saved] = await Promise.all([miniApi.glossaryOptions(), miniApi.glossaryState()])
    setGlossaryTopics(available.topics); setGlossary(saved.glossary_state); setPage('glossary')
  }
  async function loadLiterature() {
    const [topics, items] = await Promise.all([miniApi.literatureTopics(), miniApi.literatureItems()])
    setLiteratureTopics(topics.literature_topics); setLiteratureItems(items.literature_items); setPage('literature')
  }
  async function loadLearning() {
    const [review, mastery, goals, achievements] = await Promise.all([miniApi.review(), miniApi.mastery(), miniApi.goals(), miniApi.achievements()])
    setLearning({ review, mastery, goals, achievements }); setPage('learning')
  }
  async function loadProgress() { setProgress(await miniApi.overview()); setPage('progress') }
  async function prepareDeletion() {
    const prepared = await miniApi.prepareLearningDataDeletion()
    setDeletionToken(prepared.confirmation_token)
    setDeletionAcknowledged(false)
    setDeletionCompleted(false)
  }
  async function confirmDeletion() {
    if (!deletionToken || !deletionAcknowledged) return
    await miniApi.confirmLearningDataDeletion(deletionToken)
    setDeletionToken(null); setDeletionAcknowledged(false); setDeletionCompleted(true)
    setFeedback(null); setProgress(null); setLearning(null); setHomeworkCatalog(null)
    setGlossary(null); setLiteratureItems(null)
    setHomeworkId(null); setHomeworkConfirmId(null)
    reviewQuizSession.current = null; reviewGlossarySession.current = null
    await loadInitial()
    setPage('privacy')
  }
  async function startReviewQuiz(replace: boolean) {
    if (!replace) reviewQuizSession.current = (await miniApi.state()).runner_state.session?.session_id ?? null
    try { applyState((await miniApi.startReviewQuiz(reviewQuizSession.current, replace)).runner_state) }
    catch (failure) {
      if (failure instanceof MiniAppError && (!failure.status || failure.status === 409)) await refreshQuiz()
      throw failure
    }
  }
  async function startReviewGlossary(topic: string, replace: boolean) {
    if (!replace) reviewGlossarySession.current = (await miniApi.glossaryState()).glossary_state.session_id ?? null
    try {
      const result = await miniApi.startReviewGlossary(topic, reviewGlossarySession.current, replace)
      setGlossary(result.glossary_state); setGlossaryTopics((await miniApi.glossaryOptions()).topics); setPage('glossary')
    } catch (failure) {
      if (failure instanceof MiniAppError && (!failure.status || failure.status === 409)) await loadGlossary()
      throw failure
    }
  }

  if (!authorized) return <main className="loading-screen"><Brand /><h1>Откройте в Telegram</h1><p>Для личного квиза требуется запуск Mini App из Telegram.</p></main>
  if (booting) return <main className="loading-screen"><Brand /><p role="status">Восстанавливаем ваши занятия…</p></main>
  return <div className="app-layout miniapp-layout"><a className="skip-link" href="#main-content">Перейти к содержимому</a>
    <aside className="sidebar"><Brand /><nav aria-label="Разделы Mini App">
      <button className="nav-item" onClick={() => setPage(state?.state === 'in_progress' || state?.state === 'completed' ? 'quiz' : 'setup')}>Квиз</button>
      <button className="nav-item" disabled={busy} onClick={() => void run(loadHomework)}>Домашние задания</button>
      <button className="nav-item" disabled={busy} onClick={() => void run(loadGlossary)}>Глоссарий</button>
      <button className="nav-item" disabled={busy} onClick={() => void run(loadLiterature)}>Литература</button>
      <button className="nav-item" disabled={busy} onClick={() => void run(loadProgress)}>Мой прогресс</button>
      <button className="nav-item" disabled={busy} onClick={() => void run(loadLearning)}>Повторение и цели</button>
      <button className="nav-item" disabled={busy} onClick={() => setPage('privacy')}>Мои данные</button>
      <a className="nav-item miniapp-privacy-link" href="https://telegram.org/privacy-tpa" target="_blank" rel="noopener noreferrer">Политика конфиденциальности</a>
    </nav></aside>
    <div className="workspace"><header className="topbar">Ваше пространство обучения · Telegram</header><main id="main-content" className="workspace-main" tabIndex={-1}>
      {error && <div role="alert" className="app-alert">{error} <button type="button" onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
      {page === 'privacy' ? <section className="page-width panel">
          <h1>Мои учебные данные</h1>
          <p>Можно удалить сохранённые ответы и попытки, отметки книг, цели, достижения и историю повторений. Доступ к боту и Mini App сохранится. Если Telegram связан с аккаунтом владельца PWA, удаление здесь недоступно.</p>
          {deletionCompleted && <p role="status">Учебные данные удалены. Вы можете начать обучение заново.</p>}
          {!deletionToken ? <button type="button" className="button secondary" disabled={busy} onClick={() => void run(prepareDeletion)}>Подготовить удаление</button>
            : <div className="panel">
                <h2>Подтвердите удаление</h2>
                <p>Это действие удалит вашу сохранённую историю обучения. Восстановить её из приложения нельзя.</p>
                <label><input type="checkbox" checked={deletionAcknowledged} onChange={event => setDeletionAcknowledged(event.target.checked)} /> Я понимаю, какие данные будут удалены</label>
                <div><button type="button" className="button" disabled={busy || !deletionAcknowledged} onClick={() => void run(confirmDeletion)}>Удалить мои учебные данные</button>
                  <button type="button" className="button secondary" disabled={busy} onClick={() => { setDeletionToken(null); setDeletionAcknowledged(false) }}>Отмена</button></div>
              </div>}
        </section>
        : page === 'homework' && homeworkCatalog ? <HomeworkView catalog={homeworkCatalog} busy={busy} confirmId={homeworkConfirmId} onStart={id => void run(() => startHomework(id, false))} onConfirm={id => void run(() => startHomework(id, true))} onResume={item => void run(() => resumeHomework(item))} onRefresh={() => void run(loadHomework)} />
        : page === 'homeworkQuiz' && state ? <QuizView state={state} feedback={feedback} feedbackQuestion={feedbackQuestion} selected={selected} pending={pending} busy={busy} onSelect={setSelected} onAnswer={choice => void run(() => answer(choice))} onNext={() => { setFeedback(null); setFeedbackQuestion(null); setSelected(null) }} onSetup={() => void run(loadHomework)} onRefresh={() => void run(refreshQuiz)} homeworkTitle={homeworkCatalog?.assignments.find(item => item.id === homeworkId)?.title ?? 'Домашнее задание'} />
        : page === 'literature' && literatureItems ? <MiniLiterature initial={literatureItems} topics={literatureTopics} busy={busy} run={run} />
        : page === 'progress' && progress ? <MiniProgress data={progress} busy={busy} onRefresh={() => void run(loadProgress)} />
        : page === 'glossary' && glossary ? <GlossaryView key={`${glossary.session_id}:${glossary.state}:${glossary.current_question?.step_id}`} initial={glossary} topics={glossaryTopics} busy={busy} run={run} client={miniApi} />
        : page === 'learning' && learning ? <LearningView {...learning} busy={busy} onRefresh={() => void run(loadLearning)} onSaveGoal={(kind: GoalKind, target: number) => void run(async () => { await miniApi.setGoal(kind, target); await loadLearning() })} onStartQuiz={replace => void run(() => startReviewQuiz(replace))} onStartGlossary={(topic, replace) => void run(() => startReviewGlossary(topic, replace))} />
        : uncertain ? <section className="page-width panel empty-state"><h1>Проверим сохранённое состояние</h1><p>Ответ сервера не получен. Перед новым квизом восстановите текущую попытку.</p><button className="button primary" disabled={busy} onClick={() => void run(refreshQuiz)}>Восстановить квиз</button></section>
        : !state || !options ? <section className="page-width panel empty-state"><h1>Не удалось загрузить обучение</h1><button className="button primary" disabled={busy} onClick={() => void run(loadInitial)}>Повторить загрузку</button></section>
        : page === 'setup' || state.state === 'setup' ? <QuizSetup options={options} busy={busy} activeSessionId={state.state === 'in_progress' ? state.session?.session_id ?? null : null} onStart={(setup, confirmed) => void run(() => start(setup, confirmed))} onResume={() => void run(refreshQuiz)} />
        : <QuizView state={state} feedback={feedback} feedbackQuestion={feedbackQuestion} selected={selected} pending={pending} busy={busy} onSelect={setSelected} onAnswer={choice => void run(() => answer(choice))} onNext={() => { setFeedback(null); setFeedbackQuestion(null); setSelected(null) }} onSetup={() => { setPage('setup'); setFeedback(null) }} onRefresh={() => void run(refreshQuiz)} />}
    </main></div>
  </div>
}
