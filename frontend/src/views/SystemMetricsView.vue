<template>
  <MainLayout>
    <div class="system-page grid">
      <div class="top-cards-row">
        <section class="card section-card metrics-card">
          <div class="section-head">
            <h3 class="section-title">系统性能指标</h3>
            <div class="control-row">
              <button
                class="btn btn-primary btn-icon"
                type="button"
                :disabled="testing"
                :title="testing ? '测试进行中...' : '一键测试'"
                :aria-label="testing ? '测试进行中...' : '一键测试'"
                @click="startOneClickTest"
              >
                <span class="material-symbols-outlined" :class="{ 'icon-spinning': testing }" aria-hidden="true">
                  {{ testing ? 'autorenew' : 'rocket_launch' }}
                </span>
              </button>
            </div>
          </div>

          <div class="test-config-row">
            <label class="config-item">
              <span>查询轮次</span>
              <input v-model.number="testConfig.query_runs" class="input" type="number" min="1" max="200" />
            </label>
            <label class="config-item">
              <span>可视化轮次</span>
              <input v-model.number="testConfig.visual_runs" class="input" type="number" min="1" max="200" />
            </label>
            <label class="config-item">
              <span>上传轮次</span>
              <input v-model.number="testConfig.upload_runs" class="input" type="number" min="1" max="50" />
            </label>
          </div>

          <div class="live-test-panel">
            <div class="live-test-head">
              <strong>当前测试任务</strong>
              <span>状态: {{ testJob?.status || '未开始' }}</span>
              <span>进度: {{ testJob?.progress?.done_rounds || 0 }} / {{ testJob?.progress?.total_rounds || 0 }}</span>
              <span>当前项: {{ testJob?.progress?.current_metric || '-' }}</span>
            </div>

            <div class="table-wrap">
              <table class="simple-table">
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>轮次</th>
                    <th>最新值</th>
                    <th>AVG</th>
                    <th>P95</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in testMetricRows" :key="row.key">
                    <td>{{ row.label }}</td>
                    <td>{{ row.runs_done }}/{{ row.runs_total }}</td>
                    <td>{{ row.latestText }}</td>
                    <td>{{ row.avgText }}</td>
                    <td>{{ row.p95Text }}</td>
                    <td>
                      <span :class="['status-pill', row.status === 'PASS' ? 'ok' : row.status === 'FAIL' ? 'bad' : row.status === '-' ? 'neutral' : 'warn']">
                        {{ row.status }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="testJob?.error" class="danger-text">测试异常：{{ testJob?.error }}</div>
          </div>

        </section>

        <section class="card section-card">
          <div class="section-head">
            <h3 class="section-title">性能趋势（最近 10 次）</h3>
          </div>
          <div class="trend-chart-wrap">
            <div ref="trendChartRef" class="trend-chart"></div>
            <div v-if="!hasTrendData" class="trend-empty">暂无趋势数据，请先运行测评脚本后刷新。</div>
          </div>
        </section>
      </div>

      <section class="card section-card">
        <div class="section-head">
          <h3 class="section-title">数据库备份与恢复</h3>
          <button
            class="btn btn-primary btn-icon"
            type="button"
            :disabled="runningBackup"
            :title="runningBackup ? '备份中...' : '立即备份'"
            :aria-label="runningBackup ? '备份中...' : '立即备份'"
            @click="runBackup"
          >
            <span class="material-symbols-outlined" :class="{ 'icon-spinning': runningBackup }" aria-hidden="true">
              {{ runningBackup ? 'autorenew' : 'cloud_upload' }}
            </span>
          </button>
        </div>

        <div class="backup-meta">
          <span v-if="backupJob">备份进度: {{ backupJob?.progress?.percent || 0 }}%（{{ backupJob?.progress?.stage || '-' }}）</span>
          <span v-if="restoreJobId">恢复进度: {{ restoreJob?.progress?.percent || 0 }}%（{{ restoreJob?.progress?.stage || '已提交' }}）</span>
        </div>

        <div class="table-wrap">
          <table class="simple-table">
            <thead>
              <tr>
                <th>备份文件</th>
                <th>执行人员</th>
                <th>修改时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in backupItems" :key="item.name">
                <td>{{ item.name }}</td>
                <td>{{ item.executor_label || '-' }}</td>
                <td>{{ formatTime(item.created_at || item.modified_at) }}</td>
                <td>
                  <button class="btn btn-ghost btn-small" type="button" @click="selectRestore(item.name)">
                    恢复到此版本
                  </button>
                </td>
              </tr>
              <tr v-if="!backupItems.length">
                <td colspan="4" class="empty-cell">暂无备份文件</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="postcheckResult" class="probe-panel">
          <div class="restore-title">恢复后自动探活校验</div>
          <div class="restore-row">
            <span :class="postcheckResult.passed ? 'ok-text' : 'danger-text'">
              {{ postcheckResult.passed ? '探活通过' : '探活存在失败项' }}
            </span>
            <span>耗时: {{ postcheckResult.duration_ms || 0 }} ms</span>
          </div>
          <ul class="check-list">
            <li v-for="item in postcheckResult.items || []" :key="`post-${item.name}`" class="check-item">
              <span class="status-pill" :class="item.passed ? 'ok' : 'bad'">{{ item.status }}</span>
              <span>{{ item.name }}</span>
              <span class="check-detail">{{ item.detail }}</span>
            </li>
          </ul>
        </div>

        <teleport to="body">
          <div v-if="restoreTarget" class="restore-modal-mask" @click="closeRestoreDialog">
            <div class="restore-modal card" @click.stop>
              <div class="restore-modal-head">
                <h3 class="section-title" style="margin: 0;">恢复确认</h3>
                <button class="icon-btn icon-btn-close" type="button" :disabled="checkingRestore || restoring" @click="closeRestoreDialog" aria-label="关闭" title="关闭">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M18.3 5.71a1 1 0 0 0-1.42 0L12 10.59 7.12 5.7A1 1 0 0 0 5.7 7.13L10.58 12l-4.9 4.88a1 1 0 0 0 1.43 1.42L12 13.41l4.88 4.89a1 1 0 0 0 1.42-1.43L13.41 12l4.89-4.88a1 1 0 0 0 0-1.41z" />
                  </svg>
                </button>
              </div>

              <div class="restore-panel">
                <div class="restore-row">
                  <span>目标版本: {{ restoreTarget }}</span>
                  <span class="danger-text">高风险操作，将覆盖当前数据库内容</span>
                </div>

                <div v-if="restoreJob" class="restore-row">
                  <span>恢复进度: {{ restoreJob?.progress?.percent || 0 }}%（{{ restoreJob?.progress?.stage || '-' }}）</span>
                  <span class="check-detail">{{ restoreJob?.progress?.detail || '' }}</span>
                </div>

                <div class="restore-row">
                  <button class="btn btn-ghost" type="button" :disabled="checkingRestore || restoring" @click="runPrecheck">
                    {{ checkingRestore ? '检查中...' : '执行恢复前健康检查' }}
                  </button>
                  <span v-if="precheckResult" :class="precheckResult.can_restore ? 'ok-text' : 'danger-text'">
                    {{ precheckResult.can_restore ? '检查通过，可执行恢复' : '检查未通过，恢复已拦截' }}
                  </span>
                </div>

                <div v-if="precheckResult" class="check-grid">
                  <div class="check-block">
                    <div class="check-title">恢复前健康检查</div>
                    <ul class="check-list">
                      <li v-for="item in precheckResult.items || []" :key="`pre-${item.name}`" class="check-item">
                        <span class="status-pill" :class="item.passed ? 'ok' : 'bad'">{{ item.status }}</span>
                        <span>{{ item.name }}</span>
                        <span class="check-detail">{{ item.detail }}</span>
                      </li>
                    </ul>
                  </div>
                </div>

                <div class="restore-actions">
                  <input
                    v-model="restoreConfirmText"
                    class="input restore-confirm-input"
                    placeholder="请输入 RESTORE 确认"
                  />
                  <button class="btn btn-danger" type="button" :disabled="restoring || !canDoRestore" @click="confirmRestore">
                    {{ restoring ? '恢复中...' : '确认恢复' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </teleport>
      </section>

      <section class="card section-card">
        <div class="section-head">
          <h3 class="section-title">运维日志</h3>
        </div>
        <div class="table-wrap">
          <table class="simple-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>动作</th>
                <th>状态</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in logs" :key="`${row.time}-${idx}`">
                <td>{{ formatTime(row.time) }}</td>
                <td>{{ row.action }}</td>
                <td>
                  <span :class="['status-pill', row.status === 'PASS' ? 'ok' : 'bad']">{{ row.status }}</span>
                </td>
                <td>{{ row.detail }}</td>
              </tr>
              <tr v-if="!logs.length">
                <td colspan="4" class="empty-cell">暂无日志</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { init as initChart, use } from 'echarts/core'
import MainLayout from '../layouts/MainLayout.vue'
import {
  apiSystemBackupJobStatus,
  apiSystemBackupPrecheck,
  apiSystemBackupList,
  apiSystemBackupRestore,
  apiSystemBackupRun,
  apiSystemOpsLogs,
  apiSystemTestMetricUpdate,
  apiSystemTestRun,
  apiSystemTestStatus,
  apiSystemTestUploadProbe,
  apiSystemMetrics,
} from '../api/systemApi'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const loadingMetrics = ref(false)
const loadingLogs = ref(false)
const runningBackup = ref(false)
const checkingRestore = ref(false)
const restoring = ref(false)
const testing = ref(false)

const kpis = ref([])
const trend = ref({
  query_p95_s: [],
  visual_p95_s: [],
  upload_avg_mb_s: [],
})
const latestRunSummary = ref(null)

const backupDir = ref('')
const backupItems = ref([])
const logs = ref([])

const restoreTarget = ref('')
const restoreConfirmText = ref('')
const precheckResult = ref(null)
const postcheckResult = ref(null)
const testJobId = ref('')
const testJob = ref(null)
const testPollTimer = ref(null)
const frontendProbeRunning = ref(false)
const backupJobId = ref('')
const backupJob = ref(null)
const backupPollTimer = ref(null)
const restoreJobId = ref('')
const restoreJob = ref(null)
const restorePollTimer = ref(null)
const hasTriggeredTest = ref(false)
const testConfig = ref({
  query_runs: 20,
  visual_runs: 10,
  upload_runs: 3,
})
const frontendProbeMetric = ref({
  label: '500M文件上传',
  runs_total: 1,
  runs_done: 0,
  latest: null,
  stats: null,
  status: '-',
})
let cachedProbeFile = null

const trendChartRef = ref(null)
let trendChartInstance = null
let trendResizeObserver = null
const RESTORE_JOB_STORAGE_KEY = 'system_restore_job_id'

const hasRestorePermission = computed(() => true)
const hasTrendData = computed(() => {
  return (
    (trend.value.query_p95_s || []).length > 0 ||
    (trend.value.visual_p95_s || []).length > 0 ||
    (trend.value.upload_avg_mb_s || []).length > 0
  )
})
const canDoRestore = computed(() => {
  return precheckResult.value?.can_restore === true
})
const showTestResultValues = computed(() => hasTriggeredTest.value)

const testMetricRows = computed(() => {
  const metrics = {
    ...(testJob.value?.metrics || {}),
    upload_probe_500m: frontendProbeMetric.value,
  }
  const hasJob = !!testJob.value
  const defaultLabels = {
    query: '查询响应时间',
    visual: '可视化响应时间',
    upload: '上传速度',
    upload_probe_500m: '500M文件上传',
  }
  const rows = []
  for (const key of ['query', 'visual', 'upload', 'upload_probe_500m']) {
    const item = metrics[key] || {}
    const unit = key === 'upload' ? ' MB/s' : ' s'
    const hasStats = !!item.stats
    rows.push({
      key,
      label: item.label || defaultLabels[key],
      runs_done: item.runs_done || 0,
      runs_total: item.runs_total || 0,
      latestText: showTestResultValues.value && item.latest !== null && item.latest !== undefined ? `${Number(item.latest).toFixed(4)}${unit}` : '-',
      avgText: showTestResultValues.value && hasStats ? `${Number(item.stats.avg || 0).toFixed(4)}${unit}` : '-',
      p95Text: showTestResultValues.value && hasStats ? `${Number(item.stats.p95 || 0).toFixed(4)}${unit}` : '-',
      status: item.status || (hasJob ? 'RUNNING' : '-'),
    })
  }
  return rows
})

function resetFrontendProbeMetric() {
  frontendProbeMetric.value = {
    label: '500M文件上传',
    runs_total: 1,
    runs_done: 0,
    latest: null,
    stats: null,
    status: 'RUNNING',
  }
}

function updateTestingState() {
  const backendDone = ['completed', 'failed'].includes(String(testJob.value?.status || ''))
  if (backendDone && !frontendProbeRunning.value) {
    testing.value = false
  }
}

async function getOrCreateProbeFile() {
  const targetBytes = 500 * 1024 * 1024
  if (cachedProbeFile && cachedProbeFile.size >= targetBytes) {
    return cachedProbeFile
  }

  const header = 'c1,c2,c3,c4,c5\n'
  const row = '0,0,0,0,0\n'
  const chunk = row.repeat(12000)
  const parts = [header]
  let size = header.length
  while (size < targetBytes) {
    parts.push(chunk)
    size += chunk.length
  }

  cachedProbeFile = new File(parts, 'big_file.csv', { type: 'text/csv' })
  return cachedProbeFile
}

async function runFrontendUploadProbeMetric(jobId = '') {
  frontendProbeRunning.value = true
  resetFrontendProbeMetric()
  try {
    const probeFile = await getOrCreateProbeFile()
    const formData = new FormData()
    formData.append('file', probeFile, probeFile.name)

    const started = performance.now()
    const res = await apiSystemTestUploadProbe(formData)
    const elapsedSec = (performance.now() - started) / 1000
    const receivedBytes = Number(res?.data?.size_bytes || 0)
    const receivedMb = receivedBytes / 1024 / 1024
    const generatedMb = probeFile.size / 1024 / 1024
    const pass = res?.code === 0 && receivedMb >= 450

    frontendProbeMetric.value = {
      ...frontendProbeMetric.value,
      runs_done: 1,
      latest: elapsedSec,
      stats: {
        avg: elapsedSec,
        p95: elapsedSec,
      },
      status: pass ? 'PASS' : 'FAIL',
    }

    if (jobId) {
      await apiSystemTestMetricUpdate({
        job_id: jobId,
        metric_key: 'upload_probe_500m',
        latest: elapsedSec,
        generated_size_mb: generatedMb,
        received_size_mb: receivedMb,
        success: pass ? 1 : 0,
      })
      await fetchTestStatus()
    }
  } catch (error) {
    frontendProbeMetric.value = {
      ...frontendProbeMetric.value,
      runs_done: 1,
      latest: 0,
      stats: {
        avg: 0,
        p95: 0,
      },
      status: 'FAIL',
    }

    if (jobId) {
      try {
        await apiSystemTestMetricUpdate({
          job_id: jobId,
          metric_key: 'upload_probe_500m',
          latest: 0,
          generated_size_mb: 0,
          received_size_mb: 0,
          success: 0,
        })
        await fetchTestStatus()
      } catch (_) {
      }
    }
  } finally {
    frontendProbeRunning.value = false
    updateTestingState()
  }
}
function statusClass(status) {
  if (status === 'PASS') return 'status-pass'
  if (status === 'FAIL') return 'status-fail'
  return 'status-skip'
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString('zh-CN', { hour12: false })
}

function formatTimeToMinute(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)

  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

function buildTrendOption() {
  const query = trend.value.query_p95_s || []
  const visual = trend.value.visual_p95_s || []
  const upload = trend.value.upload_avg_mb_s || []
  const xLabels = [...new Set([...query, ...visual, ...upload].map((row) => row.label))]

  const toSeriesValues = (rows) => {
    const map = new Map(rows.map((item) => [item.label, item.value]))
    return xLabels.map((label) => {
      if (!map.has(label)) return null
      return Number(map.get(label))
    })
  }

  return {
    backgroundColor: 'transparent',
    color: ['#00a8cc', '#3c8dbc', '#2ecc71'],
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const title = formatTimeToMinute(params[0].axisValue)
        const lines = params
          .filter((item) => item.value !== null && item.value !== undefined && item.value !== '-')
          .map((item) => `${item.marker}${item.seriesName}&nbsp;&nbsp;${Number(item.value).toFixed(6)}`)
        return [title, ...lines].join('<br/>')
      },
    },
    legend: {
      top: 4,
      textStyle: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#333',
      },
    },
    grid: {
      left: 24,
      right: 18,
      top: 42,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisLabel: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--chart-muted').trim() || '#666',
        fontSize: 11,
        rotate: 20,
        formatter: (value) => formatTimeToMinute(value),
      },
      axisLine: {
        lineStyle: {
          color: getComputedStyle(document.documentElement).getPropertyValue('--chart-axis').trim() || '#ddd',
        },
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--chart-muted').trim() || '#666',
      },
      splitLine: {
        lineStyle: {
          color: getComputedStyle(document.documentElement).getPropertyValue('--chart-grid').trim() || '#eee',
        },
      },
    },
    series: [
      {
        name: '查询 P95 (s)',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: toSeriesValues(query),
      },
      {
        name: '可视化 P95 (s)',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: toSeriesValues(visual),
      },
      {
        name: '上传均速 (MB/s)',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: toSeriesValues(upload),
      },
    ],
  }
}

function renderTrendChart() {
  if (!trendChartInstance) return
  trendChartInstance.setOption(buildTrendOption(), true)
}

function initTrendChart() {
  if (!trendChartRef.value) return
  if (trendChartInstance) {
    trendChartInstance.dispose()
  }
  trendChartInstance = initChart(trendChartRef.value)
  renderTrendChart()

  if (trendResizeObserver) {
    trendResizeObserver.disconnect()
  }
  trendResizeObserver = new ResizeObserver(() => {
    trendChartInstance?.resize()
  })
  trendResizeObserver.observe(trendChartRef.value)
}

async function loadMetrics() {
  loadingMetrics.value = true
  try {
    const res = await apiSystemMetrics()
    if (res.code !== 0) throw new Error(res.message || '指标加载失败')

    kpis.value = (res.data.kpis || []).filter((item) => item.key !== 'pass_total')
    trend.value = res.data.trend || {
      query_p95_s: [],
      visual_p95_s: [],
      upload_avg_mb_s: [],
    }
    latestRunSummary.value = res.data.latest_run || null
  } catch (err) {
    ElMessage.error(err.message || '指标加载失败')
  } finally {
    loadingMetrics.value = false
  }
}

async function loadBackups() {
  try {
    const res = await apiSystemBackupList()
    if (res.code !== 0) throw new Error(res.message || '备份列表加载失败')
    backupDir.value = res.data.backup_dir || ''
    backupItems.value = res.data.items || []
    logs.value = res.data.logs || []
  } catch (err) {
    ElMessage.error(err.message || '备份列表加载失败')
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const res = await apiSystemOpsLogs({ limit: 120 })
    if (res.code !== 0) throw new Error(res.message || '日志加载失败')
    logs.value = res.data.items || []
  } catch (err) {
    ElMessage.error(err.message || '日志加载失败')
  } finally {
    loadingLogs.value = false
  }
}

async function fetchTestStatus() {
  if (!testJobId.value) return
  const res = await apiSystemTestStatus({ job_id: testJobId.value })
  if (res.code !== 0) {
    throw new Error(res.message || '测试状态获取失败')
  }
  testJob.value = res.data.job || null
  const status = testJob.value?.status
  if (status === 'completed' || status === 'failed') {
    stopTestPolling()
    if (status === 'completed') {
      ElMessage.success('一键测试完成')
      await loadMetrics()
      await loadLogs()
    } else {
      ElMessage.error(testJob.value?.error || '测试失败')
    }
    updateTestingState()
  }
}

function stopTestPolling() {
  if (testPollTimer.value) {
    clearInterval(testPollTimer.value)
    testPollTimer.value = null
  }
}

function startTestPolling() {
  stopTestPolling()
  testPollTimer.value = setInterval(async () => {
    try {
      await fetchTestStatus()
    } catch (err) {
      stopTestPolling()
      testing.value = false
      ElMessage.error(err.message || '测试状态轮询失败')
    }
  }, 1000)
}

async function startOneClickTest() {
  hasTriggeredTest.value = true
  testing.value = true
  testJob.value = null
  try {
    const payload = {
      query_runs: Math.min(Math.max(Number(testConfig.value.query_runs || 1), 1), 200),
      visual_runs: Math.min(Math.max(Number(testConfig.value.visual_runs || 1), 1), 200),
      upload_runs: Math.min(Math.max(Number(testConfig.value.upload_runs || 1), 1), 50),
    }
    const res = await apiSystemTestRun(payload)
    if (res.code !== 0) {
      throw new Error(res.message || '一键测试启动失败')
    }
    testJobId.value = res.data.job_id
    ElMessage.success('一键测试已启动')
    runFrontendUploadProbeMetric(testJobId.value)
    await fetchTestStatus()
    startTestPolling()
  } catch (err) {
    testing.value = false
    ElMessage.error(err.message || '一键测试启动失败')
  }
}

async function runBackup() {
  stopBackupPolling()
  backupJobId.value = ''
  backupJob.value = null
  runningBackup.value = true
  try {
    const res = await apiSystemBackupRun()
    if (res.code !== 0) throw new Error(res.message || '备份任务启动失败')
    backupJobId.value = res.data?.job_id || ''
    if (!backupJobId.value) throw new Error('未获取到备份任务ID')
    ElMessage.success('备份任务已启动')
    await fetchBackupJobStatus()
    startBackupPolling()
  } catch (err) {
    runningBackup.value = false
    ElMessage.error(err.message || '备份任务启动失败')
  } finally {
  }
}

function selectRestore(name) {
  if (!hasRestorePermission.value) {
    ElMessage.warning('当前用户无恢复权限')
    return
  }
  restoreTarget.value = name
  restoreConfirmText.value = ''
  precheckResult.value = null
  postcheckResult.value = null
  runPrecheck()
}

function cancelRestore() {
  restoreTarget.value = ''
  restoreConfirmText.value = ''
  precheckResult.value = null
}

function closeRestoreDialog() {
  if (checkingRestore.value || restoring.value) return
  cancelRestore()
}

function saveRestoreJobId(jobId) {
  const normalized = String(jobId || '').trim()
  if (!normalized) return
  localStorage.setItem(RESTORE_JOB_STORAGE_KEY, normalized)
}

function clearRestoreJobId() {
  localStorage.removeItem(RESTORE_JOB_STORAGE_KEY)
}

async function resumeRestoreJobIfNeeded() {
  const cachedJobId = String(localStorage.getItem(RESTORE_JOB_STORAGE_KEY) || '').trim()
  if (!cachedJobId) return

  restoreJobId.value = cachedJobId
  restoring.value = true
  try {
    await fetchRestoreJobStatus()
    if (restoring.value) {
      startRestorePolling()
    }
  } catch (_) {
    restoring.value = false
    clearRestoreJobId()
    restoreJobId.value = ''
    restoreJob.value = null
  }
}

async function runPrecheck() {
  if (!restoreTarget.value) {
    ElMessage.warning('请先选择备份版本')
    return
  }

  checkingRestore.value = true
  try {
    const res = await apiSystemBackupPrecheck({ backup_name: restoreTarget.value })
    if (res.code !== 0) throw new Error(res.message || '恢复前检查失败')
    precheckResult.value = res.data || null
    if (precheckResult.value?.can_restore) {
      ElMessage.success('恢复前检查通过')
    } else {
      ElMessage.warning('恢复前检查未通过')
    }
  } catch (err) {
    ElMessage.error(err.message || '恢复前检查失败')
  } finally {
    checkingRestore.value = false
  }
}

async function confirmRestore() {
  if (!restoreTarget.value) {
    ElMessage.warning('请先选择备份版本')
    return
  }
  if (restoreConfirmText.value.trim().toUpperCase() !== 'RESTORE') {
    ElMessage.warning('请输入 RESTORE 确认')
    return
  }
  if (!precheckResult.value?.can_restore) {
    ElMessage.warning('请先通过恢复前健康检查')
    return
  }

  stopRestorePolling()
  restoreJobId.value = ''
  restoreJob.value = {
    status: 'running',
    progress: {
      percent: 0,
      stage: '已提交',
      detail: '等待后台开始执行恢复任务',
    },
  }
  restoring.value = true
  try {
    const res = await apiSystemBackupRestore({
      backup_name: restoreTarget.value,
      confirm_text: restoreConfirmText.value.trim(),
    })
    if (res.code !== 0) throw new Error(res.message || '恢复任务启动失败')
    restoreJobId.value = res.data?.job_id || ''
    if (!restoreJobId.value) throw new Error('未获取到恢复任务ID')
    saveRestoreJobId(restoreJobId.value)
    ElMessage.success('恢复任务已提交后台执行')
    cancelRestore()
    startRestorePolling()
  } catch (err) {
    restoring.value = false
    clearRestoreJobId()
    postcheckResult.value = null
    ElMessage.error(err.message || '恢复任务启动失败')
  }
}

async function fetchBackupJobStatus() {
  if (!backupJobId.value) return
  const res = await apiSystemBackupJobStatus({ job_id: backupJobId.value })
  if (res.code !== 0) {
    throw new Error(res.message || '备份任务状态获取失败')
  }

  backupJob.value = res.data?.job || null
  const status = backupJob.value?.status
  if (status === 'completed' || status === 'failed') {
    stopBackupPolling()
    runningBackup.value = false
    if (status === 'completed') {
      backupItems.value = backupJob.value?.result?.items || backupItems.value
      ElMessage.success(backupJob.value?.result?.message || '备份执行成功')
      await loadLogs()
    } else {
      ElMessage.error(backupJob.value?.error || '备份执行失败')
    }
  }
}

function stopBackupPolling() {
  if (backupPollTimer.value) {
    clearInterval(backupPollTimer.value)
    backupPollTimer.value = null
  }
}

function startBackupPolling() {
  stopBackupPolling()
  backupPollTimer.value = setInterval(async () => {
    try {
      await fetchBackupJobStatus()
    } catch (err) {
      stopBackupPolling()
      runningBackup.value = false
      ElMessage.error(err.message || '备份任务轮询失败')
    }
  }, 1000)
}

async function fetchRestoreJobStatus() {
  if (!restoreJobId.value) return
  const res = await apiSystemBackupJobStatus({ job_id: restoreJobId.value })
  if (res.code !== 0) {
    throw new Error(res.message || '恢复任务状态获取失败')
  }

  restoreJob.value = res.data?.job || null
  const status = restoreJob.value?.status
  if (status === 'completed' || status === 'failed') {
    stopRestorePolling()
    restoring.value = false
    clearRestoreJobId()
    if (status === 'completed') {
      postcheckResult.value = restoreJob.value?.result?.postcheck || null
      const pass = !!postcheckResult.value?.passed
      ElMessage.success(pass ? '恢复成功且探活通过' : '恢复完成，但探活有失败项')
      cancelRestore()
      await loadBackups()
      await loadLogs()
    } else {
      postcheckResult.value = null
      ElMessage.error(restoreJob.value?.error || '恢复失败')
    }
  }
}

function stopRestorePolling() {
  if (restorePollTimer.value) {
    clearInterval(restorePollTimer.value)
    restorePollTimer.value = null
  }
}

function startRestorePolling() {
  stopRestorePolling()
  restorePollTimer.value = setInterval(async () => {
    try {
      await fetchRestoreJobStatus()
    } catch (err) {
      stopRestorePolling()
      restoring.value = false
      ElMessage.error(err.message || '恢复任务轮询失败')
    }
  }, 1000)
}

onMounted(async () => {
  await Promise.all([loadMetrics(), loadBackups()])
  await resumeRestoreJobIfNeeded()
  await nextTick()
  initTrendChart()
})

watch(
  trend,
  () => {
    renderTrendChart()
  },
  { deep: true }
)

onBeforeUnmount(() => {
  stopTestPolling()
  stopBackupPolling()
  stopRestorePolling()
  if (trendResizeObserver) {
    trendResizeObserver.disconnect()
    trendResizeObserver = null
  }
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
})
</script>

<style scoped>
.system-page {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: auto minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}

.system-page > .top-cards-row {
  grid-column: 1 / -1;
  min-height: 0;
}

.section-card {
  padding: 16px;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.metrics-card {
  overflow: hidden;
}

.metrics-card .live-test-panel {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.metrics-card .live-test-panel .table-wrap {
  flex: 1 1 auto;
  min-height: 0;
}

.metrics-card .live-test-panel .table-wrap {
  min-height: 178px;
}

.top-cards-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: stretch;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.test-config-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.config-item {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}

.live-test-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--brand) 8%, var(--panel-elevated));
  padding: 12px;
  display: grid;
  gap: 10px;
}

.live-test-head {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
}

.section-title {
  margin: 0;
  font-size: 18px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.kpi-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-soft);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kpi-name {
  font-size: 13px;
  color: var(--muted);
}

.kpi-value {
  font-size: 18px;
  font-weight: 700;
}

.kpi-meta {
  font-size: 12px;
  color: var(--muted);
}

.kpi-status {
  font-size: 12px;
  font-weight: 700;
}

.status-pass {
  border-left: 4px solid #1e9c5e;
}

.status-fail {
  border-left: 4px solid #d64545;
}

.status-skip {
  border-left: 4px solid #f59e0b;
}

.kpi-empty {
  grid-column: 1 / -1;
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 16px;
  color: var(--muted);
}

.trend-chart-wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-soft);
  padding: 10px;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 178px;
}

.trend-chart {
  width: 100%;
  height: 100%;
  min-height: 158px;
}

.trend-empty {
  color: var(--muted);
  font-size: 13px;
  padding: 0 8px 8px;
}

.backup-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 13px;
}

.table-wrap {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  overflow: auto;
}

.simple-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.simple-table th,
.simple-table td {
  border-bottom: 1px solid var(--border);
  padding: 10px 8px;
  text-align: left;
}

.simple-table th {
  color: var(--muted);
  font-weight: 600;
}

.empty-cell {
  text-align: center;
  color: var(--muted);
}

.btn-small {
  min-height: 30px;
  padding: 4px 10px;
  font-size: 12px;
}

.btn-icon {
  width: 38px;
  height: 38px;
  min-width: 38px;
  min-height: 38px;
  padding: 0;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon .material-symbols-outlined {
  font-size: 20px;
}

.icon-spinning {
  animation: spin-360 1s linear infinite;
}

@keyframes spin-360 {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.restore-panel {
  border: 1px solid color-mix(in srgb, var(--danger) 35%, var(--border));
  border-radius: 10px;
  padding: 12px;
  background: color-mix(in srgb, var(--danger) 7%, var(--panel-elevated));
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.restore-modal-mask {
  position: fixed;
  inset: 0;
  background: var(--overlay-loading-bg);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 1100;
}

.restore-modal {
  width: min(1080px, 100%);
  max-height: min(88vh, 920px);
  overflow: auto;
  padding: 16px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.restore-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  background: var(--surface-soft);
  color: #81ecff;
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.icon-btn svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.icon-btn-close {
  width: 38px;
  height: 38px;
  border-radius: 999px;
}

.icon-btn-close:hover {
  background: var(--surface-hover);
}

.restore-title {
  font-weight: 700;
}

.restore-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.restore-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.restore-confirm-input {
  width: min(240px, 100%);
}

.danger-text {
  color: var(--danger);
}

.ok-text {
  color: #1e9c5e;
}

.check-grid {
  display: grid;
  grid-template-columns: 1fr;
}

.check-block {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-soft);
  padding: 10px;
}

.check-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.check-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.check-item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.check-detail {
  color: var(--muted);
}

.probe-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: color-mix(in srgb, #1e9c5e 8%, var(--panel-elevated));
}

.status-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 700;
}

.status-pill.ok {
  background: color-mix(in srgb, #1e9c5e 20%, transparent);
  color: #1e9c5e;
}

.status-pill.bad {
  background: color-mix(in srgb, #d64545 18%, transparent);
  color: #d64545;
}

.status-pill.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #b76d00;
}

.status-pill.neutral {
  background: color-mix(in srgb, var(--muted) 18%, transparent);
  color: var(--muted);
}

@media (max-width: 768px) {
  .system-page {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
    height: auto;
  }

  .top-cards-row {
    grid-template-columns: 1fr;
  }

  .section-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .backup-meta,
  .restore-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .live-test-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .trend-chart {
    height: 280px;
  }

  .check-item {
    grid-template-columns: 1fr;
    align-items: flex-start;
  }
}
</style>
