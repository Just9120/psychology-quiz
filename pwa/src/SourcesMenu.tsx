import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

export function SourcesMenu({ label, children }: { label: string; children: ReactNode }) {
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  return <div className="sources-menu" ref={root}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false) }}
    onKeyDown={event => {
      if (event.key === 'Escape' && open) {
        event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus()
      }
    }}>
    <button type="button" className="button secondary sources-trigger" ref={trigger}
      aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
      <span aria-hidden="true" className="sources-kebab">⋮</span>{label}
    </button>
    {open && <div id={id} className="sources-panel">{children}</div>}
  </div>
}
