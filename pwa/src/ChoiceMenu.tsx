import { useEffect, useId, useRef, useState } from 'react'

export type Choice = { value: string; label: string; disabled?: boolean }

export function ChoiceMenu({ label, value, options, disabled = false, onChange }: {
  label: string; value: string; options: Choice[]; disabled?: boolean; onChange: (value: string) => void
}) {
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(value)
  const [above, setAbove] = useState(false)
  const [listHeight, setListHeight] = useState(320)
  const filtered = options.filter(option => option.label.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')))
  const enabled = filtered.filter(option => !option.disabled)
  const current = options.find(option => option.value === value)
  const searchable = options.length > 7

  function close(returnFocus = false) {
    setOpen(false); setQuery('')
    if (returnFocus) trigger.current?.focus()
  }
  function show(last = false) {
    if (disabled) return
    const bounds = trigger.current?.getBoundingClientRect()
    if (bounds) {
      const below = window.innerHeight - bounds.bottom - 16, top = bounds.top - 16
      const preferred = Math.min(320, window.innerHeight * .42) + (searchable ? 82 : 24)
      const flip = below < preferred && top > below
      setAbove(flip)
      setListHeight(Math.max(72, Math.min(320, (flip ? top : below) - (searchable ? 82 : 24))))
    }
    setQuery(''); setActive(current && !current.disabled ? value : (last ? options.filter(option => !option.disabled).at(-1)?.value : options.find(option => !option.disabled)?.value) ?? '')
    setOpen(true)
  }
  function choose(option: Choice) {
    if (disabled || option.disabled) return
    onChange(option.value); close(true)
  }
  function navigate(event: React.KeyboardEvent) {
    if (event.key === 'Escape') { event.preventDefault(); close(true); return }
    if (event.key === 'Tab') { close(); return }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      const index = enabled.findIndex(option => option.value === active)
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : event.key === 'ArrowDown' ? Math.min(index + 1, enabled.length - 1) : Math.max(index - 1, 0)
      if (enabled[next]) setActive(enabled[next].value)
    } else if (event.key === 'Enter' || (event.key === ' ' && event.target === trigger.current)) {
      event.preventDefault()
      const option = enabled.find(option => option.value === active)
      if (option) choose(option)
    }
  }

  useEffect(() => {
    if (!open) return
    if (searchable) search.current?.focus()
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) close() }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open, searchable])
  useEffect(() => { if (disabled) { setOpen(false); setQuery('') } }, [disabled])
  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView?.({ block: 'nearest' })
  }, [active, open])

  return <div className="choice-field" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) close() }}>
    <label id={`${id}-label`} htmlFor={`${id}-trigger`}>{label}</label>
    <button id={`${id}-trigger`} ref={trigger} type="button" role="combobox" aria-labelledby={`${id}-label`}
      className="choice-trigger" value={value} disabled={disabled} aria-expanded={open} aria-controls={`${id}-list`}
      aria-haspopup="listbox" aria-activedescendant={open && !searchable ? `${id}-option-${Math.max(0, options.findIndex(option => option.value === active))}` : undefined}
      onClick={() => open ? close() : show()} onKeyDown={event => {
        if (open) navigate(event)
        else if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) { event.preventDefault(); show(event.key === 'ArrowUp') }
      }}>
      <span>{current?.label ?? 'Выберите вариант'}</span><span aria-hidden="true" className="choice-chevron">⌄</span>
    </button>
    {open && <div className={`choice-popover${above ? ' choice-popover-above' : ''}`}>
      {searchable && <input ref={search} type="search" className="choice-search" aria-label={`Поиск: ${label}`} placeholder="Найти тему…"
        aria-controls={`${id}-list`} aria-activedescendant={enabled.some(option => option.value === active) ? `${id}-option-${options.findIndex(option => option.value === active)}` : undefined}
        value={query} onChange={event => { setQuery(event.target.value); setActive(options.find(option => !option.disabled && option.label.toLocaleLowerCase('ru').includes(event.target.value.trim().toLocaleLowerCase('ru')))?.value ?? '') }} onKeyDown={navigate} />}
      <div id={`${id}-list`} ref={list} role="listbox" aria-labelledby={`${id}-label`} className="choice-options" style={{ maxHeight: listHeight }}>
        {filtered.map(option => <div key={option.value} id={`${id}-option-${options.indexOf(option)}`} role="option" aria-selected={option.value === value}
          aria-disabled={option.disabled || undefined} data-value={option.value} data-active={option.value === active} className="choice-option"
          onPointerMove={() => { if (!option.disabled) setActive(option.value) }} onMouseDown={event => event.preventDefault()} onClick={() => choose(option)}>
          <span>{option.label}</span><span aria-hidden="true">{option.value === value ? '✓' : ''}</span>
        </div>)}
        {!filtered.length && <p className="choice-empty" role="status">Ничего не найдено. Попробуйте другой запрос.</p>}
      </div>
    </div>}
  </div>
}
