import { useRef, useState } from 'react'
import { activateUpdate, useWaitingUpdate } from './pwaUpdate'
import { Icon } from './Icon'

export function UpdateButton({ busy, checkActive }: { busy: boolean; checkActive: () => Promise<boolean> }) {
  const worker = useWaitingUpdate()
  const [open, setOpen] = useState(false)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')
  const button = useRef<HTMLButtonElement>(null)
  function close() { setOpen(false); setMessage(''); button.current?.focus() }
  async function apply() {
    setChecking(true); setMessage('')
    try {
      if (await checkActive()) {
        setMessage('Сначала подтвердите сохранение последнего действия или восстановите состояние. Затем можно обновить приложение.')
        return
      }
      if (worker) activateUpdate(worker)
    } catch {
      setMessage('Не удалось проверить сохранённое состояние. Попробуйте позже; приложение не обновлено.')
    } finally { setChecking(false) }
  }
  if (!worker) return null
  return <><button ref={button} className="update-button" disabled={busy} onClick={() => setOpen(true)}><Icon name="refresh" size={16} />Обновить<span className="update-dot" /></button>
    {open && <div className="update-overlay"><section role="dialog" aria-modal="true" aria-labelledby="update-title" className="panel update-dialog" onKeyDown={event => {
      if (event.key === 'Escape' && !checking) close()
      if (event.key === 'Tab') {
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
        const next = event.shiftKey ? buttons.at(-1) : buttons[0]
        if (document.activeElement === (event.shiftKey ? buttons[0] : buttons.at(-1))) { event.preventDefault(); next?.focus() }
      }
    }}><h2 id="update-title">Доступна новая версия</h2><p>Обновление перезагрузит страницу. Сохранённый прогресс останется; несохранённый ввод нужно завершить заранее.</p>
      {message && <p role="status">{message}</p>}<div className="button-row"><button className="button primary" disabled={checking || busy || Boolean(message)} onClick={() => void apply()}>Обновить сейчас</button><button autoFocus className="button secondary" disabled={checking} onClick={close}>{message ? 'Вернуться' : 'Позже'}</button></div>
    </section></div>}
  </>
}
