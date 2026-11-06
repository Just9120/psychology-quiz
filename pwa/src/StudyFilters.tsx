import { ChoiceMenu } from './ChoiceMenu'
import { studyChoices, type StudyScope } from './studyScope'

export function StudyFilters({ choices, busy, onChange, topicLabel = 'Тема курса' }: {
  choices: ReturnType<typeof studyChoices>; busy: boolean; onChange: (scope: StudyScope) => void; topicLabel?: string
}) {
  const value = choices.scope
  return <div className="study-filters">
    <ChoiceMenu label="Модуль обучения" value={value.module} disabled={busy} onChange={module => onChange({ module, discipline: '', topic: '' })}
      options={[{ value: '', label: 'Все модули' }, ...choices.modules]} />
    <ChoiceMenu label="Дисциплина" value={value.discipline} disabled={busy} onChange={discipline => onChange({ ...value, discipline, topic: '' })}
      options={[{ value: '', label: 'Все дисциплины' }, ...choices.disciplines]} />
    <ChoiceMenu label={topicLabel} value={value.topic} disabled={busy} onChange={topic => onChange({ ...value, topic })}
      options={[{ value: '', label: 'Все темы курса' }, ...choices.topics]} />
  </div>
}
