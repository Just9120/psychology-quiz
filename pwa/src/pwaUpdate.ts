import { useSyncExternalStore } from 'react'

let waiting: ServiceWorker | null = null
const listeners = new Set<() => void>()
function publish(worker: ServiceWorker | null) {
  waiting = worker
  for (const listener of listeners) listener()
}
export function useWaitingUpdate() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, () => waiting)
}
export function watchUpdates(registration: ServiceWorkerRegistration) {
  const inspect = () => {
    if (registration.waiting && navigator.serviceWorker.controller) publish(registration.waiting)
  }
  inspect()
  registration.addEventListener('updatefound', () => {
    registration.installing?.addEventListener('statechange', inspect)
  })
  // Checking downloads a new worker, but never activates it or reloads the tab.
  const check = () => { if (document.visibilityState === 'visible') void registration.update().catch(() => {}) }
  window.addEventListener('focus', check)
  document.addEventListener('visibilitychange', check)
  window.setInterval(check, 5 * 60 * 1000)
}
export function activateUpdate(worker: ServiceWorker, reload = () => window.location.reload()) {
  // Other tabs may observe controllerchange; only an explicit click installs this listener.
  let reloaded = false
  const finish = () => {
    if (reloaded) return
    reloaded = true
    window.clearTimeout(timer)
    navigator.serviceWorker.removeEventListener('controllerchange', finish)
    reload()
  }
  const timer = window.setTimeout(finish, 5000)
  navigator.serviceWorker.addEventListener('controllerchange', finish)
  worker.postMessage({ type: 'APPLY_UPDATE' })
}
