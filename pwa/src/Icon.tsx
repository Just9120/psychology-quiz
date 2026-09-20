const paths: Record<string, string> = {
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12M18 6 6 18',
  book: 'M12 5C8 2 4 3 3 4v15c3-2 6-1 9 1m0-15c4-3 8-2 9-1v15c-3-2-6-1-9 1V5',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  logout: 'M10 4H4v16h6m4-13 5 5-5 5m-6-5h11',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3',
  refresh: 'M20 10a8 8 0 0 0-14-5L3 8m0-5v5h5m-4 6a8 8 0 0 0 14 5l3-3m0 5v-5h-5',
  chart: 'M4 3v17h17M8 15v-4m5 4V6m5 9V9',
}

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.book} /></svg>
}

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Icon name="book" size={25} /></span><span>Psychology<span className="brand-light">Atlas</span></span></div>
}
