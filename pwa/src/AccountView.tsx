import { useState } from 'react'
import { api, ApiError } from './api'
import { Icon } from './Icon'
import type { Account } from './types'

export function AccountView({ account, busy, run, onAccount, onLearn, onReset }: {
  account: Account
  busy: boolean
  run: (operation: () => Promise<void>) => Promise<void>
  onAccount: (account: Account) => void
  onLearn: () => void
  onReset: () => void
}) {
  const [name, setName] = useState(account.display_name ?? '')
  const [saved, setSaved] = useState(false)
  const [uncertain, setUncertain] = useState(false)

  async function refresh() {
    const latest = await api.me()
    onAccount(latest)
    setName(latest.display_name ?? '')
    setSaved(false)
    setUncertain(false)
  }

  async function save() {
    try {
      const result = await api.setDisplayName(name)
      onAccount({ ...account, display_name: result.display_name })
      setName(result.display_name ?? '')
      setSaved(true)
    } catch (failure) {
      if (!(failure instanceof ApiError) || !failure.status || failure.status >= 500) setUncertain(true)
      throw failure
    }
  }

  return <section className="page-width account-page"><span className="eyebrow">ВАШ ПРОФИЛЬ</span><h1>Мой аккаунт</h1>
    <div className="panel"><h2>{account.display_name || account.email}</h2><p className="muted">{account.email} · Почта подтверждена</p>
      <form onSubmit={event => { event.preventDefault(); if (!busy && !uncertain) void run(save) }}>
        <label className="field">Имя в приложении<input value={name} maxLength={60} autoComplete="nickname" disabled={busy || uncertain} onChange={event => { setName(event.target.value); setSaved(false) }} placeholder="Как к вам обращаться" /></label>
        <p className="muted">Имя видно только в вашем профиле. Пустое поле уберёт его; имя в Telegram не изменится.</p>
        {uncertain ? <div className="notice" role="status">Сохранение не подтверждено. Обновите профиль перед новой попыткой.</div> : <button className="button secondary" type="submit" disabled={busy || name.trim() === (account.display_name ?? '')}>Сохранить имя</button>}
        {saved && <p role="status">Имя сохранено.</p>}
      </form>
      {uncertain && <button className="button secondary" disabled={busy} onClick={() => void run(refresh)}>Обновить профиль</button>}
      <hr /><p>{account.needs_identity ? 'Выберите, с каким прогрессом продолжить обучение.' : account.telegram_linked ? 'Прогресс связан с вашим Telegram-аккаунтом.' : 'Самостоятельный аккаунт с отдельным прогрессом.'}</p>
      <button className="button secondary" disabled={busy} onClick={onLearn}>К обучению<Icon name="arrow" /></button>
    </div>
    <div className="panel"><h2>Настройки учебного прогресса</h2><p className="muted">Можно сбросить результаты отдельной темы или всех тестов. Аккаунт и литература сохраняются.</p><button className="button secondary warning-text" disabled={busy || account.needs_identity} onClick={onReset}>Настроить сброс</button></div>
  </section>
}
