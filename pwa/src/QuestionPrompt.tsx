/** Keep long conditions readable without turning the entire situation into a heading. */
export function QuestionPrompt({ text, number }: { text: string; number?: number }) {
  // The runner separates the situation of a captured case with a blank line.
  // Older single-paragraph prompts can have an explicit final question instead.
  const paragraph = text.lastIndexOf('\n\n')
  const legacy = /[.!…][ \t]+([^.!?…\n]+\?\s*)$/u.exec(text)
  const legacySituation = legacy ? text.slice(0, legacy.index + 1) : ''
  const split = paragraph > 0 ? paragraph + 2
    : /(?:^|[^\p{L}])клиент(?:а|у|ом|е|ка)?(?:[^\p{L}]|$)/iu.test(legacySituation) && legacy
      ? text.length - legacy[1].length : 0
  if (split && text.slice(split).trim()) return <div className="question-prompt">
    <p className="question-body case-situation">{text.slice(0, split)}</p>
    <h1 className="question-heading">{text.slice(split)}</h1>
  </div>

  const long = text.length > 240 || text.includes('\n')
  return <div className="question-prompt">
    <h1 className="question-heading">{long ? number ? `Вопрос ${number}` : 'Условие вопроса' : text}</h1>
    {long && <p className="question-body">{text}</p>}
  </div>
}
