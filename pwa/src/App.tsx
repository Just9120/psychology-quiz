import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, errorMessage } from './api'
import { AuthScreen } from './AuthScreen'
import { AccountView } from './AccountView'
import { Brand, Icon } from './Icon'
import { Onboarding } from './Onboarding'
import { QuizSetup } from './QuizSetup'
import { QuizView } from './QuizView'
import { HomeworkView } from './HomeworkView'
import { ErrorsView, ProgressView } from './ProgressView'
import { OwnerStatsView } from './OwnerStatsView'
import { ResetView } from './ResetView'
import { LiteratureView } from './LiteratureView'
import { LearningView, loadLearning } from './LearningView'
import type { GoalKind } from './types'
import type { LiteratureCatalog } from './types'
import { GlossaryView } from './GlossaryView'
import type { GlossaryState, GlossaryTopic } from './types'
import type { ResetPreview } from './types'
import { InstallButton } from './install'
import type { Account, Answer, Feedback, MailProof, Question, QuizState, RunnerState, Setup, SetupOptions, ProgressOverview, HistoryPage, AttemptPage, ErrorsPage, OwnerStats } from './types'
import type { HomeworkAssignment, HomeworkCatalog } from './types'

export function App({ initialProof = null }: { initialProof?: MailProof | null }) {
  const [proof, setProof] = useState(initialProof)
  const [account, setAccount] = useState<Account | null>(null)
  const [options, setOptions] = useState<SetupOptions | null>(null)
  const [state, setState] = useState<RunnerState | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [feedbackQuestion, setFeedbackQuestion] = useState<Question | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState<Answer | null>(null)
  const [uncertainSetup, setUncertainSetup] = useState(false)
  const [view, setView] = useState<'quiz' | 'setup' | 'homework' | 'homeworkQuiz' | 'account' | 'progress' | 'errors' | 'reset' | 'glossary' | 'literature' | 'learning' | 'ownerStats'>('setup')
  const [homeworkCatalog, setHomeworkCatalog] = useState<HomeworkCatalog | null>(null)
  const [homeworkId, setHomeworkId] = useState<string | null>(null)
  const [homeworkConfirmId, setHomeworkConfirmId] = useState<string | null>(null)
  const [resetPreview, setResetPreview] = useState<ResetPreview | null>(null)
  const [glossary, setGlossary] = useState<GlossaryState | null>(null)
  const [glossaryTopics, setGlossaryTopics] = useState<GlossaryTopic[]>([])
  const [literature, setLiterature] = useState<LiteratureCatalog | null>(null)
  const [literatureLoad, setLiteratureLoad] = useState(0)
  const [learning, setLearning] = useState<Awaited<ReturnType<typeof loadLearning>> | null>(null)
  const [notice, setNotice] = useState('')
  const [progress, setProgress] = useState<ProgressOverview | null>(null)
  const [ownerStats, setOwnerStats] = useState<OwnerStats | null>(null)
  const [progressScope, setProgressScope] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryPage | null>(null)
  const [detail, setDetail] = useState<AttemptPage | null>(null)
  const [mistakes, setMistakes] = useState<ErrorsPage | null>(null)
  const [booting, setBooting] = useState(!initialProof)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [offline, setOffline] = useState(!navigator.onLine)
  const lock = useRef(false)
  const alertRef = useRef<HTMLDivElement>(null)
  const reviewQuizSession = useRef<number | null>(null)
  const reviewGlossarySession = useRef<string | null>(null)

  function clearPrivateState() {
    reviewQuizSession.current = null; reviewGlossarySession.current = null
    setAccount(null); setOptions(null); setState(null); setFeedback(null); setFeedbackQuestion(null)
    setSelected(null); setPending(null); setUncertainSetup(false); setView('setup')
    setProgress(null); setOwnerStats(null); setProgressScope(null); setHistory(null); setDetail(null); setMistakes(null)
    setResetPreview(null); setNotice(''); setGlossary(null); setGlossaryTopics([]); setLiterature(null); setLearning(null)
    setHomeworkCatalog(null); setHomeworkId(null); setHomeworkConfirmId(null)
  }

  function applyState(result: QuizState, resume = false) {
    setState(result.runner_state); setSelected(null); setPending(null); setUncertainSetup(false)
    setFeedback(resume && result.runner_state.state === 'in_progress' ? result.recent_answer_feedback ?? null : null)
    setFeedbackQuestion(resume && result.runner_state.state === 'in_progress' &&
      result.recent_answer_question?.question_id === result.recent_answer_feedback?.question_id
      ? result.recent_answer_question ?? null : null)
    setView(result.runner_state.state === 'setup' ? 'setup' : 'quiz')
  }

  async function loadAccount() {
    const current = await api.me()
    setAccount(current)
    if (!current.needs_identity) {
      const [available, saved] = await Promise.all([api.options(), api.state()])
      setOptions(available.setup_options); applyState(saved, true)
    }
  }

  const run = useCallback(async (operation: () => Promise<void>) => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try { await operation() }
    catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) clearPrivateState()
      setError(errorMessage(failure))
    } finally { lock.current = false; setBusy(false); setBooting(false) }
  }, [])

  useEffect(() => {
    if (initialProof) return
    const controller = new AbortController()
    let active = true
    void api.me(controller.signal).then(async current => {
      if (!active) return
      setAccount(current)
      if (!current.needs_identity) {
        const [available, saved] = await Promise.all([api.options(), api.state()])
        if (active) { setOptions(available.setup_options); applyState(saved, true) }
      }
    }).catch(failure => {
      if (!active) return
      if (failure instanceof ApiError && failure.status === 401) clearPrivateState()
      else if (!(failure instanceof ApiError && failure.code === 'aborted')) setError(errorMessage(failure))
    }).finally(() => { if (active) setBooting(false) })
    return () => { active = false; controller.abort() }
  }, [initialProof])

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    window.addEventListener('online', update); window.addEventListener('offline', update)
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) }
  }, [])
  useEffect(() => { if (error) alertRef.current?.focus() }, [error])

  async function refreshState() {
    const result = await api.state()
    const sameHomework = view === 'homeworkQuiz' && homeworkId && result.runner_state.session?.session_id === state?.session?.session_id
    applyState(result, true)
    if (sameHomework) setView('homeworkQuiz')
    else setHomeworkId(null)
  }
  async function loadHomework() {
    setHomeworkCatalog(await api.homework()); setHomeworkConfirmId(null); setView('homework')
  }
  async function startHomework(id: string, replace: boolean) {
    const current = await api.state()
    const active = current.runner_state.state === 'in_progress' ? current.runner_state.session?.session_id ?? null : null
    if (active && !replace) { setHomeworkConfirmId(id); return }
    const result = await api.startHomework(id, active, Boolean(active && replace))
    const selected = homeworkCatalog?.assignments.find(item => item.id === id)
    setState(result.runner_state); setHomeworkId(id); setHomeworkConfirmId(null)
    setFeedback(null); setFeedbackQuestion(null); setSelected(null); setPending(null)
    setView('homeworkQuiz')
    if (!selected) setHomeworkCatalog(await api.homework())
  }
  async function resumeHomework(item: HomeworkAssignment) {
    const result = await api.state()
    if (result.runner_state.session?.session_id !== item.active_session_id || result.runner_state.state !== 'in_progress') {
      await loadHomework(); throw new ApiError('attempt_changed', 409)
    }
    applyState(result, true); setHomeworkId(item.id); setView('homeworkQuiz')
  }
  async function loadProgress(scope: string | null = null) {
    const [summary, attempts] = await Promise.all([api.progress(), api.history(null, scope)])
    setProgress(summary); setHistory(attempts); setProgressScope(scope); setDetail(null); setView('progress')
  }
  async function loadErrors() { setMistakes(await api.errors()); setView('errors') }
  async function loadOwnerStats(period: OwnerStats['period'] = '7d') { setOwnerStats(await api.ownerStats(period)); setView('ownerStats') }
  async function loadGlossary() {
    const [available, current] = await Promise.all([api.glossaryOptions(), api.glossaryState()])
    setGlossaryTopics(available.topics); setGlossary(current.glossary_state); setView('glossary')
  }
  async function loadLiterature() { setLiterature(await api.literature()); setLiteratureLoad(value => value + 1); setView('literature') }
  async function loadLearningView() { setLearning(await loadLearning()); setView('learning') }
  async function saveGoal(kind: GoalKind, target: number) { await api.setGoal(kind, target); await loadLearningView(); setNotice('Недельная цель сохранена.') }
  async function startReviewQuiz(replace: boolean) {
    if (!replace) reviewQuizSession.current = (await api.state()).runner_state.session?.session_id ?? null
    try { applyState(await api.startReviewQuiz(reviewQuizSession.current, replace)) }
    catch (failure) {
      if (failure instanceof ApiError && (!failure.status || failure.status === 409)) await refreshState()
      throw failure
    }
  }
  async function startReviewGlossary(topic: string, replace: boolean) {
    if (!replace) reviewGlossarySession.current = (await api.glossaryState()).glossary_state.session_id ?? null
    try {
      const result = await api.startReviewGlossary(topic, reviewGlossarySession.current, replace)
      const available = await api.glossaryOptions()
      setGlossaryTopics(available.topics); setGlossary(result.glossary_state); setView('glossary')
    } catch (failure) {
      if (failure instanceof ApiError && (!failure.status || failure.status === 409)) await loadGlossary()
      throw failure
    }
  }
  async function loadReset() { setResetPreview(await api.resetPreview()); setView('reset') }
  async function afterReset() {
    setProgress(null); setHistory(null); setDetail(null); setMistakes(null); setResetPreview(null); setLearning(null)
    setState(null); setFeedback(null); setFeedbackQuestion(null); setPending(null); setSelected(null)
    setUncertainSetup(false); setView('progress')
    applyState(await api.state())
    await loadProgress()
    setGlossary(null); setNotice('Учебный прогресс сброшен.')
  }
  async function trainErrors(replace: boolean, count: number | null) {
    if (!mistakes) return
    try { applyState(await api.trainErrors(mistakes.latest_session_id, replace, count)) }
    catch (failure) {
      if (failure instanceof ApiError && (!failure.status || failure.code === 'practice_changed')) {
        setUncertainSetup(true); setView('setup')
      }
      throw failure
    }
  }
  async function start(setup: Setup, confirmed: boolean) {
    try { setHomeworkId(null); applyState(await api.setup({ ...setup, replace_active: confirmed,
      expected_session_id: confirmed ? state?.session?.session_id ?? null : null })) }
    catch (failure) {
      if (failure instanceof ApiError && !failure.status) setUncertainSetup(true)
      else if (failure instanceof ApiError && failure.status === 409) await refreshState()
      throw failure
    }
  }
  async function answer(choice?: number) {
    const question = state?.current_question
    if (!pending && (!question || (selected === null && choice === undefined))) return
    const payload = pending ?? { session_id: question!.session_id, question_id: question!.question_id, selected_option_index: choice ?? selected! }
    setPending(payload)
    const result = await api.answer(payload)
    if (result.feedback && result.runner_state) {
      setState(result.runner_state); setFeedback(result.feedback); setFeedbackQuestion(question ?? null); setPending(null)
    } else if (result.runner_state) {
      applyState({ ok: true, runner_state: result.runner_state }, true)
      setError('Квиз изменился в другом окне. Показали актуальное состояние.')
    } else throw new ApiError('unavailable')
  }

  const alert = error && <div className="app-alert" role="alert" tabIndex={-1} ref={alertRef}><Icon name="close" /><span>{error}</span><button aria-label="Скрыть сообщение" onClick={() => setError('')}><Icon name="close" size={16} /></button></div>
  if (booting) return <main className="loading-screen"><Brand /><span className="spinner" aria-hidden="true" /><p role="status">Открываем ваше пространство…</p></main>
  if (!account || proof) return <>{alert}<AuthScreen busy={busy} run={run} proof={proof} consumeProof={() => setProof(null)} onLogin={loadAccount} /></>

  return <div className="app-layout"><a className="skip-link" href="#main-content">Перейти к содержимому</a>
    <aside className="sidebar"><Brand /><div className="nav-heading">МОЁ ОБУЧЕНИЕ</div><nav aria-label="Основная навигация"><button className={view === 'quiz' || view === 'setup' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => setView(state?.state === 'in_progress' || state?.state === 'completed' ? 'quiz' : 'setup')}><Icon name="book" />Квиз по психологии<span className="nav-dot" /></button><button className={view === 'homework' || view === 'homeworkQuiz' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadHomework)}><Icon name="book" />Домашние задания</button><button className={view === 'glossary' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadGlossary)}><Icon name="book" />Глоссарий</button><button className={view === 'literature' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadLiterature)}><Icon name="book" />Литература</button><button className={view === 'progress' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadProgress)}><Icon name="chart" />Мой прогресс</button><button className={view === 'learning' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadLearningView)}><Icon name="refresh" />Повторение и цели</button><button className={view === 'errors' ? 'nav-item active' : 'nav-item'} disabled={busy || account.needs_identity} onClick={() => void run(loadErrors)}><Icon name="refresh" />Мои ошибки</button><button className={view === 'account' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => setView('account')}><Icon name="user" />Мой аккаунт</button>{account.role === 'owner' && <button className={view === 'ownerStats' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => void run(() => loadOwnerStats())}><Icon name="chart" />Статистика</button>}</nav><div className="sidebar-note"><Icon name="spark" /><p>Небольшие шаги.<br />Большое понимание.</p></div><InstallButton /><button className="logout" disabled={busy} onClick={() => void run(async () => { try { await api.logout() } finally { clearPrivateState() } })}><Icon name="logout" />Выйти</button></aside>
    <div className="workspace"><header className="topbar"><span>Ваше пространство обучения</span><div className="profile-badge"><span className="avatar">{(account.display_name || account.email)[0].toUpperCase()}</span><span>{account.display_name || 'Личный аккаунт'}</span></div></header><main id="main-content" tabIndex={-1} className="workspace-main">
      {alert}{notice && <p className="notice" role="status">{notice}</p>}{offline && <div className="offline-banner" role="status">Вы не в сети. Новые ответы требуют подтверждения сервера.</div>}
      {view === 'account' ? <><AccountView account={account} busy={busy} run={run} onAccount={setAccount} onLearn={() => setView('setup')} onReset={() => void run(loadReset)} /><div className="mobile-install"><InstallButton /></div></>
        : view === 'ownerStats' && account.role === 'owner' && ownerStats ? <OwnerStatsView data={ownerStats} busy={busy} onPeriod={period => void run(() => loadOwnerStats(period))} />
        : account.needs_identity ? <Onboarding account={account} busy={busy} run={run} refresh={loadAccount} />
          : view === 'homework' && homeworkCatalog ? <HomeworkView catalog={homeworkCatalog} busy={busy} confirmId={homeworkConfirmId} onStart={id => void run(() => startHomework(id, false))} onConfirm={id => void run(() => startHomework(id, true))} onResume={item => void run(() => resumeHomework(item))} onRefresh={() => void run(loadHomework)} />
          : view === 'homeworkQuiz' && state ? <QuizView state={state} feedback={feedback} feedbackQuestion={feedbackQuestion} selected={selected} pending={pending} busy={busy} onSelect={setSelected} onAnswer={choice => void run(() => answer(choice))} onNext={() => { setFeedback(null); setFeedbackQuestion(null); setSelected(null) }} onSetup={() => void run(loadHomework)} onRefresh={() => void run(refreshState)} homeworkTitle={homeworkCatalog?.assignments.find(item => item.id === homeworkId)?.title ?? 'Домашнее задание'} />
          : view === 'literature' && literature ? <LiteratureView key={literatureLoad} initial={literature} busy={busy} run={run} />
          : view === 'glossary' && glossary ? <GlossaryView key={`${glossary.session_id}:${glossary.state}:${glossary.current_question?.step_id}`} initial={glossary} topics={glossaryTopics} busy={busy} run={run} />
          : view === 'learning' && learning ? <LearningView {...learning} busy={busy} onRefresh={() => void run(loadLearningView)} onSaveGoal={(kind, target) => void run(() => saveGoal(kind, target))} onStartQuiz={replace => void run(() => startReviewQuiz(replace))} onStartGlossary={(topic, replace) => void run(() => startReviewGlossary(topic, replace))} />
          : view === 'reset' && resetPreview ? <ResetView initial={resetPreview} busy={busy} run={run} onCancel={() => setView('account')} onComplete={afterReset} />
          : view === 'progress' && progress && history ? <ProgressView scope={progressScope} onScope={scope => void run(async () => { const page = await api.history(null, scope); setHistory(page); setProgressScope(scope) })} data={progress} history={history} detail={detail} busy={busy} onRefresh={() => void run(() => loadProgress(progressScope))} onBack={() => setDetail(null)} onOpen={id => void run(async () => setDetail(await api.attempt(id)))} onMore={() => void run(async () => { const page = await api.history(history.next_before, progressScope); setHistory({ ...page, items: [...history.items, ...page.items] }) })} onMoreAnswers={() => void run(async () => { if (detail) { const page = await api.attempt(detail.attempt.session_id, detail.next_after); setDetail({ ...page, items: [...detail.items, ...page.items] }) } })} />
          : view === 'errors' && mistakes ? <ErrorsView data={mistakes} busy={busy} onRefresh={() => void run(loadErrors)} onResume={() => void run(refreshState)} onTrain={(replace, count) => void run(() => trainErrors(replace, count))} onMore={() => void run(async () => { const page = await api.errors(mistakes.next_before); setMistakes({ ...page, items: [...mistakes.items, ...page.items] }) })} />
          : uncertainSetup ? <section className="page-width panel empty-state"><h1>Проверим, создался ли квиз</h1><p className="muted">Ответ сервера не дошёл. Сначала восстановим состояние, чтобы не начинать две попытки.</p><button className="button primary" disabled={busy} onClick={() => void run(refreshState)}>Восстановить квиз<Icon name="refresh" /></button></section>
            : !options || !state ? <section className="page-width panel empty-state"><h1>Подключимся к вашему прогрессу</h1><button className="button primary" disabled={busy} onClick={() => void run(loadAccount)}>Повторить загрузку</button></section>
              : view === 'setup' || state.state === 'setup' ? <QuizSetup options={options} busy={busy} activeSessionId={state.state === 'in_progress' ? state.session?.session_id ?? null : null} onStart={(setup, confirmed) => void run(() => start(setup, confirmed))} onResume={() => void run(refreshState)} />
                : <QuizView state={state} feedback={feedback} feedbackQuestion={feedbackQuestion} selected={selected} pending={pending} busy={busy} onSelect={setSelected} onAnswer={choice => void run(() => answer(choice))} onNext={() => { setFeedback(null); setFeedbackQuestion(null); setSelected(null) }} onSetup={() => { setView('setup'); setFeedback(null) }} onRefresh={() => void run(refreshState)} />}
    </main><footer className="workspace-footer">PsychologyAtlas <span>·</span> В своём темпе, с пониманием</footer></div>
  </div>
}
