import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, errorMessage } from './api'
import { AuthScreen } from './AuthScreen'
import { Brand, Icon } from './Icon'
import { Onboarding } from './Onboarding'
import { QuizSetup } from './QuizSetup'
import { QuizView } from './QuizView'
import { InstallButton } from './install'
import type { Account, Answer, Feedback, MailProof, Question, QuizState, RunnerState, Setup, SetupOptions } from './types'

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
  const [view, setView] = useState<'quiz' | 'setup' | 'account'>('setup')
  const [booting, setBooting] = useState(!initialProof)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [offline, setOffline] = useState(!navigator.onLine)
  const lock = useRef(false)
  const alertRef = useRef<HTMLDivElement>(null)

  function clearPrivateState() {
    setAccount(null); setOptions(null); setState(null); setFeedback(null); setFeedbackQuestion(null)
    setSelected(null); setPending(null); setUncertainSetup(false); setView('setup')
  }

  function applyState(result: QuizState, resume = false) {
    setState(result.runner_state); setSelected(null); setPending(null); setUncertainSetup(false)
    setFeedback(resume && result.runner_state.state === 'in_progress' ? result.recent_answer_feedback ?? null : null)
    setFeedbackQuestion(null)
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
    lock.current = true; setBusy(true); setError('')
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

  async function refreshState() { applyState(await api.state(), true) }
  async function start(setup: Setup) {
    try { applyState(await api.setup(setup)) }
    catch (failure) { if (failure instanceof ApiError && !failure.status) setUncertainSetup(true); throw failure }
  }
  async function answer() {
    const question = state?.current_question
    if (!pending && (!question || selected === null)) return
    const payload = pending ?? { session_id: question!.session_id, question_id: question!.question_id, selected_option_index: selected! }
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
    <aside className="sidebar"><Brand /><div className="nav-heading">МОЁ ОБУЧЕНИЕ</div><nav aria-label="Основная навигация"><button className={view !== 'account' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => setView(state?.state === 'in_progress' || state?.state === 'completed' ? 'quiz' : 'setup')}><Icon name="book" />Квиз по психологии<span className="nav-dot" /></button><button className={view === 'account' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => setView('account')}><Icon name="user" />Мой аккаунт</button></nav><div className="sidebar-note"><Icon name="spark" /><p>Небольшие шаги.<br />Большое понимание.</p></div><InstallButton /><button className="logout" disabled={busy} onClick={() => void run(async () => { try { await api.logout() } finally { clearPrivateState() } })}><Icon name="logout" />Выйти</button></aside>
    <div className="workspace"><header className="topbar"><span>Ваше пространство обучения</span><div className="profile-badge"><span className="avatar">{account.email[0].toUpperCase()}</span><span>Личный аккаунт</span></div></header><main id="main-content" tabIndex={-1} className="workspace-main">
      {alert}{offline && <div className="offline-banner" role="status">Вы не в сети. Новые ответы требуют подтверждения сервера.</div>}
      {view === 'account' ? <section className="page-width account-page"><span className="eyebrow">ВАШ ПРОФИЛЬ</span><h1>Мой аккаунт</h1><div className="panel"><h2>{account.email}</h2><p className="muted">Почта подтверждена</p><hr /><p>{account.needs_identity ? 'Выберите, с каким прогрессом продолжить обучение.' : account.telegram_linked ? 'Прогресс связан с вашим Telegram-аккаунтом.' : 'Самостоятельный аккаунт с отдельным прогрессом.'}</p><button className="button secondary" disabled={busy} onClick={() => setView('setup')}>К обучению<Icon name="arrow" /></button></div><div className="mobile-install"><InstallButton /></div></section>
        : account.needs_identity ? <Onboarding account={account} busy={busy} run={run} refresh={loadAccount} />
          : uncertainSetup ? <section className="page-width panel empty-state"><h1>Проверим, создался ли квиз</h1><p className="muted">Ответ сервера не дошёл. Сначала восстановим состояние, чтобы не начинать две попытки.</p><button className="button primary" disabled={busy} onClick={() => void run(refreshState)}>Восстановить квиз<Icon name="refresh" /></button></section>
            : !options || !state ? <section className="page-width panel empty-state"><h1>Подключимся к вашему прогрессу</h1><button className="button primary" disabled={busy} onClick={() => void run(loadAccount)}>Повторить загрузку</button></section>
              : view === 'setup' || state.state === 'setup' ? <QuizSetup options={options} busy={busy} hasAttempt={state.state === 'in_progress'} onStart={setup => void run(() => start(setup))} onResume={() => void run(refreshState)} />
                : <QuizView state={state} feedback={feedback} feedbackQuestion={feedbackQuestion} selected={selected} pending={pending} busy={busy} onSelect={setSelected} onAnswer={() => void run(answer)} onNext={() => { setFeedback(null); setFeedbackQuestion(null); setSelected(null) }} onSetup={() => { setView('setup'); setFeedback(null) }} onRefresh={() => void run(refreshState)} />}
    </main><footer className="workspace-footer">PsychologyAtlas <span>·</span> В своём темпе, с пониманием</footer></div>
  </div>
}
