/** Keep long conditions readable without turning the entire situation into a heading. */
export function QuestionPrompt({ text, number }: { text: string; number?: number }) {
  const long = text.length > 240 || text.includes('\n')
  return <div className="question-prompt">
    <h1 className="question-heading">{long ? number ? `Вопрос ${number}` : 'Условие вопроса' : text}</h1>
    {long && <p className="question-body">{text}</p>}
  </div>
}
