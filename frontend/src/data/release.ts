/** 上线审查接口的类型：与后端 /api/release 返回结构保持一致。 */

export type ReviewCheck = {
  check: string
  passed: boolean
  detail: string
}

export type SampleRow = {
  id: number
  plan_id: number
  plan_name: string
  branch: string
  step_key: string
  step_name: string
  version: string
  batch: string
  status: string
  input: Record<string, unknown>[]
  output: Record<string, unknown>[]
  input_rows: number
  output_rows: number
  created_at: string
  verified_at: string
  review_id: number | null
}

export type ReviewRow = {
  id: number
  sample_id: number
  plan_id: number
  plan_name: string
  branch: string
  step_key: string
  step_name: string
  plan_version: string
  transform_version: string
  sample_batch: string
  status: string
  passed: boolean
  checks: ReviewCheck[]
  issues: string[]
  input_snapshot: Record<string, unknown>[]
  output_snapshot: Record<string, unknown>[]
  input_rows: number
  output_rows: number
  verified_at: string
}

export type PlanRow = {
  plan_id: number
  plan_name: string
  branch: string
  step_key: string
  step_name: string
  seq: number
  version: string
  status: string
  online_status: string
  input_table: string
  output_table: string
  production_table: string
  sample_status: string
  verified: boolean
  sample_id: number | null
  review_id: number | null
}

export type ChecklistStep = {
  step_key: string
  step_name: string
  seq: number
  current_plan_id: number | null
  current_version: string
  current_output_table: string
  candidate_plan_id: number | null
  candidate_version: string
  candidate_output_table: string
  sample_id: number | null
  sample_batch: string
  sample_status: string
  review_id: number | null
  verified: boolean
  gate_passed: boolean | null
  gate_reason: string
  decision: string
  adopted_plan_id: number | null
  adopted_version: string
  output_table: string
}

export type ChecklistBranch = {
  branch: string
  current_version: string
  target_version: string
  adopted_version: string
  ready: boolean
  reason: string
  production_table: string
  output_table: string
  plan_id: number | null
  plan_name: string
  steps: ChecklistStep[]
}

export type Checklist = {
  order_id: number
  order_no: string
  title: string
  generated_at: string
  branches: ChecklistBranch[]
  production_outputs: {
    branch: string
    production_table: string
    adopted_version: string
    output_table: string
    plan_id: number | null
    plan_name: string
  }[]
}

export type SubmitResult = {
  ok: boolean
  order_id: number
  order_no: string
  revision: number
  application_no: string
  status: string
  summary: string
  previous_versions: Record<string, string>
  adopted_versions: Record<string, string>
  checklist: Checklist
  message: string
}

export type FetchTableResult = {
  requested_table: string
  production_table: string
  branch: string
  adopted_version: string
  plan_id: number | null
  plan_name: string
  output_table: string
  executed: boolean
  skipped: boolean
  status: string
  row_count?: number
  reason?: string
  previous_version?: string
  previous_output_table?: string
  previous_executed_at?: string
  message: string
}

export type FetchRun = {
  ok: boolean
  batch_date: string
  application_no: string
  tables: FetchTableResult[]
  fetch_run: {
    id: number
    batch_date: string
    application_no: string
    requested_at: string
    requested_tables: string[]
    executed: number
    skipped: number
  }
  message: string
}

export type FetchRecord = {
  id: number
  run_id: number
  production_table: string
  branch: string
  batch_date: string
  plan_id: number | null
  plan_name: string
  plan_version: string
  output_table: string
  application_no: string
  row_count: number
  status: string
  executed_at: string
}

export type UsageBranch = {
  branch: string
  current_version: string
  versions: {
    version: string
    executions: number
    plan_ids: number[]
    output_tables: string[]
    batches: string[]
    records: FetchRecord[]
  }[]
}

export type UsageResult = {
  records: FetchRecord[]
  by_branch: UsageBranch[]
  total_executions: number
}

export type ReleaseOverview = {
  orders: {
    id: number
    order_no: string
    title: string
    status: string
    targets: Record<string, string>
    last_application_no: string
    submissions: number
  }[]
  live: Record<string, { version: string; plan_id: number | null; output_table: string; production_table: string }>
  pending_samples: { branch: string; step_key: string; step_name: string; version: string; sample_status: string }[]
  reviews: number
  fetch_executions: number
}

export type SampleTemplate = {
  ok: boolean
  plan_id: number
  batch: string
  input: Record<string, unknown>[]
  output: Record<string, unknown>[]
  message?: string
}

export type VerifyResult = {
  ok: boolean
  passed: boolean
  review: ReviewRow
  sample?: SampleRow
  message: string
}
