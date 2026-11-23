<template>
  <section class="page release-page">
    <header class="page-head">
      <div>
        <h2>流水线上线审查</h2>
        <p class="page-desc">
          按转换步骤读入样本并校验输出，生成上线阶段清单；ETL 部署按清单决定每个分支下一次采用的方案版本和输出数据表。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="refresh" type="button" @click="reloadAll">刷新</button>
        <button class="btn primary" data-testid="submit-order" type="button" :disabled="busy" @click="submitOrder">
          提交上线单
        </button>
        <button class="btn" data-testid="deploy-order" type="button" :disabled="busy" @click="deployOrder">
          ETL 接收上线请求
        </button>
      </div>
    </header>

    <p v-if="message" class="notice" data-testid="release-message">{{ message }}</p>
    <p v-if="errorMessage" class="error-text" data-testid="release-error">{{ errorMessage }}</p>

    <div class="stat-row">
      <article v-for="card in summaryCards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <section class="release-block">
      <h3>上线阶段清单</h3>
      <p class="hint">
        上线单 {{ checklist?.order_no || order.order_no }}：目标版本
        <template v-for="(version, branch) in order.targets" :key="branch">
          <span class="tag">{{ branch }} → {{ version }}</span>
        </template>
        清单只推进核验通过的分支，样本缺失或未通过的步骤保持现行版本。
      </p>
      <div v-for="branch in checklist?.branches || []" :key="branch.branch" class="branch-card" :data-testid="`branch-${branch.branch}`">
        <header class="branch-head">
          <strong>{{ branch.branch }}分支</strong>
          <span class="tag">现行 {{ branch.current_version }}</span>
          <span class="tag" :class="{ 'tag-ok': branch.ready, 'tag-warn': !branch.ready }">
            本次采用 {{ branch.adopted_version }}
          </span>
          <span class="muted">生产表 {{ branch.production_table }} → 输出 {{ branch.output_table }}</span>
        </header>
        <p class="hint">{{ branch.reason }}</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>阶段</th>
              <th>步骤</th>
              <th>现行版本 / 输出表</th>
              <th>候选版本 / 输出表</th>
              <th>样本状态</th>
              <th>门禁</th>
              <th>结论</th>
              <th>采用版本 / 输出表</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="step in branch.steps"
              :key="step.step_key"
              :data-testid="`step-${branch.branch}-${step.step_key}`"
              :data-sample-status="step.sample_status"
            >
              <td>{{ step.seq }}</td>
              <td>{{ step.step_name }}</td>
              <td>{{ step.current_version }} / {{ step.current_output_table }}</td>
              <td>{{ step.candidate_version }} / {{ step.candidate_output_table }}</td>
              <td>
                <span :class="step.verified ? 'tag-ok' : 'tag-warn'">{{ step.sample_status }}</span>
                <span v-if="step.sample_id" class="muted"> #{{ step.sample_id }}</span>
              </td>
              <td>{{ step.gate_passed === null ? '—' : step.gate_passed ? '同版清洗已通过' : step.gate_reason }}</td>
              <td>{{ step.decision }}</td>
              <td>{{ step.adopted_version }} / {{ step.output_table }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="release-block">
      <h3>样本核验</h3>
      <p class="hint">核验记录会固化当时的输入、输出和转换版本；没有样本的步骤保持“样本缺失”，不会被标成已核验。</p>
      <table class="data-table">
        <thead>
          <tr>
            <th>方案</th>
            <th>分支 / 步骤</th>
            <th>版本</th>
            <th>上线状态</th>
            <th>样本状态</th>
            <th>核验记录</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="plan in plans" :key="plan.plan_id" :data-testid="`plan-${plan.plan_id}`">
            <td>{{ plan.plan_name }}</td>
            <td>{{ plan.branch }} / {{ plan.step_name }}</td>
            <td>{{ plan.version }}</td>
            <td>{{ plan.online_status }}</td>
            <td>
              <span :class="plan.verified ? 'tag-ok' : 'tag-warn'">{{ plan.sample_status }}</span>
            </td>
            <td>
              <button v-if="plan.review_id" class="link" type="button" @click="showReview(plan.review_id)">
                #{{ plan.review_id }}
              </button>
              <span v-else>—</span>
            </td>
            <td class="row-actions">
              <button class="link" :data-testid="`ingest-${plan.plan_id}`" type="button" @click="openSample(plan)">
                录入样本
              </button>
              <button
                v-if="plan.sample_id && !plan.verified"
                class="link"
                :data-testid="`verify-${plan.sample_id}`"
                type="button"
                @click="verifyExisting(plan.sample_id)"
              >
                核验样本 #{{ plan.sample_id }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="release-block">
      <h3>上线单提交记录</h3>
      <p class="hint">
        同一张上线单可以多次提交，每次提交固化当时的阶段版本；已按某版本处理过的批次不会重复执行。
      </p>
      <table class="data-table" data-testid="order-history">
        <thead>
          <tr><th>提交批次</th><th>提交时间</th><th>提交前版本</th><th>提交后采用版本</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in orderDetail?.submissions || []" :key="item.application_no" :data-testid="`submission-${item.revision}`">
            <td>{{ item.application_no }}</td>
            <td>{{ item.submitted_at }}</td>
            <td>{{ formatVersions(item.previous_versions) }}</td>
            <td>{{ formatVersions(item.adopted_versions) }}</td>
          </tr>
          <tr v-if="!orderDetail?.submissions?.length">
            <td colspan="4" class="empty-state">尚未提交上线单</td>
          </tr>
        </tbody>
      </table>
      <p v-if="orderDetail?.latest_application?.pipeline_bindings?.length" class="hint" data-testid="deploy-bindings">
        ETL 部署最近一次接收：{{ orderDetail.latest_application.application_no }} / {{ orderDetail.latest_application.deployed_at }}；
        <span v-for="bind in orderDetail.latest_application.pipeline_bindings" :key="bind.pipeline_id" class="tag">
          {{ bind.pipeline_name }} · {{ bind.branch }} {{ bind.adopted_version }} → {{ bind.output_table }}
        </span>
      </p>
    </section>

    <section class="release-block">
      <h3>取数核对</h3>
      <form class="filter-bar" @submit.prevent="runFetch">
        <label class="filter-item">
          <span>数据表（逗号分隔）</span>
          <input v-model="fetchTables" data-testid="fetch-tables" placeholder="dws_order_daily,dws_access_daily" />
        </label>
        <label class="filter-item">
          <span>批次</span>
          <input v-model="fetchBatch" data-testid="fetch-batch" placeholder="2026-11-21" />
        </label>
        <button class="btn primary" data-testid="run-fetch" type="submit" :disabled="busy">发起取数</button>
      </form>
      <table v-if="fetchRun" class="data-table" data-testid="fetch-result">
        <thead>
          <tr>
            <th>请求表</th>
            <th>分支</th>
            <th>采用的阶段版本</th>
            <th>输出数据表</th>
            <th>执行情况</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in fetchRun.tables" :key="index" :data-testid="`fetch-${item.branch}-${item.adopted_version}`">
            <td>{{ item.requested_table }}</td>
            <td>{{ item.branch }}</td>
            <td>{{ item.adopted_version }}</td>
            <td>{{ item.output_table || '—' }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.message }}</td>
          </tr>
        </tbody>
      </table>

      <h4>使用记录（按分支/版本）</h4>
      <div v-for="branch in usage?.by_branch || []" :key="branch.branch" class="branch-card" :data-testid="`usage-${branch.branch}`">
        <header class="branch-head">
          <strong>{{ branch.branch }}分支</strong>
          <span class="tag">当前 {{ branch.current_version }}</span>
        </header>
        <table class="data-table">
          <thead>
            <tr><th>版本</th><th>执行次数</th><th>输出表</th><th>批次</th><th>最近执行</th></tr>
          </thead>
          <tbody>
            <tr v-for="version in branch.versions" :key="version.version" :data-testid="`usage-${branch.branch}-${version.version}`">
              <td>{{ version.version }}</td>
              <td>{{ version.executions }}</td>
              <td>{{ version.output_tables.join('、') }}</td>
              <td>{{ version.batches.join('、') }}</td>
              <td>{{ version.records[version.records.length - 1]?.executed_at || '—' }}</td>
            </tr>
            <tr v-if="!branch.versions.length">
              <td colspan="5" class="empty-state">该分支还没有取数记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="sampleForm" class="modal-backdrop" data-testid="sample-modal">
      <form class="modal" @submit.prevent="saveSample">
        <h3>录入并核验样本 · {{ sampleForm.planName }}（{{ sampleForm.version }}）</h3>
        <p class="hint">
          修改样本后提交，核验记录会保存本次输入、输出和转换版本。
          <template v-if="sampleForm.templateMessage">{{ sampleForm.templateMessage }}</template>
        </p>
        <label class="create-field">
          <span>样本批次</span>
          <input v-model="sampleForm.batch" data-testid="sample-batch" required />
        </label>
        <label class="create-field">
          <span>输入样本（JSON 数组）</span>
          <textarea v-model="sampleForm.input" data-testid="sample-input" rows="7" class="json-input" required />
        </label>
        <label class="create-field">
          <span>输出样本（JSON 数组）</span>
          <textarea v-model="sampleForm.output" data-testid="sample-output" rows="7" class="json-input" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="sampleForm = null">取消</button>
          <button class="btn primary" data-testid="save-sample" type="submit" :disabled="busy">保存并核验</button>
        </div>
      </form>
    </div>

    <div v-if="reviewDetail" class="modal-backdrop" data-testid="review-modal">
      <div class="modal">
        <h3>核验记录 #{{ reviewDetail.id }}</h3>
        <dl class="review-meta">
          <dt>转换版本</dt><dd>{{ reviewDetail.transform_version }}</dd>
          <dt>步骤</dt><dd>{{ reviewDetail.branch }} / {{ reviewDetail.step_name }}</dd>
          <dt>结论</dt><dd>{{ reviewDetail.status }}</dd>
          <dt>核验时间</dt><dd>{{ reviewDetail.verified_at }}</dd>
        </dl>
        <table class="data-table">
          <thead><tr><th>校验项</th><th>结果</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="check in reviewDetail.checks" :key="check.check">
              <td>{{ check.check }}</td>
              <td>{{ check.passed ? '通过' : '未通过' }}</td>
              <td>{{ check.detail }}</td>
            </tr>
          </tbody>
        </table>
        <h4>核验时的输入快照</h4>
        <pre class="json-view">{{ pretty(reviewDetail.input_snapshot) }}</pre>
        <h4>核验时的输出快照</h4>
        <pre class="json-view">{{ pretty(reviewDetail.output_snapshot) }}</pre>
        <div class="page-actions">
          <button class="btn" type="button" @click="reviewDetail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  deployOrder as applyDeploy,
  ingestSample,
  listReleasePlans,
  listReviews,
  loadChecklist,
  loadOrder,
  loadReleaseOverview,
  loadUsage,
  runFetch as applyFetch,
  sampleTemplate,
  submitOrder as applySubmit,
  verifySample,
} from '@/api/release-service'
import type { Checklist, FetchRun, PlanRow, ReleaseOverview, ReviewRow, UsageResult } from '@/data/release'

type OrderDetail = Awaited<ReturnType<typeof loadOrder>>

const overview = ref<ReleaseOverview | null>(null)
const checklist = ref<Checklist | null>(null)
const orderDetail = ref<OrderDetail | null>(null)
const plans = ref<PlanRow[]>([])
const reviews = ref<ReviewRow[]>([])
const usage = ref<UsageResult | null>(null)
const fetchRun = ref<FetchRun | null>(null)
const fetchTables = ref('dws_order_daily,dws_access_daily')
const fetchBatch = ref('2026-11-21')
const busy = ref(false)
const message = ref('')
const errorMessage = ref('')

const sampleForm = ref<null | {
  planId: number
  planName: string
  version: string
  batch: string
  input: string
  output: string
  templateMessage: string
}>(null)
const reviewDetail = ref<ReviewRow | null>(null)

const order = computed(() => overview.value?.orders[0] ?? {
  id: 1,
  order_no: 'REL-20261121-01',
  title: '订单与访问双分支上线单',
  status: '草稿',
  targets: {} as Record<string, string>,
  last_application_no: '',
  submissions: 0,
})

const summaryCards = computed(() => {
  const live = overview.value?.live ?? {}
  return [
    { label: '上线单状态', value: order.value.status },
    { label: '订单现行版本', value: live['订单']?.version ?? '—' },
    { label: '访问现行版本', value: live['访问']?.version ?? '—' },
    { label: '待补样本步骤', value: overview.value?.pending_samples.length ?? 0 },
  ]
})

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function formatVersions(versions: Record<string, string>): string {
  const entries = Object.entries(versions || {})
  return entries.length ? entries.map(([branch, version]) => `${branch} ${version}`).join('；') : '—'
}

function describeError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

async function reloadAll() {
  errorMessage.value = ''
  try {
    const [overviewPayload, checklistPayload, orderPayload, planRows, reviewRows, usagePayload] = await Promise.all([
      loadReleaseOverview(),
      loadChecklist(1),
      loadOrder(1),
      listReleasePlans(),
      listReviews(),
      loadUsage(),
    ])
    overview.value = overviewPayload
    checklist.value = checklistPayload
    orderDetail.value = orderPayload
    plans.value = planRows
    reviews.value = reviewRows
    usage.value = usagePayload
  } catch (error) {
    errorMessage.value = describeError(error, '上线审查数据读取失败')
  }
}

async function submitOrder() {
  busy.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const result = await applySubmit(1)
    message.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = describeError(error, '上线单提交失败')
  } finally {
    busy.value = false
  }
}

async function deployOrder() {
  busy.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const result = await applyDeploy(1)
    message.value = `${result.message}：${result.pipeline_bindings.map((item) => `${item.branch}=${item.adopted_version}@${item.output_table}`).join('；')}`
    await reloadAll()
  } catch (error) {
    errorMessage.value = describeError(error, '部署接收失败')
  } finally {
    busy.value = false
  }
}

async function openSample(plan: PlanRow) {
  errorMessage.value = ''
  try {
    const template = await sampleTemplate(plan.plan_id)
    sampleForm.value = {
      planId: plan.plan_id,
      planName: plan.plan_name,
      version: plan.version,
      batch: template.batch || '2026-11-21',
      input: pretty(template.input ?? []),
      output: pretty(template.output ?? []),
      templateMessage: template.message ?? '',
    }
  } catch (error) {
    errorMessage.value = describeError(error, '样本模板读取失败')
  }
}

async function saveSample() {
  if (!sampleForm.value) return
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    let inputRows: unknown
    let outputRows: unknown
    try {
      inputRows = JSON.parse(sampleForm.value.input)
      outputRows = JSON.parse(sampleForm.value.output)
    } catch {
      throw new Error('样本必须是合法的 JSON 数组')
    }
    const saved = await ingestSample({
      plan_id: sampleForm.value.planId,
      batch: sampleForm.value.batch,
      input: inputRows,
      output: outputRows,
    })
    const review = await verifySample(saved.sample.id)
    message.value = review.message
    sampleForm.value = null
    await reloadAll()
  } catch (error) {
    errorMessage.value = describeError(error, '样本核验失败')
  } finally {
    busy.value = false
  }
}

async function verifyExisting(sampleId: number) {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const review = await verifySample(sampleId)
    message.value = review.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = describeError(error, '样本核验失败')
  } finally {
    busy.value = false
  }
}

function showReview(reviewId: number) {
  reviewDetail.value = reviews.value.find((row) => row.id === reviewId) ?? null
}

async function runFetch() {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const tables = fetchTables.value.split(',').map((item) => item.trim()).filter(Boolean)
    fetchRun.value = await applyFetch(tables, fetchBatch.value)
    message.value = fetchRun.value.message
    usage.value = await loadUsage()
    overview.value = await loadReleaseOverview()
    checklist.value = await loadChecklist(1)
  } catch (error) {
    errorMessage.value = describeError(error, '取数失败')
  } finally {
    busy.value = false
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.release-block { margin-top: 20px; }
.release-block h3 { margin: 0 0 6px; font-size: 15px; }
.release-block h4 { margin: 16px 0 6px; font-size: 13px; }
.hint { color: var(--muted); font-size: 12px; margin: 4px 0 10px; }
.muted { color: var(--muted); font-size: 12px; }
.branch-card { border: 1px solid var(--border); border-radius: 8px; background: #fff; padding: 12px; margin-bottom: 12px; }
.branch-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 4px; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; background: #eef2f7; font-size: 12px; color: #334155; }
.tag-ok { background: #e7f6ec; color: #177245; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.tag-warn { background: #fdf1e3; color: #a15c00; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.notice { background: #eef4ff; border: 1px solid #c9dafc; color: #1f3f86; padding: 8px 10px; border-radius: 6px; font-size: 13px; }
.json-input { width: 100%; font-family: monospace; font-size: 12px; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
.json-view { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-size: 12px; max-height: 200px; overflow: auto; }
.review-meta { display: grid; grid-template-columns: 90px 1fr; gap: 4px 10px; font-size: 13px; margin: 0 0 12px; }
.review-meta dt { color: var(--muted); }
.review-meta dd { margin: 0; }
</style>
