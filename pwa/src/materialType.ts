const labels: Record<string, string> = { book: 'Книга', chapter: 'Глава', article: 'Статья', video: 'Видео', course_material: 'Учебный материал', other: 'Материал' }
export const materialType = (type?: string) => labels[type ?? ''] ?? 'Материал'
