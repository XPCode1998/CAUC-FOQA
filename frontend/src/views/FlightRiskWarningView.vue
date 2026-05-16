<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="qarId" @search="handleSearch" />
      </div>
    </template>

    

    <div class="warning-page">
      <div class="summary-grid">
        <div class="card card-pad summary-card summary-config-card">
        <div class="summary-head">模型配置</div>
        <div class="summary-body upload-params-block">
          <label class="form-item inline-item compact-item">
            <span>模型</span>
            <select v-model="form.modelName" class="input input-w-sm">
              <option value="Transformer">Transformer</option>
              <option value="iTransformer">iTransformer</option>
              <option value="Informer">Informer</option> 
              <option value="Flowformer">Flowformer</option>   
              <option value="CNN">CNN</option>
              <option value="LSTM">LSTM</option>
              <option value="GRU">GRU</option>
            </select>
          </label>

          

          <label class="form-item inline-item compact-item">
            <span>窗口长度</span>
            <input
              v-model.number="form.seqLen"
              class="input input-w-xs"
              type="number"
              min="10"
              step="10"
              :disabled="isITransformer"
            />
          </label>
        </div>
      </div>

        <div class="card card-pad summary-card stat-card">
        <div class="summary-head stat-label">已推理窗口</div>
        <div class="summary-body stat-value">{{ windows.length }}</div>
      </div>

        <div class="card card-pad summary-card stat-card">
        <div class="summary-head stat-label">当前类别</div>
        <div class="summary-body stat-value with-chip">
          <span class="class-chip" :class="classLevelClass(currentWindow?.predicted_class_id)">{{ currentWindow?.predicted_class_name || '--' }}</span>
        </div>
      </div>

        <div class="card card-pad summary-card stat-card">
        <div class="summary-head stat-label">当前置信度</div>
        <div class="summary-body stat-value">{{ currentConfidenceText }}</div>
      </div>

        <div class="card card-pad summary-card stat-card">
        <div class="summary-head stat-label">推理速度</div>
        <div class="summary-body stat-value">{{ streamRateText }}</div>
      </div>

        <div class="card card-pad summary-card action-card">
        <div class="summary-head">操作</div>
        <div class="summary-body control-row action-row compact-actions">
          <button
            class="btn icon-action-btn"
            :class="isStreaming ? 'btn-danger' : 'btn-primary'"
            type="button"
            :disabled="(!canStart && !isStreaming) || (!isStreaming && !qarId)"
            @click="toggleStreaming"
            :title="isStreaming ? '停止推理' : '开始推理'"
            :aria-label="isStreaming ? '停止推理' : '开始推理'"
          >
            <span class="material-symbols-outlined" aria-hidden="true">{{ isStreaming ? 'stop_circle' : 'play_circle' }}</span>
          </button>
          <button
            class="btn btn-ghost icon-action-btn"
            type="button"
            :disabled="isStreaming"
            @click="resetAll"
            title="清空结果"
            aria-label="清空结果"
          >
            <span class="material-symbols-outlined" aria-hidden="true">settings_backup_restore</span>
          </button>
        </div>
      </div>
      </div>

   
      <div class="card card-pad chart-card">
        <div class="panel-head">
          <div>
            <h3 class="panel-title">实时风险趋势</h3>
            <div class="section-subtitle">实时推理QAR数据当前的飞行风险情况</div>
          </div>
          <div class="chart-head-tools">
            <div class="stream-status" :class="streamStatusClass">{{ streamStatusText }}</div>
            <div class="meta-summary" v-if="meta">
              <span>特征维度 {{ meta.feature_dim }}</span>
              <span>总窗口 {{ meta.window_count }}</span>
              <span>丢弃行 {{ meta.dropped_rows }}</span>
            </div>
          </div>
        </div>
        <div ref="chartRef" class="live-chart"></div>
      </div>
    </div>

    
  </MainLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { init as initChart, use } from 'echarts/core'
import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { getQarPageCache, setQarPageCache } from '../utils/qarPageCache'

use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, GraphicComponent, CanvasRenderer])

const chartRef = ref(null)
const donutChartRef = ref(null)
const isStreaming = ref(false)
const hasCompleted = ref(false)
const errorMessage = ref('')
const meta = ref(null)
const windows = ref([])
const elapsedSeconds = ref(0)

const route = useRoute()
const router = useRouter()
const qarId = ref(String(route.query?.qar_id || '').trim())

const form = ref({
  modelName: 'CNN',
  seqLen: 10,
  autoSelect: true,
  manualSelect: true,
})

const ITRANSFORMER_FIXED_SEQ_LEN = 300
const DEFAULT_SEQ_LEN = 10

const isITransformer = computed(() => String(form.value.modelName || '').trim() === 'iTransformer')

const riskMatrix = ref([
  { classId: 0, className: 'normal', riskWeight: 0.05, alertWeight: 0 },
  { classId: 1, className: 'icing', riskWeight: 0.45, alertWeight: 1 },
  { classId: 2, className: 'single_engine_failure', riskWeight: 0.68, alertWeight: 2 },
  { classId: 3, className: 'double_engine_failure', riskWeight: 0.95, alertWeight: 3 },
  { classId: 4, className: 'low_energy', riskWeight: 0.82, alertWeight: 2 },
  { classId: 5, className: 'other_risk', riskWeight: 0.72, alertWeight: 1.5 },
])

let streamAbortController = null
let streamStartedAt = 0
let elapsedTimer = null
let chartInstance = null
let donutChartInstance = null
let chartResizeObserver = null
let windowRenderTimer = null
let pendingWindowResults = []
let hasStreamDone = false

const STREAM_API_URL = '/api/v1/flight/risk/overlimit/stream/by-qar'
const STREAM_RENDER_INTERVAL_MS = 120

const canStart = computed(() => {
  if (isStreaming.value) return false
  if (!qarId.value) return false
  if (isITransformer.value) return true
  return Number(form.value.seqLen) >= 10
})

const currentWindow = computed(() => {
  if (!windows.value.length) return null
  return windows.value[windows.value.length - 1]
})

const currentConfidenceText = computed(() => {
  if (!currentWindow.value) return '--'
  return `${(Number(currentWindow.value.confidence || 0) * 100).toFixed(2)}%`
})

const streamRateText = computed(() => {
  if (!windows.value.length || elapsedSeconds.value <= 0) return '--'
  return `${(windows.value.length / elapsedSeconds.value).toFixed(2)} 窗口/秒`
})

const streamStatusText = computed(() => {
  if (isStreaming.value) return '实时推理进行中'
  if (errorMessage.value) return errorMessage.value
  if (hasCompleted.value) return '推理完成'
  return '待开始'
})

const streamStatusClass = computed(() => {
  if (isStreaming.value) return 'is-running'
  if (errorMessage.value) return 'is-error'
  if (hasCompleted.value) return 'is-done'
  return 'is-idle'
})

const recentRows = computed(() => windows.value.slice(-20).reverse())

const classDistribution = computed(() => {
  const map = new Map()
  windows.value.forEach((item) => {
    const key = Number(item.predicted_class_id)
    if (!map.has(key)) {
      map.set(key, {
        classId: key,
        className: item.predicted_class_name || `class_${key}`,
        count: 0,
      })
    }
    map.get(key).count += 1
  })
  return [...map.values()].sort((a, b) => a.classId - b.classId)
})

const weightedAlertCount = computed(() => {
  return windows.value.reduce((sum, item) => sum + alertCountUnit(item), 0)
})

const weightedAlertCountText = computed(() => weightedAlertCount.value.toFixed(1))

const alertWindowCount = computed(() => windows.value.filter((item) => alertCountUnit(item) > 0).length)

const highRiskWindowCount = computed(() => {
  return windows.value.filter((item) => classLevelClass(item.predicted_class_id) === 'level-high').length
})

const mediumRiskWindowCount = computed(() => {
  return windows.value.filter((item) => classLevelClass(item.predicted_class_id) === 'level-medium').length
})

function classLevelClass(classId) {
  if (Number(classId) === 0) return 'level-normal'
  if (Number(classId) <= 2) return 'level-medium'
  return 'level-high'
}

function classColor(classId) {
  if (Number(classId) === 0) return '#22a06b'
  if (Number(classId) <= 2) return '#ff9800'
  return '#d64545'
}

function normalizeClassToken(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s_\-﹣＿]+/g, '')
}

function mapDisplayClassName(classId, rawName) {
  const token = normalizeClassToken(rawName)
  const byName = {
    normal: '正常',
    normal1: '正常',
    normal2: '正常',
    risk1: '结冰',
    risk2: '单发失效',
    risk3: '双发失效',
    risk4: '双发失效',
    risk5: '双发失效',
    risk6: '低能量',
    icing: '结冰',
    singleenginefailure: '单发失效',
    doubleenginefailure: '双发失效',
    lowenergy: '低能量',
    otherrisk: '其他风险',
  }

  if (token && byName[token]) return byName[token]

  const byId = {
    0: '正常',
    1: '结冰',
    2: '单发失效',
    3: '双发失效',
    4: '低能量',
  }
  if (Object.prototype.hasOwnProperty.call(byId, Number(classId))) {
    return byId[Number(classId)]
  }
  return rawName || '未知'
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function getMatrixRow(classId) {
  const id = Number(classId)
  const found = riskMatrix.value.find((row) => Number(row.classId) === id)
  if (found) return found
  return { classId: id, className: `class_${id}`, riskWeight: 0.6, alertWeight: 1 }
}

function ensureMatrixRow(classId, className) {
  const id = Number(classId)
  const found = riskMatrix.value.find((row) => Number(row.classId) === id)
  if (found) {
    if (className && (!found.className || found.className.startsWith('class_'))) {
      found.className = className
    }
    return
  }

  riskMatrix.value.push({
    classId: id,
    className: className || `class_${id}`,
    riskWeight: id === 0 ? 0.05 : 0.6,
    alertWeight: id === 0 ? 0 : 1,
  })
  riskMatrix.value.sort((a, b) => Number(a.classId) - Number(b.classId))
}

function riskScore(item) {
  const matrixRow = getMatrixRow(item?.predicted_class_id)
  const riskWeight = clamp(Number(matrixRow.riskWeight || 0), 0, 1)
  const confidence = Number(item?.confidence || 0)
  const confidenceFactor = 0.35 + 0.65 * clamp(confidence, 0, 1)
  return clamp(100 * riskWeight * confidenceFactor, 0, 100)
}

function alertCountUnit(item) {
  const matrixRow = getMatrixRow(item?.predicted_class_id)
  const confidence = clamp(Number(item?.confidence || 0), 0, 1)
  const alertWeight = Math.max(0, Number(matrixRow.alertWeight || 0))
  return alertWeight * (0.4 + 0.6 * confidence)
}

function probPreview(probabilities) {
  if (!Array.isArray(probabilities) || probabilities.length === 0) return '--'
  return probabilities
    .slice(0, 4)
    .map((p, i) => `C${i}:${(Number(p || 0) * 100).toFixed(1)}%`)
    .join(' | ')
}

async function handleSearch() {
  const nextQarId = String(qarId.value || '').trim()
  qarId.value = nextQarId
  const currentQarId = String(route.query?.qar_id || '').trim()

  if (nextQarId !== currentQarId) {
    const nextQuery = { ...route.query }
    if (nextQarId) nextQuery.qar_id = nextQarId
    else delete nextQuery.qar_id
    await router.replace({ path: route.path, query: nextQuery })
  }
}

function resetAll() {
  if (isStreaming.value) return
  stopWindowRenderLoop(true)
  hasStreamDone = false
  windows.value = []
  meta.value = null
  hasCompleted.value = false
  errorMessage.value = ''
  elapsedSeconds.value = 0
  renderChart()
  renderDonutChart()
}

function restoreCachedRiskResult() {
  const normalizedQarId = String(qarId.value || '').trim()
  if (!normalizedQarId) return
  const cached = getQarPageCache('flight-risk-warning', normalizedQarId)
  if (!cached || typeof cached !== 'object') return

  windows.value = Array.isArray(cached.windows) ? cached.windows : []
  meta.value = cached.meta && typeof cached.meta === 'object' ? cached.meta : null
  hasCompleted.value = !!cached.hasCompleted
  errorMessage.value = ''
  renderChart()
  renderDonutChart()
}

function persistRiskResultSnapshot() {
  const normalizedQarId = String(qarId.value || '').trim()
  if (!normalizedQarId || !windows.value.length) return
  setQarPageCache('flight-risk-warning', normalizedQarId, '', {
    windows: windows.value.slice(-800),
    meta: meta.value,
    hasCompleted: hasCompleted.value,
  })
}

function toggleStreaming() {
  if (isStreaming.value) {
    stopStreaming()
    return
  }

  startStreaming()
}

function startElapsedTimer() {
  stopElapsedTimer()
  streamStartedAt = Date.now()
  elapsedSeconds.value = 0
  elapsedTimer = window.setInterval(() => {
    elapsedSeconds.value = Math.max(0, (Date.now() - streamStartedAt) / 1000)
  }, 300)
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    window.clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

function parseSseEvent(rawEvent) {
  const payloadText = rawEvent
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('')

  if (!payloadText) return null

  try {
    return JSON.parse(payloadText)
  } catch (_) {
    return null
  }
}

function consumeBuffer(state, flush = false) {
  state.buffer = state.buffer.replace(/\r\n/g, '\n')

  while (true) {
    const marker = state.buffer.indexOf('\n\n')
    if (marker < 0) break
    const rawEvent = state.buffer.slice(0, marker).trim()
    state.buffer = state.buffer.slice(marker + 2)
    if (!rawEvent) continue
    handleStreamEvent(parseSseEvent(rawEvent))
  }

  if (flush && state.buffer.trim()) {
    handleStreamEvent(parseSseEvent(state.buffer.trim()))
    state.buffer = ''
  }
}

function buildWindowRecord(payload) {
  const displayClassName = mapDisplayClassName(payload.predicted_class_id, payload.predicted_class_name)
  ensureMatrixRow(payload.predicted_class_id, displayClassName)
  return {
    window_index: Number(payload.window_index || windows.value.length),
    start_row: Number(payload.start_row || 0),
    end_row: Number(payload.end_row || 0),
    predicted_class_id: Number(payload.predicted_class_id || 0),
    predicted_class_name: String(displayClassName || '未知'),
    confidence: Number(payload.confidence || 0),
    probabilities: Array.isArray(payload.probabilities) ? payload.probabilities : [],
  }
}

function stopWindowRenderLoop(clearQueue = false) {
  if (windowRenderTimer) {
    window.clearInterval(windowRenderTimer)
    windowRenderTimer = null
  }
  if (clearQueue) {
    pendingWindowResults = []
  }
}

function startWindowRenderLoop() {
  if (windowRenderTimer) return
  windowRenderTimer = window.setInterval(() => {
    if (!pendingWindowResults.length) {
      stopWindowRenderLoop(false)
      if (hasStreamDone && !isStreaming.value) {
        hasCompleted.value = true
      }
      return
    }

    const nextWindow = pendingWindowResults.shift()
    windows.value.push(nextWindow)
    renderChart()
    renderDonutChart()
  }, STREAM_RENDER_INTERVAL_MS)
}

function queueWindowResult(payload) {
  pendingWindowResults.push(buildWindowRecord(payload))
  startWindowRenderLoop()
}

function handleStreamEvent(payload) {
  if (!payload || typeof payload !== 'object') return
  const eventType = payload.event

  if (eventType === 'meta') {
    meta.value = payload
    return
  }

  if (eventType === 'window_result') {
    queueWindowResult(payload)
    return
  }

  if (eventType === 'done') {
    hasStreamDone = true
    if (!pendingWindowResults.length && !isStreaming.value) {
      hasCompleted.value = true
    }
  }
}

async function startStreaming() {
  if (!canStart.value) return

  stopStreaming(false)
  stopWindowRenderLoop(true)
  hasStreamDone = false
  windows.value = []
  meta.value = null
  hasCompleted.value = false
  errorMessage.value = ''

  const formData = new FormData()
  formData.append('qar_id', qarId.value)
  formData.append('model_name', form.value.modelName || 'CNN')
  const seqLen = isITransformer.value ? ITRANSFORMER_FIXED_SEQ_LEN : Number(form.value.seqLen || DEFAULT_SEQ_LEN)
  formData.append('seq_len', String(seqLen))
  formData.append('auto_select', form.value.autoSelect ? '1' : '0')
  formData.append('manual_select', form.value.manualSelect ? '1' : '0')

  streamAbortController = new AbortController()
  isStreaming.value = true
  startElapsedTimer()

  try {
    const token = localStorage.getItem('access_token')
    const headers = {}
    if (token) headers.Authorization = `Bearer ${token}`

    const response = await fetch(STREAM_API_URL, {
      method: 'POST',
      body: formData,
      headers,
      signal: streamAbortController.signal,
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `服务响应异常: ${response.status}`)
    }

    if (!response.body) {
      throw new Error('浏览器不支持流式读取，请升级浏览器')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const state = { buffer: '' }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      state.buffer += decoder.decode(value, { stream: true })
      consumeBuffer(state)
    }

    state.buffer += decoder.decode()
    consumeBuffer(state, true)
    hasStreamDone = true
  } catch (error) {
    if (error?.name !== 'AbortError') {
      errorMessage.value = error?.message || '实时推理失败'
    }
  } finally {
    isStreaming.value = false
    stopElapsedTimer()
    if (streamAbortController) {
      streamAbortController = null
    }
    if (hasStreamDone && !pendingWindowResults.length) {
      hasCompleted.value = true
    }
    persistRiskResultSnapshot()
    renderChart()
    renderDonutChart()
  }
}

function stopStreaming(markStopped = true) {
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  if (markStopped && isStreaming.value && !errorMessage.value) {
    errorMessage.value = '推理已手动停止'
  }
  stopWindowRenderLoop(markStopped)
  if (markStopped) {
    hasStreamDone = false
  }
  isStreaming.value = false
  stopElapsedTimer()
}

function renderChart() {
  if (!chartRef.value) return

  if (!chartInstance) {
    chartInstance = initChart(chartRef.value)
  }

  if (!windows.value.length) {
    chartInstance.setOption({
      animation: false,
      grid: { top: 40, right: 58, bottom: 44, left: 48, containLabel: true },
      xAxis: { type: 'category', data: [] },
      yAxis: [{ type: 'value', min: 0, max: 100 }, { type: 'value', min: 0, max: 100 }],
      series: [],
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            fill: '#7b88a1',
            fontSize: 14,
          },
        },
      ],
    })
    return
  }

  const xAxis = windows.value.map((item) => `#${item.window_index}`)
  const riskSeries = windows.value.map((item) => ({
    value: Number(riskScore(item).toFixed(2)),
    itemStyle: { color: classColor(item.predicted_class_id) },
  }))
  const confidenceSeries = windows.value.map((item) => Number((item.confidence * 100).toFixed(2)))

  chartInstance.setOption({
    animation: true,
    animationDurationUpdate: 280,
    animationEasingUpdate: 'cubicOut',
    grid: { top: 40, right: 58, bottom: 72, left: 54, containLabel: true },
    legend: {
      top: 8,
      textStyle: { color: 'var(--muted)' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        if (!Array.isArray(params) || !params.length) return ''
        const index = Number(params[0].dataIndex || 0)
        const row = windows.value[index]
        if (!row) return ''
        return [
          `窗口 #${row.window_index}`,
          `范围: ${row.start_row} - ${row.end_row}`,
          `类别: ${row.predicted_class_name}`,
          `置信度: ${(row.confidence * 100).toFixed(2)}%`,
          `风险得分: ${riskScore(row).toFixed(1)}`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: xAxis,
      axisLabel: { color: 'var(--muted)' },
      axisLine: { lineStyle: { color: 'var(--chart-axis)' } },
    },
    yAxis: [
      {
        type: 'value',
        min: 0,
        max: 100,
        name: '风险得分',
        splitLine: { lineStyle: { color: 'var(--chart-grid)' } },
        axisLabel: { color: 'var(--muted)' },
      },
      {
        type: 'value',
        min: 0,
        max: 100,
        name: '置信度(%)',
        axisLabel: { color: 'var(--muted)' },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, height: 20, bottom: 16 },
    ],
    series: [
      {
        name: '风险得分',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 22,
        data: riskSeries,
      },
      {
        name: '置信度',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#0f7bff' },
        areaStyle: { color: 'rgba(15, 123, 255, 0.12)' },
        data: confidenceSeries,
      },
    ],
    graphic: [],
  })
}

function renderDonutChart() {
  if (!donutChartRef.value) return

  if (!donutChartInstance) {
    donutChartInstance = initChart(donutChartRef.value)
  }

  if (!classDistribution.value.length) {
    donutChartInstance.setOption({
      animation: false,
      series: [],
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无类别分布',
            fill: '#7b88a1',
            fontSize: 14,
          },
        },
      ],
    })
    return
  }

  const pieData = classDistribution.value.map((item) => ({
    name: `${item.className} (C${item.classId})`,
    value: item.count,
    itemStyle: { color: classColor(item.classId) },
  }))

  donutChartInstance.setOption({
    animation: true,
    animationDurationUpdate: 280,
    animationEasingUpdate: 'cubicOut',
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const total = Math.max(1, windows.value.length)
        const ratio = (Number(params.value || 0) / total) * 100
        return `${params.name}<br/>窗口数: ${params.value} (${ratio.toFixed(1)}%)`
      },
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'middle',
      textStyle: { color: 'var(--muted)' },
    },
    series: [
      {
        type: 'pie',
        radius: ['52%', '72%'],
        center: ['34%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{d}%',
          color: 'var(--muted)',
          fontSize: 11,
        },
        data: pieData,
      },
    ],
    graphic: [
      {
        type: 'group',
        left: '34%',
        top: '50%',
        bounding: 'raw',
        children: [
          {
            type: 'text',
            left: 'center',
            top: -14,
            style: {
              text: '窗口总数',
              fill: '#7b88a1',
              textAlign: 'center',
              fontSize: 12,
            },
          },
          {
            type: 'text',
            left: 'center',
            top: 6,
            style: {
              text: String(windows.value.length),
              fill: '#12223b',
              textAlign: 'center',
              fontSize: 20,
              fontWeight: 700,
            },
          },
        ],
      },
    ],
  })
}

onMounted(() => {
  renderChart()
  renderDonutChart()
  if (typeof ResizeObserver !== 'undefined') {
    chartResizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
      donutChartInstance?.resize()
    })
    if (chartRef.value) chartResizeObserver.observe(chartRef.value)
    if (donutChartRef.value) chartResizeObserver.observe(donutChartRef.value)
  }
  window.addEventListener('resize', handleWindowResize)
})

watch(
  () => route.query?.qar_id,
  () => {
    qarId.value = String(route.query?.qar_id || '').trim()
    restoreCachedRiskResult()
  },
  { immediate: true },
)

watch(
  riskMatrix,
  () => {
    renderChart()
  },
  { deep: true },
)

watch(
  () => form.value.modelName,
  (nextModel, prevModel) => {
    if (String(nextModel || '').trim() === 'iTransformer') {
      form.value.seqLen = ITRANSFORMER_FIXED_SEQ_LEN
      return
    }

    if (String(prevModel || '').trim() === 'iTransformer') {
      form.value.seqLen = DEFAULT_SEQ_LEN
    }
  },
  { immediate: true },
)

function handleWindowResize() {
  chartInstance?.resize()
  donutChartInstance?.resize()
}

onBeforeUnmount(() => {
  persistRiskResultSnapshot()
  stopStreaming(false)
  stopWindowRenderLoop(true)
  if (chartResizeObserver && chartRef.value) {
    chartResizeObserver.unobserve(chartRef.value)
  }
  if (chartResizeObserver && donutChartRef.value) {
    chartResizeObserver.unobserve(donutChartRef.value)
  }
  if (chartResizeObserver) {
    chartResizeObserver.disconnect()
    chartResizeObserver = null
  }
  window.removeEventListener('resize', handleWindowResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (donutChartInstance) {
    donutChartInstance.dispose()
    donutChartInstance = null
  }
})
</script>

<style scoped>
.intro-card {
  margin-bottom: 10px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.form-item {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}

.inline-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.inline-item > span {
  white-space: nowrap;
  min-width: 72px;
}

.upload-params-block {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.compact-item {
  min-width: 148px;
}

.compact-actions {
  margin-top: 0;
  flex: 1 1 auto;
  gap: 8px;
}

.compact-actions .btn {
  min-height: 34px;
  padding: 6px 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1.7fr) repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
  align-items: stretch;
}

.warning-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.summary-card {
  min-height: 118px;
  height: 118px;
  padding: 10px 12px;
  display: grid;
  grid-template-rows: 18px minmax(0, 1fr);
  align-items: stretch;
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.summary-config-card {
  gap: 6px;
}

.summary-head {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 0;
  line-height: 1.1;
  font-weight: 600;
}

.summary-config-card,
.action-card,
.summary-card.stat-card {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--panel-elevated) 88%, transparent) 0%,
    color-mix(in srgb, var(--surface-soft) 92%, transparent) 100%
  );
}

.summary-card .stat-label {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 6px;
}

.summary-card .stat-value {
  font-size: 24px;
  line-height: 1;
  font-weight: 700;
}

.summary-card .stat-label,
.summary-card .summary-head {
  line-height: 1.1;
}

.summary-card .stat-label {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 6px;
}

.summary-card .stat-value {
  margin-top: 2px;
}

.summary-body {
  display: flex;
  align-items: center;
  min-width: 0;
}

.summary-card.stat-card .summary-body {
  align-items: flex-start;
  padding-top: 6px;
}

.summary-card .with-chip {
  display: flex;
  align-items: center;
  min-height: 28px;
}

.summary-card .class-chip {
  min-height: 26px;
}

.action-card {
  min-height: 118px;
}

.action-card .summary-body {
  justify-content: center;
  align-items: center;
}

.action-card .compact-actions {
  height: 100%;
  width: auto;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin: 0 auto;
}

.action-card .action-row {
  margin-top: 0;
}

.action-card .stream-status {
  margin-left: auto;
}

.action-card .compact-actions .btn {
  width: auto;
  margin-left: 0;
  margin-right: 0;
  min-height: 30px;
  padding-top: 5px;
  padding-bottom: 5px;
}

.action-card .compact-actions .icon-action-btn {
  width: 42px;
  height: 42px;
  aspect-ratio: 1 / 1;
  flex: 0 0 42px;
  min-height: 42px;
  border-radius: 50%;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.icon-action-btn .material-symbols-outlined {
  font-size: 22px;
}

.switch-row {
  margin-top: 8px;
}

.switch-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.action-row {
  margin-top: 6px;
}

.stream-status {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0 10px;
  font-size: 12px;
  border: 1px solid transparent;
}

.stream-status.is-idle {
  color: var(--muted);
  background: color-mix(in srgb, var(--surface-soft) 80%, transparent);
}

.stream-status.is-running {
  color: color-mix(in srgb, var(--brand) 85%, #fff 15%);
  border-color: color-mix(in srgb, var(--brand) 35%, transparent);
  background: color-mix(in srgb, var(--brand) 10%, transparent);
}

.stream-status.is-done {
  color: #1d9a67;
  border-color: rgba(29, 154, 103, 0.3);
  background: rgba(29, 154, 103, 0.12);
}

.stream-status.is-error {
  color: #b63b3b;
  border-color: rgba(182, 59, 59, 0.3);
  background: rgba(182, 59, 59, 0.1);
}

.summary-config-card .upload-params-block {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}

.summary-config-card .compact-item {
  min-width: 0;
  display: grid;
  gap: 6px;
  padding: 8px;
  border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-soft) 68%, transparent);
}

.summary-config-card .inline-item > span {
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1;
}

.summary-config-card .input-w-sm,
.summary-config-card .input-w-xs {
  width: 100%;
}

.summary-config-card .inline-item {
  display: grid;
  align-items: stretch;
  gap: 6px;
}

.summary-config-card .input {
  min-height: 34px;
  padding: 6px 10px;
}

.summary-grid .stat-card {
  min-height: 72px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 0;
  align-content: initial;
}

.situation-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.situation-card {
  min-height: 0;
  overflow: hidden;
  position: relative;
  z-index: 2;
  background: var(--panel-elevated);
}

.panel-title-row {
  margin-bottom: 8px;
}

.donut-chart {
  height: 260px;
}

.alert-counters {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
}

.counter-item {
  border: 1px solid color-mix(in srgb, var(--border) 82%, transparent);
  border-radius: 10px;
  padding: 10px;
  background: color-mix(in srgb, var(--surface-soft) 70%, transparent);
}

.counter-item.total {
  background: linear-gradient(120deg, color-mix(in srgb, var(--brand) 14%, transparent) 0%, color-mix(in srgb, var(--surface-soft) 82%, transparent) 100%);
}

.counter-label {
  font-size: 12px;
  color: var(--muted);
}

.counter-value {
  margin-top: 4px;
  font-size: 28px;
  font-weight: 700;
}

.counter-value.small {
  font-size: 22px;
}

.matrix-wrap {
  border: 1px solid color-mix(in srgb, var(--border) 82%, transparent);
  border-radius: 10px;
  padding: 10px;
  overflow-x: auto;
  overflow-y: visible;
  max-height: none;
}

.matrix-head {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.matrix-table {
  width: 100%;
}

.matrix-table thead th {
  position: static;
  top: auto;
  z-index: auto;
}

.matrix-table th,
.matrix-table td {
  padding: 8px;
}

.matrix-input {
  min-height: 30px;
  padding: 4px 8px;
  width: 96px;
}

.matrix-note {
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}

.stat-card {
  min-height: 96px;
  display: grid;
  gap: 8px;
  align-content: center;
}

.stat-label {
  color: var(--muted);
  font-size: 12px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
}

.with-chip {
  font-size: 14px;
}

.class-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border-radius: 999px;
  padding: 0 10px;
  font-weight: 600;
  border: 1px solid transparent;
}

.class-chip.level-normal {
  color: #1d9a67;
  border-color: rgba(29, 154, 103, 0.35);
  background: rgba(29, 154, 103, 0.12);
}

.class-chip.level-medium {
  color: #c26a07;
  border-color: rgba(194, 106, 7, 0.35);
  background: rgba(194, 106, 7, 0.12);
}

.class-chip.level-high {
  color: #b63b3b;
  border-color: rgba(182, 59, 59, 0.35);
  background: rgba(182, 59, 59, 0.12);
}

.chart-card {
  margin-bottom: 0;
  position: relative;
  z-index: 1;
  background: var(--panel-elevated);
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.chart-head-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.panel-title {
  margin: 0;
}

.meta-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
  flex-wrap: wrap;
}

.chart-head-tools .meta-summary {
  justify-content: flex-end;
}

.live-chart {
  height: 100%;
  min-height: 320px;
  flex: 1 1 auto;
  margin-top: 10px;
}

.timeline-strip {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(26px, 1fr));
  gap: 6px;
}

.timeline-block {
  min-height: 26px;
  border-radius: 6px;
  font-size: 10px;
  display: grid;
  place-items: center;
  color: #fff;
  opacity: 0.82;
}

.timeline-block.level-normal {
  background: #22a06b;
}

.timeline-block.level-medium {
  background: #ff9800;
}

.timeline-block.level-high {
  background: #d64545;
}

.timeline-block.active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 35%, transparent);
  animation: pulse-border 0.9s ease-in-out infinite alternate;
}

@keyframes pulse-border {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.06);
  }
}

.prob-cell {
  max-width: 420px;
  white-space: normal;
  line-height: 1.4;
}

.empty-cell {
  text-align: center;
  color: var(--muted);
}

.table-card {
  position: relative;
  z-index: 1;
  background: var(--panel-elevated);
}

@media (max-width: 1160px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-config-card .upload-params-block {
    grid-template-columns: 1fr;
  }

  .situation-grid {
    grid-template-columns: 1fr;
  }

  .alert-counters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .live-chart {
    height: 260px;
  }
}

@media (min-width: 1400px) {
  .summary-grid {
    grid-template-columns: minmax(200px, 1.15fr) repeat(5, minmax(0, 1fr));
  }
}
</style>
