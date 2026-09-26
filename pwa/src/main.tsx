import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { takeInvitation, takeMailProof } from './proof'
import { registerServiceWorker } from './install'
import './styles.css'

const invitation = takeInvitation()
const proof = takeMailProof()
const root = createRoot(document.getElementById('root')!)
let generation = 0
root.render(<StrictMode><App key={generation} initialProof={proof} initialInvitation={invitation} /></StrictMode>)
window.addEventListener('hashchange', () => {
  if (!/^#(?:verify|recover|invite)=/.test(location.hash)) return
  const invited = takeInvitation()
  const next = takeMailProof()
  if (next || invited) root.render(<StrictMode><App key={++generation} initialProof={next} initialInvitation={invited} /></StrictMode>)
})
registerServiceWorker()
