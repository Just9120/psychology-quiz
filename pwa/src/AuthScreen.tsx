import { useState } from 'react'
import { api } from './api'
import { Brand, Icon } from './Icon'
import type { MailProof } from './types'

export interface TaskProps {
  busy: boolean
  run: (operation: () => Promise<void>) => Promise<void>
}

export function AuthScreen({ busy, run, proof, consumeProof, onLogin, onDemo }: TaskProps & {
  proof: MailProof | null; consumeProof: () => void; onLogin: () => Promise<void>; onDemo?: () => void
}) {
  const [mode, setMode] = useState<'login' | 'register' | 'recover'>(proof?.purpose === 'recover' ? 'recover' : 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [notice, setNotice] = useState('')
  const settingPassword = proof !== null
  const title = settingPassword ? (proof.purpose === 'verify' ? 'Создайте свой пароль' : 'Новый пароль')
    : mode === 'register' ? 'Начнём с вашей почты' : mode === 'recover' ? 'Восстановить доступ' : 'Рады видеть вас снова'
  const description = settingPassword ? 'Длинная фраза из 15–128 символов поможет защитить ваш прогресс.'
    : mode === 'register' ? 'Отправим ссылку для подтверждения. Доступ пока открыт владельцу пространства.'
      : mode === 'recover' ? 'Отправим ссылку на почту, если для неё доступно восстановление.'
        : 'Войдите, чтобы продолжить обучение с того места, где остановились.'

  async function submit() {
    if (proof) {
      if (proof.purpose === 'verify') await api.verify(proof.token, password)
      else await api.reset(proof.token, password)
      consumeProof(); setPassword(''); setMode('login'); setNotice('Пароль сохранён. Теперь можно войти.')
    } else if (mode === 'login') {
      await api.login(email, password)
      setPassword('')
      await onLogin()
    } else {
      if (mode === 'register') await api.register(email)
      else await api.recover(email)
      setNotice('Если для этой почты доступно действие, письмо уже отправлено. Проверьте входящие и папку «Спам».')
    }
  }

  return <div className="auth-layout">
    <aside className="auth-story">
      <Brand />
      <div className="story-content"><span className="eyebrow light">ВАШ АТЛАС ЗНАНИЙ</span>
        <h1>Понимать глубже.<br />Учиться в своём темпе.</h1>
        <p>Исследуйте психологию через вопросы, понятные объяснения и небольшие шаги каждый день.</p>
        <div className="orbit" aria-hidden="true"><span className="orbit-center">ψ</span><span className="orbit-dot one" /><span className="orbit-dot two" /><span className="orbit-dot three" /></div>
      </div>
      <span className="story-footer">Знания, к которым хочется возвращаться.</span>
    </aside>
    <main className="auth-main">
      <div className="auth-mobile-brand"><Brand /></div>
      <div className="auth-card"><span className="eyebrow">PSYCHOLOGYATLAS</span><h2>{title}</h2><p className="muted">{description}</p>
        {notice && <div className="notice" role="status"><Icon name="check" /><span>{notice}</span></div>}
        <form onSubmit={event => { event.preventDefault(); void run(submit) }}>
          {!settingPassword && <label className="field">Электронная почта<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" required disabled={busy} /></label>}
          {(mode === 'login' || settingPassword) && <label className="field">{settingPassword ? 'Новый пароль' : 'Пароль'}<input type="password" autoComplete={settingPassword ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} minLength={settingPassword ? 15 : undefined} maxLength={128} required disabled={busy} /></label>}
          <button className="button primary full" disabled={busy}>{busy ? 'Подождите…' : settingPassword ? 'Сохранить пароль' : mode === 'login' ? 'Войти в пространство' : 'Получить письмо'}<Icon name="arrow" /></button>
        </form>
        <div className="auth-links">
          {settingPassword ? <button disabled={busy} onClick={() => { consumeProof(); setMode('recover'); setPassword(''); setNotice('') }}>Запросить новую ссылку</button>
            : mode === 'login' ? <><button disabled={busy} onClick={() => { setMode('recover'); setNotice(''); setPassword('') }}>Забыли пароль?</button><button disabled={busy} onClick={() => { setMode('register'); setNotice(''); setPassword('') }}>Первый вход</button></>
              : <button disabled={busy} onClick={() => { setMode('login'); setNotice('') }}>Вернуться ко входу</button>}
        </div>
        {!settingPassword && onDemo && <button className="button secondary full" disabled={busy} onClick={onDemo}>Посмотреть демонстрацию</button>}
        {!settingPassword && <p className="muted">Новые студенческие аккаунты PWA пока не открыты. Демонстрация доступна без регистрации; Telegram-квиз доступен из Telegram.</p>}
        <p className="auth-note"><Icon name="book" size={16} />Ваш прогресс хранится в аккаунте — можно продолжить на другом устройстве.</p>
      </div>
    </main>
  </div>
}
