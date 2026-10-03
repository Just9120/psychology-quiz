export function BookSearch({ search }: { search?: { query: string; url: string } }) {
  if (!search) return null
  return <div className="literature-search">
    <h3>Поиск книги в интернете</h3>
    <label className="field">Поисковый запрос книги
      <textarea readOnly value={search.query} rows={3} />
    </label>
    <a href={search.url} target="_blank" rel="noopener noreferrer">Найти книгу для скачивания</a>
    <p className="muted">Результаты поиска не подтверждают доступность скачивания.</p>
  </div>
}
