import { useState } from 'react'
import { api } from './api'
import { Icon } from './Icon'
import type { Account } from './types'
import type { TaskProps } from './AuthScreen'

export function Onboarding({ account, busy, run, refresh }: TaskProps & { account: Account; refresh: () => Promise<void> }) {
  const [code, setCode] = useState('')
  const [newWarning, setNewWarning] = useState(false)
  return <section className="onboarding page-width"><span className="eyebrow">ПЕРЕД ПЕРВЫМ КВИЗОМ</span><h1>Ваш прогресс — с вами</h1>
    <p className="lead">Уже занимались в Telegram? Подключите прежнюю историю, чтобы продолжить здесь.</p>
    <div className="panel connect-panel"><span className="tile-icon"><Icon name="refresh" size={26} /></span><h2>Подключить Telegram</h2><p className="muted">Понадобится подтверждение в личном чате с вашим учебным ботом. Пароль Telegram вводить не нужно.</p>
      {!code && !account.link_confirmed && <button className="button primary" disabled={busy} onClick={() => void run(async () => { setCode((await api.linkStart()).code); await refresh() })}>{account.link_pending ? 'Получить новый код' : 'Получить код'}<Icon name="arrow" /></button>}
      {code && !account.link_confirmed && <div className="link-instructions"><ol><li>Скопируйте команду ниже.</li><li>Отправьте её учебному боту в личном чате.</li><li>Проверьте почту аккаунта в сообщении бота и подтвердите связь.</li></ol>
        <label className="field">Команда для бота<input readOnly value={`/link ${code}`} onFocus={event => event.currentTarget.select()} /></label>
        <div className="button-row"><button className="button primary" disabled={busy} onClick={() => void run(refresh)}>Я подтвердил в Telegram</button><button className="button quiet" disabled={busy} onClick={() => void run(async () => { setCode((await api.linkStart()).code); await refresh() })}>Новый код</button></div>
        <p className="hint">Код действует 10 минут. Не передавайте его другим людям.</p>
      </div>}
      {account.link_confirmed && account.link_target && <div className="notice-stack"><div className="notice"><Icon name="check" /><span>Telegram подтверждён: <strong>{account.link_target.display_name || account.link_target.username || 'Учебный аккаунт'}</strong>{account.link_target.username && ` (@${account.link_target.username})`}<br /><small>ID {account.link_target.telegram_id}</small></span></div>
        <button className="button primary" disabled={busy} onClick={() => void run(async () => { await api.linkComplete(); setCode(''); await refresh() })}>Подключить этот прогресс<Icon name="arrow" /></button></div>}
    </div>
    <div className="panel independent-panel"><h2>Начать без Telegram</h2><p className="muted">Создадим отдельный прогресс для этого аккаунта.</p>
      {!newWarning ? <button className="button secondary" disabled={busy} onClick={() => setNewWarning(true)}>Создать новый прогресс</button>
        : <><p className="warning-text">После этого объединить историю с прежним Telegram-прогрессом не получится. Если он вам нужен, подключите его выше.</p><div className="button-row"><button className="button primary" disabled={busy} onClick={() => void run(async () => { await api.newIdentity(); await refresh() })}>Начать с чистого листа</button><button className="button quiet" disabled={busy} onClick={() => setNewWarning(false)}>Назад</button></div></>}
    </div>
  </section>
}
