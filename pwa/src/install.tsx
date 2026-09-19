import { useEffect, useState } from 'react'
import { Icon } from './Icon'

interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function InstallButton() {
  const [prompt, setPrompt] = useState<InstallEvent | null>(null)
  const [help, setHelp] = useState(false)
  const [installed, setInstalled] = useState(window.matchMedia('(display-mode: standalone)').matches)
  useEffect(() => {
    const capture = (event: Event) => { event.preventDefault(); setPrompt(event as InstallEvent) }
    const complete = () => { setInstalled(true); setPrompt(null); setHelp(false) }
    window.addEventListener('beforeinstallprompt', capture)
    window.addEventListener('appinstalled', complete)
    return () => { window.removeEventListener('beforeinstallprompt', capture); window.removeEventListener('appinstalled', complete) }
  }, [])
  if (installed) return <p className="installed-label"><Icon name="check" size={16} />Приложение установлено</p>
  return <div className="install-section"><button className="install-button" onClick={() => {
    if (prompt) void prompt.prompt().then(() => prompt.userChoice).catch(() => setHelp(true)).finally(() => setPrompt(null))
    else setHelp(current => !current)
  }}><Icon name="download" />Установить приложение</button>{help && <p className="install-help" role="status">В меню браузера выберите «Установить приложение» или «Добавить на главный экран». На iPhone эта команда находится в меню «Поделиться» Safari.</p>}</div>
}

export function registerServiceWorker() {
  if ('serviceWorker' in navigator && import.meta.env.PROD) {
    // Network-only learning: the worker caches only an unpersonalized offline page.
    void navigator.serviceWorker.register('/sw.js').catch(() => {})
  }
}
