export interface Account {
  ok: true
  email: string
  csrf_token: string
  needs_identity: boolean
  telegram_linked: boolean
  link_pending: boolean
  link_confirmed: boolean
  link_target: { telegram_id: number; username: string | null; display_name: string } | null
}

export interface SetupOptions {
  categories: { id: number; name: string }[]
  question_count_choices: (5 | 10 | 15 | 'all')[]
  difficulty_choices: ('any' | 'easy' | 'medium' | 'hard')[]
}

export interface Setup {
  quiz_mode: 'single' | 'selected_mix' | 'all'
  category_ids: number[]
  question_count: 5 | 10 | 15 | null
  difficulty: 'any' | 'easy' | 'medium' | 'hard'
}

export interface Question {
  session_id: number
  question_id: number
  question_text: string
  order_index: number
  total_questions: number
  options: { option_index: number; option_text: string }[]
}

export interface RunnerState {
  state: 'setup' | 'in_progress' | 'completed' | 'forbidden'
  status: string
  session: { session_id: number; session_status?: string } | null
  current_question?: Question
  progress?: { current_question_number: number; total_questions: number; answered_count: number }
  result?: { score: number; total_questions: number; percent: number; summary: string }
}

export interface Feedback {
  question_id?: number
  selected_option_index: number | null
  selected_option_text: string | null
  is_correct: boolean
  correct_option_index: number
  correct_option_text: string
  explanation: string | null
}

export interface QuizState {
  ok: true
  runner_state: RunnerState
  recent_answer_feedback?: Feedback
}

export interface Answer {
  session_id: number
  question_id: number
  selected_option_index: number
}

export interface AnswerResult {
  ok: true
  submission_status: string
  feedback?: Feedback
  runner_state?: RunnerState
}

export interface MailProof { purpose: 'verify' | 'recover'; token: string }

export interface PracticeCounts { answered: number; correct: number; accuracy: number | null }
export interface PracticeDay extends PracticeCounts { day: string }
export interface TopicProgress extends PracticeCounts { topic: string; days: PracticeDay[] }
export interface ProgressOverview {
  ok: true
  summary: PracticeCounts & { attempts: number; finished: number }
  topics: TopicProgress[]
  days: PracticeDay[]
}
export interface HistoryAttempt extends PracticeCounts {
  session_id: number
  status: string
  started_at: string
  finished_at: string | null
  total_questions: number
}
export interface SavedAnswer {
  answer_id: number
  question_id: number
  session_id: number
  answered_at: string
  is_correct: boolean
  question_text: string
  topic: string
  selected_option_text: string | null
  correct_option_text: string | null
  explanation: string | null
  snapshot_provenance: string
  content_sha256: string
}
export interface HistoryPage { ok: true; items: HistoryAttempt[]; next_before: number | null }
export interface AttemptPage { ok: true; attempt: HistoryAttempt; items: SavedAnswer[]; next_after: number | null }
export interface ErrorAnswer extends SavedAnswer { edition_state: 'current' | 'changed' | 'retired'; trainable: boolean }
export interface ErrorsPage {
  ok: true
  items: ErrorAnswer[]
  next_before: number | null
  total: number
  trainable_count: number
  latest_session_id: number | null
  has_active_attempt: boolean
}
