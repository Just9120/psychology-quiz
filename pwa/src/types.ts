export interface Account {
  ok: true
  email: string
  role?: 'owner' | 'student'
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
  content_kind_choices?: ('theory' | 'glossary' | 'case')[]
}

export interface Setup {
  quiz_mode: 'single' | 'selected_mix' | 'all' | 'adaptive'
  category_ids: number[]
  question_count: 5 | 10 | 15 | null
  difficulty: 'any' | 'easy' | 'medium' | 'hard'
  content_kinds?: ('theory' | 'glossary' | 'case')[]
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
  case_review?: { approach: string; conditions: string[]; ambiguity: string; option_rationales: string[] }
}

export interface ReviewItem {
  kind: 'quiz' | 'glossary'; question_id?: number; topic_id?: string; term_id?: string
  topic: string; due_on: string; is_due: boolean; correct_streak: number; reason: 'error' | 'scheduled' | 'new_edition' | 'unverified_order'
}
export interface ReviewQueue { ok: true; today: string; due_count: number; items: ReviewItem[] }
export interface MasteryItem { status: 'mastered' | 'insufficient_data'; correct_streak: number; question_id?: number; topic_id?: string; term_id?: string }
export interface MasteryGroup { ok: true; items: MasteryItem[]; mastered_count: number; assessed_count: number }
export interface MasteryOverview { ok: true; questions: MasteryGroup; terms: MasteryGroup }
export type GoalKind = 'study' | 'review' | 'reading'
export interface WeeklyGoal { goal_kind: GoalKind; weekly_target: number | null; completed: number; reached: boolean | null }
export interface GoalsOverview { ok: true; week_start: string; week_end_exclusive: string; goals: WeeklyGoal[] }
export interface Achievement { kind: 'new_topic' | 'corrected_error' | 'regularity'; evidence_key: string; earned_at: string }
export interface AchievementsOverview { ok: true; achievements: Achievement[] }
export interface DemoItem { id: 'theory' | 'term' | 'case'; kind: 'theory' | 'glossary' | 'case'; prompt: string; options: string[] }
export interface DemoItems { ok: true; items: DemoItem[] }
export interface DemoAnswer { ok: true; is_correct: boolean; correct_option_index: number; explanation: string; case_review?: NonNullable<Feedback['case_review']> }

export interface QuizState {
  ok: true
  runner_state: RunnerState
  recent_answer_feedback?: Feedback
  recent_answer_question?: Question
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
export interface ResetPreview {
  ok: true
  scope: 'all' | 'topic'
  topic: string | null
  topics: string[]
  revision: string
  questions: number
  answers: number
  attempts: number
  active_attempts: number
  glossary_attempts: number
  glossary_answers: number
}
export interface GlossaryTopic { topic_id: string; title: string; available_count: number }
export interface GlossaryQuestion {
  session_id: string; step_id: number; topic_id: string; topic_title: string
  order_index: number; total_questions: number; term: string
  options: { option_index: number; option_text: string }[]
}
export interface GlossaryFeedback {
  step_id: number; is_correct: boolean; selected_option_index: number; selected_option_text: string
  correct_option_index: number; correct_option_text: string; explanation: string
  answered_count: number; total_questions: number; has_next: boolean
}
export interface GlossaryState {
  state: 'idle' | 'in_progress' | 'feedback' | 'completed'
  session_id?: string; topic_id?: string; topic_title?: string; topic_ids?: string[]
  current_question?: GlossaryQuestion; feedback?: GlossaryFeedback
  result?: { score: number; total_questions: number }
}
export interface PracticeDay extends PracticeCounts { day: string }
export interface TopicProgress extends PracticeCounts { topic: string; days: PracticeDay[] }
export interface CurriculumProgress extends PracticeCounts { scope: string; title: string; days: PracticeDay[] }
export interface DisciplineProgress extends CurriculumProgress { topics: CurriculumProgress[]; unmapped_answers: number }
export interface ProgressOverview {
  ok: true
  summary: PracticeCounts & { attempts: number; finished: number }
  topics: TopicProgress[]
  days: PracticeDay[]
  curriculum?: { disciplines: DisciplineProgress[]; unmapped: CurriculumProgress }
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
  curriculum?: { discipline_id: string | null; discipline_title: string | null; topic_id: string | null; topic_title: string | null }
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
export type ReadingStatus = 'not_started' | 'in_progress' | 'read' | 'revisit' | 'skipped'
export type ReadingState = { literature_id: string; reading_status: ReadingStatus; progress_percent: number | null; updated_at: string }
export type LiteratureEntry = {
  id: string; topic_id: string; topic_title: string; module: string; year: number | null;
  source: { id: string; title: string; locator: string; citation: string };
  metadata_warnings: string[]; user_state: ReadingState | null;
}
export type LiteratureWork = { work_id: string; title: string; authors: string[]; type: string; entries: LiteratureEntry[] }
export type LiteratureCatalog = { ok: true; works: LiteratureWork[]; topics: { topic_id: string; title: string; module: string }[] }
