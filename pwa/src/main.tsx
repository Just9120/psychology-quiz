import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { takeMailProof } from './proof'
import { registerServiceWorker } from './install'
import './styles.css'

const proof = takeMailProof()
const root = createRoot(document.getElementById('root')!)
let generation = 0
root.render(<StrictMode><App key={generation} initialProof={proof} /></StrictMode>)
window.addEventListener('hashchange', () => {
  if (!/^#(?:verify|recover)=/.test(location.hash)) return
  const next = takeMailProof()
  if (next) root.render(<StrictMode><App key={++generation} initialProof={next} /></StrictMode>)
})
registerServiceWorker()
