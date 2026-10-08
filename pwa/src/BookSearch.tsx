import { useEffect, useRef, useState } from 'react'

export function BookSearch({ search }: { search?: { query: string; url: string } }) {
  const input = useRef<HTMLTextAreaElement>(null)
  const generation = useRef(0)
  const [state, setState] = useState<'idle' | 'copying' | 'copied' | 'failed'>('idle')
  useEffect(() => { generation.current += 1; setState('idle'); return () => { generation.current += 1 } }, [search?.query])
  if (!search) return null
  const query = encodeURIComponent(search.query.replace(/\s+скачать$/u, ''))
  async function copy() {
    const request = generation.current
    setState('copying')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(search!.query)
      if (request !== generation.current) return
      setState('copied')
    } catch {
      if (request !== generation.current) return
      input.current?.focus(); input.current?.select(); setState('failed')
    }
  }
  return <div className="literature-search">
    <h3>Найти книгу</h3>
    <div className="provider-searches"><span>Поиск в каталогах</span><div className="button-row">
      <a className="provider-search" href={`https://www.litres.ru/search/?q=${query}`} target="_blank" rel="noopener noreferrer">Литрес ↗</a>
      <a className="provider-search" href={`https://mybook.ru/search/?q=${query}`} target="_blank" rel="noopener noreferrer">MyBook ↗</a>
      <a className="provider-search" href={`https://books.yandex.ru/search/all/${query}`} target="_blank" rel="noopener noreferrer">Яндекс Книги ↗</a>
    </div><p className="hint">Это поиск, а не подтверждённые версии книги. Сверьте автора и формат.</p></div>
    <label className="field">Поисковый запрос книги
      <textarea ref={input} readOnly value={search.query} rows={2} />
    </label>
    <div className="button-row"><button type="button" className="button secondary" disabled={state === 'copying'} onClick={() => void copy()}>{state === 'copied' ? 'Скопировано ✓' : 'Скопировать запрос'}</button>
      <a className="provider-search" href={search.url} target="_blank" rel="noopener noreferrer">Поиск в интернете ↗</a></div>
    <p className="hint" role="status">{state === 'failed' ? 'Автоматическое копирование недоступно. Запрос выделен — скопируйте его вручную.' : state === 'copied' ? 'Поисковый запрос скопирован.' : 'Результаты поиска не подтверждают доступность скачивания.'}</p>
  </div>
}
