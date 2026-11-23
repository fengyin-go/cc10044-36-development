import { fetchJson, request } from './client'
import type {
  Checklist,
  FetchRun,
  PlanRow,
  ReleaseOverview,
  ReviewRow,
  SampleRow,
  SampleTemplate,
  SubmitResult,
  UsageResult,
  VerifyResult,
} from '@/data/release'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  const payload = (await response.json()) as T & { detail?: string; message?: string }
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `接口返回 ${response.status}，数据未更新`)
  }
  return payload
}

export function loadReleaseOverview(): Promise<ReleaseOverview> {
  return fetchJson<ReleaseOverview>('/api/release/overview')
}

export async function listReleasePlans(branch?: string): Promise<PlanRow[]> {
  const query = branch ? `?branch=${encodeURIComponent(branch)}` : ''
  const payload = await fetchJson<{ items: PlanRow[] }>(`/api/release/plans${query}`)
  return payload.items
}

export async function loadChecklist(orderId = 1): Promise<Checklist> {
  return fetchJson<Checklist>(`/api/release/checklist?order_id=${orderId}`)
}

export async function loadOrder(orderId = 1): Promise<{
  id: number
  order_no: string
  status: string
  submissions: { revision: number; application_no: string; submitted_at: string; previous_versions: Record<string, string>; adopted_versions: Record<string, string> }[]
  latest_application: {
    application_no: string
    revision: number
    deployed_at: string
    adopted_versions: Record<string, string>
    pipeline_bindings: {
      pipeline_id: number
      pipeline_name: string
      branch: string
      adopted_version: string
      plan_id: number | null
      output_table: string
    }[]
  } | null
}> {
  return fetchJson(`/api/release/orders/${orderId}`)
}

export async function submitOrder(orderId = 1): Promise<SubmitResult> {
  return postJson<SubmitResult>(`/api/release/orders/${orderId}/submit`, {})
}

export async function deployOrder(orderId = 1): Promise<{
  ok: boolean
  application_no: string
  checklist: Checklist
  pipeline_bindings: {
    pipeline_id: number
    pipeline_name: string
    branch: string
    adopted_version: string
    plan_id: number | null
    output_table: string
  }[]
  message: string
}> {
  return postJson(`/api/release/orders/${orderId}/deploy`, {})
}

export function sampleTemplate(planId: number): Promise<SampleTemplate> {
  return fetchJson<SampleTemplate>(`/api/release/plans/${planId}/sample-template`)
}

export async function listSamples(filters: Record<string, string> = {}): Promise<SampleRow[]> {
  const query = new URLSearchParams(filters).toString()
  const payload = await fetchJson<{ items: SampleRow[] }>(`/api/release/samples?${query}`)
  return payload.items
}

export function ingestSample(
  payload: Record<string, unknown>,
): Promise<{ ok: boolean; sample: SampleRow; message: string }> {
  return postJson('/api/release/samples', payload)
}

export function verifySample(sampleId: number): Promise<VerifyResult> {
  return postJson<VerifyResult>(`/api/release/samples/${sampleId}/verify`, {})
}

export async function listReviews(filters: Record<string, string> = {}): Promise<ReviewRow[]> {
  const query = new URLSearchParams(filters).toString()
  const payload = await fetchJson<{ items: ReviewRow[] }>(`/api/release/reviews?${query}`)
  return payload.items
}

export function runFetch(tables: string[], batchDate: string): Promise<FetchRun> {
  return postJson<FetchRun>('/api/release/fetch', { tables, batch_date: batchDate })
}

export function loadUsage(tables: string[] = []): Promise<UsageResult> {
  const query = tables.length ? `?tables=${encodeURIComponent(tables.join(','))}` : ''
  return fetchJson<UsageResult>(`/api/release/usage${query}`)
}
