export type Role = 'admin' | 'teacher' | 'student';
export type Difficulty = 'easy' | 'medium' | 'hard';
export type Visibility = 'public' | 'private' | 'hidden' | 'classroom';
export type SubmissionRetentionMode = 'latest' | 'best';
export type LanguageId = 'cpp17' | 'cpp20' | 'python3';

export interface AllowedUserItem {
  id: number;
  username: string;
  full_name: string;
  email?: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  roles: Role[];
  is_active?: boolean;
  stats?: {
    solved_count: number;
    submission_count: number;
  };
}

export interface ProblemSummary {
  id: number;
  code: string;
  title: string;
  difficulty: Difficulty;
  points: number;
  visibility: Visibility;
  submission_retention_mode?: SubmissionRetentionMode;
  allowed_user_count?: number;
  time_limit_ms: number;
  memory_limit_mb: number;
  tags: string[];
  ac_count: number;
  submission_count: number;
  ac_rate: number;
  user_status: 'solved' | 'attempted' | 'unsolved';
}

export interface ProblemDetail extends ProblemSummary {
  statement_md: string;
  input_description: string;
  output_description: string;
  constraints_md: string;
  sample_input: string;
  sample_output: string;
  explanation?: string | null;
  checker_type: 'standard' | 'strict' | 'float_tol' | 'custom';
  checker_language?: 'python3' | 'cpp17' | 'cpp20';
  checker_source?: string;
  testcase_count: number;
  samples: Array<{ id: number; name: string; input: string; output: string }>;
  recent_submissions: SubmissionSummary[];
  allowed_users?: AllowedUserItem[];
  allowed_user_ids?: number[];
  block_old_code?: boolean;
}

export interface AutoImportProblemResult {
  title: string;
  description: string;
  input_description: string;
  output_description: string;
  constraints: string;
  sample_input: string;
  sample_output: string;
  explanation: string;
  time_limit_ms: number;
  memory_limit_mb: number;
}

export interface TestcaseGroup {
  id: number;
  problem_id: number;
  name: string;
  points: number;
  order_index: number;
}

export interface TestcaseItem {
  id: number;
  problem_id: number;
  group_id: number | null;
  name: string;
  input_size_bytes: number;
  output_size_bytes: number;
  is_sample: boolean;
  is_hidden: boolean;
  order_index: number;
  input_preview?: string;
  output_preview?: string;
  input_data?: string;
  expected_output?: string;
}

export interface GeneratedTestItemPreview {
  index: number;
  name: string;
  profile: string;
  status: 'SUCCESS' | 'FAILED';
  input_preview: string;
  output_preview: string;
  input_size_bytes: number;
  output_size_bytes: number;
  execution_time_ms: number;
  memory_kb: number;
  error: string;
}

export interface GenerationBatchResponse {
  batch_id: string;
  problem_id: number;
  mode: string;
  requested_count: number;
  success_count: number;
  failed_count: number;
  duration_ms: number;
  seed: number;
  reference_compile_error: string;
  generator_compile_error: string;
  items: GeneratedTestItemPreview[];
}

export interface SubmissionSummary {
  id: number;
  user_id: number;
  username: string;
  problem_id: number;
  problem_code: string;
  problem_title: string;
  contest_id?: number | null;
  language: LanguageId;
  status: string;
  verdict: string;
  score: number;
  max_score: number;
  execution_time_ms: number;
  memory_kb: number;
  created_at: string;
  code_blocked?: boolean;
}

export interface ContestItem {
  id: number;
  title: string;
  description: string;
  start_time: string;
  end_time: string;
  visibility: Visibility;
  status: 'UPCOMING' | 'RUNNING' | 'ENDED';
  participant_count: number;
  is_registered: boolean;
  is_hidden?: boolean;
  block_old_code?: boolean;
  is_restricted?: boolean;
  penalty_minutes: number;
  freeze_before_end_minutes: number;
}

export interface ClassroomItem {
  id: number;
  name: string;
  description: string;
  join_code: string;
  teacher_username?: string;
  teacher_name?: string;
  student_count: number;
  assignment_count: number;
}
