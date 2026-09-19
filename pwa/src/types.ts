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
