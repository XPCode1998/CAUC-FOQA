<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="qarId" @search="preview" />
      </div>
    </template>

    <div class="imputation-page">
      <div class="summary-grid">
        <div class="card card-pad summary-card control-card">
          <div class="summary-head">模型选择</div>
          <div class="summary-body control-grid">
            <label class="inline-field">
              <select v-model="repairModel" class="input input-w-sm">
                <option v-if="loadingModelOptions" value="" disabled>加载模型中...</option>
                <option v-else-if="!modelOptions.length" value="" disabled>暂无可用模型</option>
                <option
                  v-for="(item, idx) in modelOptions"
                  :key="`${item.value}-${idx}`"
                  :value="item.value"
                >{{ item.label }}</option>
              </select>
            </label>
           
          </div>
        </div>

        <div class="card card-pad summary-card stat-card">
          <div class="summary-head">数据长度</div>
          <div class="summary-value">{{ total }}</div>
        </div>

        <div class="card card-pad summary-card stat-card">
          <div class="summary-head">缺失点总数</div>
          <div class="summary-value">{{ missingCellCount }}</div>
        </div>

        <div class="card card-pad summary-card stat-card">
          <div class="summary-head">当前扩散步</div>
          <div class="summary-value">{{ currentStepText }}</div>
        </div>

        <div class="card card-pad summary-card stat-card">
          <div class="summary-head">推理时间(秒)</div>
          <div class="summary-value">{{ inferenceTimeText }}</div>
          <div class="summary-subvalue">目标: &lt; 60s</div>
        </div>

        <div class="card card-pad summary-card stat-card">
          <div class="summary-head">十分位准确率</div>
          <div class="summary-value">{{ decileAccuracyText }}</div>
          <div class="summary-subvalue">缺失点位样本数: {{ decileSampleCount }}</div>
        </div>

        

        <div class="card card-pad summary-card action-card">
          <div class="summary-head">操作</div>
          <div class="summary-body control-row action-row compact-actions">
            <button
              class="btn icon-action-btn"
              :class="repairing ? 'btn-danger' : 'btn-primary'"
              type="button"
              :disabled="!qarId || !repairModel"
              @click="toggleRepairStream"
              :title="repairing ? '停止插补' : '开始插补'"
              :aria-label="repairing ? '停止插补' : '开始插补'"
            >
              <span class="material-symbols-outlined" aria-hidden="true">{{ repairing ? 'stop_circle' : 'handyman' }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="card card-pad chart-card">
        <div class="panel-head">
          <div>
            <h3 class="panel-title">数据修复可视化</h3>
            <div class="section-subtitle">实时更新每个扩散步的QAR数据</div>
          </div>
          <div class="stream-status" :class="repairing ? 'is-running' : 'is-idle'">{{ streamStepText || message || '模型加载中' }}</div>
        </div>
        <div class="table-card realtime-table" :class="{ pulse: tablePulse, 'is-repairing': repairing }">
          <div v-if="repairing" class="table-aurora-mask" aria-hidden="true"></div>
          <div class="realtime-grid-layer">
            <table class="plain-table realtime-grid-table">
              <thead>
                <tr>
                  <th v-for="field in visibleFields" :key="field">{{ field }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in pageRows" :key="idx">
                  <td
                    v-for="field in visibleFields"
                    :key="field"
                    :class="{ 'missing-cell': isOriginallyMissingCell(idx, field) }"
                  >
                    <span :class="{ 'missing-chip': isOriginallyMissingCell(idx, field) }">
                      {{ formatDisplayCellValue(idx, row, field) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { apiDataImputationModels, apiDataImputationPreview } from '../api/dataApi'
import { formatTableCellValue } from '../utils/tableFormat'
import { getQarPageCache, setQarPageCache } from '../utils/qarPageCache'

const qarId = ref('')
const fields = ref([])
const rows = ref([])
const total = ref(0)
const message = ref('')
const repairing = ref(false)
const modelOptions = ref([])
const loadingModelOptions = ref(false)
const repairModel = ref('')
const diffSteps = ref(30)
const maxRowsPerEvent = ref(200)
const streamMeta = ref(null)
const streamStepText = ref('')
const totalSteps = ref(0)
const tablePulse = ref(false)
const rowMissingKeySets = ref([])
const previewMaskColumns = ref([])
const previewMissingMask = ref([])
const previewRowsSnapshot = ref([])
const hasRepairStarted = ref(false)
const groundTruthRows = ref([])
const inferenceSeconds = ref(null)
const decileAccuracy = ref(null)
const decileSampleCount = ref(0)
const modelRequestSentAtMs = ref(0)
const diffusionInferenceStartAtMs = ref(0)
const diffusionInferenceEndAtMs = ref(0)
const ENABLE_IMPUTATION_DEBUG_LOG = true
let repairAbortController = null
let tablePulseTimer = null

const pageRows = computed(() => {
  return rows.value
})

const hiddenFields = new Set(['id', 'qar_id', 'created_at', 'updated_at', 'dSimTime', 'dStepTime'])
const tailDisplayFields = [
  'dGravityAcc', 'dUwg', 'dVwg', 'dWwg',
  'dUTrub', 'dVTrub', 'dWTrub', 'dMass',
]

const visibleFields = computed(() => {
  const source = fields.value.filter((field) => !hiddenFields.has(field))
  if (!source.length) return source

  const tailSet = new Set(tailDisplayFields)
  const normalFields = source.filter((field) => !tailSet.has(field))
  const tailFields = tailDisplayFields.filter((field) => source.includes(field))
  return [...normalFields, ...tailFields]
})

function formatCellValue(value) {
  return formatTableCellValue(value, 4, 'None')
}

function formatRepairCellValue(value) {
  return formatTableCellValue(value, 4, 'None')
}

function isMissingValue(value) {
  return formatCellValue(value) === 'None'
}

function isMissingMaskBit(value) {
  if (value === null || value === undefined || value === '') return false
  if (typeof value === 'boolean') return !value
  const n = Number(value)
  if (Number.isFinite(n)) return n === 0
  const text = String(value).trim().toLowerCase()
  if (['0', 'false', 'f', 'no', 'n'].includes(text)) return true
  if (['1', 'true', 't', 'yes', 'y'].includes(text)) return false
  return false
}

const currentStepText = computed(() => {
  if (!totalSteps.value) return '--'
  return `${Math.min(totalSteps.value, Math.max(0, Number(currentStep.value || 0)))}/${totalSteps.value}`
})

const inferenceTimeText = computed(() => {
  if (!Number.isFinite(inferenceSeconds.value)) return '--'
  return Number(inferenceSeconds.value).toFixed(2)
})

const decileAccuracyText = computed(() => {
  if (!Number.isFinite(decileAccuracy.value)) return '--'
  return `${Number(decileAccuracy.value).toFixed(2)}%`
})

const missingCellCount = computed(() => {
  const missingCellsFromMeta = Number(streamMeta.value?.missing_cells)
  if (Number.isFinite(missingCellsFromMeta)) return missingCellsFromMeta

  const capturedMissingCount = rowMissingKeySets.value.reduce((totalCount, missingKeys) => {
    return totalCount + (missingKeys ? missingKeys.size : 0)
  }, 0)
  if (capturedMissingCount > 0) return capturedMissingCount

  return getRemainingMissingStats().totalMissingCells
})

const currentStep = ref(0)

function syncFromPayload(payload) {
  qarId.value = payload.qar_id
  fields.value = payload.fields || []
  rows.value = Array.isArray(payload.rows)
    ? payload.rows.map((row) => (row && typeof row === 'object' ? { ...row } : row))
    : []
  total.value = payload.total || 0
  previewMaskColumns.value = Array.isArray(payload.mask_columns) ? payload.mask_columns : []
  previewMissingMask.value = Array.isArray(payload.missing_mask) ? payload.missing_mask : []
  previewRowsSnapshot.value = rows.value.map((row) => (row && typeof row === 'object' ? { ...row } : row))
  hasRepairStarted.value = false
  captureMissingWriteMask()
  groundTruthRows.value = []
  resetMetricCards()
}

async function preview() {
  const normalizedQarId = String(qarId.value || '').trim()
  const cached = getQarPageCache('data-imputation-preview', normalizedQarId)
  if (cached && typeof cached === 'object') {
    syncFromPayload(cached)
    message.value = '已加载缓存数据'
  }

  const res = await apiDataImputationPreview({ qar_id: qarId.value })
  if (res.code === 0) {
    syncFromPayload(res.data)
    setQarPageCache('data-imputation-preview', normalizedQarId, '', res.data)
    message.value = '待修复'
  } else {
    message.value = res.message || '加载失败'
  }
}

async function loadModelOptions() {
  loadingModelOptions.value = true
  try {
    const res = await apiDataImputationModels()
    if (res.code !== 0) {
      message.value = res.message || '模型列表加载失败'
      return
    }

    const payload = res.data || {}
    const rawModels = Array.isArray(payload.models) ? payload.models : []

    const nextOptions = rawModels
      .map((item) => {
        if (typeof item === 'string') {
          const value = item.trim()
          if (!value) return null
          return { value, label: value }
        }

        if (item && typeof item === 'object') {
          const fileName = typeof item.file_name === 'string' ? item.file_name.trim() : ''
          const pathName = typeof item.path === 'string' ? item.path.trim() : ''
          const modelName = typeof item.model === 'string' ? item.model.trim() : ''
          // 优先使用上游返回的模型名；未提供时默认回退到 LGTDM-V1。
          const value = modelName || 'LGTDM-V1'
          if (!value) return null

          const label = fileName || pathName || value
          return { value, label }
        }

        return null
      })
      .filter(Boolean)

    modelOptions.value = nextOptions

    if (nextOptions.length && !nextOptions.some((item) => item.value === repairModel.value)) {
      repairModel.value = nextOptions[0].value
    }
  } catch (_) {
    message.value = '模型列表加载失败'
  } finally {
    loadingModelOptions.value = false
  }
}

function pulseTable() {
  tablePulse.value = true
  if (tablePulseTimer) clearTimeout(tablePulseTimer)
  tablePulseTimer = setTimeout(() => {
    tablePulse.value = false
    tablePulseTimer = null
  }, 220)
}

function resetProgressState() {
  currentStep.value = 0
}

function resetMetricCards() {
  inferenceSeconds.value = null
  decileAccuracy.value = null
  decileSampleCount.value = 0
  diffusionInferenceStartAtMs.value = 0
  diffusionInferenceEndAtMs.value = 0
  groundTruthRows.value = []
}

function resetRowsToPreviewSnapshot() {
  rows.value = previewRowsSnapshot.value.map((row) => (row && typeof row === 'object' ? { ...row } : row))
}

function stopProgressState() {
  // 实时表格不需要动画队列，停止时仅保留当前表格与步骤信息。
}

function captureMissingWriteMask() {
  const fromPreviewMask = buildRowMissingKeySetsFromMask(
    rows.value,
    previewMaskColumns.value,
    previewMissingMask.value,
  )
  if (fromPreviewMask.some((item) => item && item.size > 0)) {
    rowMissingKeySets.value = fromPreviewMask
    return
  }

  rowMissingKeySets.value = rows.value.map((row) => {
    const missingKeys = new Set()
    if (!row || typeof row !== 'object') return missingKeys
    Object.keys(row).forEach((key) => {
      if (isMissingValue(row[key])) missingKeys.add(key)
    })
    return missingKeys
  })
}

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return n
}

function computeDecileAccuracy() {
  const baseRows = groundTruthRows.value
  if (!baseRows.length || !rows.value.length) {
    decileAccuracy.value = null
    decileSampleCount.value = 0
    return
  }

  let validCount = 0
  let passCount = 0
  rows.value.forEach((currentRow, rowIdx) => {
    const baseRow = baseRows[rowIdx]
    const missingKeys = rowMissingKeySets.value[rowIdx]
    if (!currentRow || !baseRow) return
    if (!missingKeys || !missingKeys.size) return

    missingKeys.forEach((field) => {
      const original = toFiniteNumber(baseRow[field])
      const filled = toFiniteNumber(currentRow[field])
      if (original === null || filled === null) return

      const denominator = Math.max(Math.abs(original), 1)
      const isPass = Math.abs(filled - original) / denominator < 0.1

      validCount += 1
      if (isPass) passCount += 1
    })
  })

  decileSampleCount.value = validCount
  if (!validCount) {
    decileAccuracy.value = null
    return
  }
  decileAccuracy.value = (passCount / validCount) * 100
}

function isOriginallyMissingCell(rowIdx, field) {
  const missingKeys = rowMissingKeySets.value[rowIdx]
  return !!(missingKeys && missingKeys.has(field))
}

function buildRowMissingKeySetsFromMask(sourceRows, maskColumns, missingMaskRows) {
  if (!Array.isArray(sourceRows) || !sourceRows.length) return []
  if (!Array.isArray(maskColumns) || !maskColumns.length) {
    return sourceRows.map(() => new Set())
  }

  return sourceRows.map((_, rowIdx) => {
    const missingKeys = new Set()
    const rowMask = Array.isArray(missingMaskRows?.[rowIdx]) ? missingMaskRows[rowIdx] : []
    for (let colIdx = 0; colIdx < maskColumns.length; colIdx += 1) {
      const field = maskColumns[colIdx]
      if (!field) continue
      const observed = Number(rowMask[colIdx]) === 1
      if (!observed) {
        missingKeys.add(field)
      }
    }
    return missingKeys
  })
}

function formatDisplayCellValue(rowIdx, row, field) {
  if (!hasRepairStarted.value && isOriginallyMissingCell(rowIdx, field)) {
    return 'None'
  }
  if (repairing.value && isOriginallyMissingCell(rowIdx, field)) {
    return formatRepairCellValue(row?.[field])
  }
  return formatCellValue(row?.[field])
}

function mergeIncomingRowByMissingMask(rowIdx, currentRow, incomingRow) {
  const baseRow = currentRow && typeof currentRow === 'object' ? currentRow : {}
  const patchRow = incomingRow && typeof incomingRow === 'object' ? incomingRow : {}
  const missingKeys = rowMissingKeySets.value[rowIdx] || new Set()

  if (!missingKeys.size) {
    // 当该行没有原始缺失快照时，回退为普通合并，避免整行持续显示 None。
    return { ...baseRow, ...patchRow }
  }

  const merged = { ...baseRow }
  Object.keys(patchRow).forEach((key) => {
    const incomingIsValid = !isMissingValue(patchRow[key])
    if (!incomingIsValid) return

    const isOriginallyMissing = missingKeys.has(key)
    const isCurrentlyMissing = isMissingValue(baseRow[key])
    // 允许两种写入路径：
    // 1) 原始缺失位；2) 当前仍为缺失（处理行索引/快照偏差导致的漏写）。
    if (isOriginallyMissing || isCurrentlyMissing) {
      merged[key] = patchRow[key]
    }
  })
  return merged
}

function flattenNestedArray(value) {
  if (!Array.isArray(value)) return []

  const flattened = []
  const queue = [...value]
  while (queue.length) {
    const item = queue.shift()
    if (Array.isArray(item)) {
      queue.unshift(...item)
      continue
    }
    flattened.push(item)
  }

  return flattened
}

function mergeRowByIncomingMask(rowIdx, currentRow, incomingRow) {
  const baseRow = currentRow && typeof currentRow === 'object' ? currentRow : {}
  const merged = { ...baseRow }
  const patchRow = incomingRow && typeof incomingRow === 'object' ? incomingRow : {}

  Object.keys(patchRow).forEach((key) => {
    if (isMissingValue(patchRow[key])) return
    merged[key] = patchRow[key]
  })

  return merged
}

function shouldAppendIncomingRow(currentRow, incomingRow) {
  if (currentRow && typeof currentRow === 'object') return true
  if (!incomingRow || typeof incomingRow !== 'object') return false

  const expectedFieldCount = fields.value.length
  if (!expectedFieldCount) return true

  // 防止仅包含掩码列的补丁行扩展为“整行 None”。
  const incomingFieldCount = Object.keys(incomingRow).length
  return incomingFieldCount >= Math.max(8, Math.floor(expectedFieldCount * 0.5))
}

function getRemainingMissingStats() {
  const fieldPool = fields.value.length
    ? fields.value
    : (rows.value[0] && typeof rows.value[0] === 'object' ? Object.keys(rows.value[0]) : [])

  const fieldMissingCounts = {}
  let totalMissingCells = 0

  rows.value.forEach((row) => {
    if (!row || typeof row !== 'object') return
    fieldPool.forEach((field) => {
      if (isMissingValue(row[field])) {
        fieldMissingCounts[field] = (fieldMissingCounts[field] || 0) + 1
        totalMissingCells += 1
      }
    })
  })

  return { totalMissingCells, fieldMissingCounts }
}

async function repair(triggerPerfAt = performance.now()) {
  const clickPerfAt = Number.isFinite(triggerPerfAt) ? triggerPerfAt : performance.now()
  const requestPrepareAt = performance.now()

  if (ENABLE_IMPUTATION_DEBUG_LOG) {
    console.info('[imputation] click->request dispatch', {
      qarId: qarId.value,
      modelName: repairModel.value,
      clickToRequestMs: Number((requestPrepareAt - clickPerfAt).toFixed(2)),
      clickIsoTime: new Date().toISOString(),
    })
  }

  repairing.value = true
  resetRowsToPreviewSnapshot()
  hasRepairStarted.value = true
  modelRequestSentAtMs.value = 0
  message.value = ''
  streamMeta.value = null
  streamStepText.value = ''
  resetMetricCards()
  captureMissingWriteMask()
  try {
    const token = localStorage.getItem('access_token')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    const requestBody = JSON.stringify({
      qar_id: qarId.value,
      model_name: repairModel.value,
      diff_steps: Number(diffSteps.value || 30),
      max_rows_per_event: Number(maxRowsPerEvent.value || 200),
    })

    repairAbortController = new AbortController()
    modelRequestSentAtMs.value = performance.now()
    const response = await fetch('/api/v1/data/imputation/stream/repair/by-qar', {
      method: 'POST',
      headers,
      body: requestBody,
      signal: repairAbortController.signal,
    })

    const responsePerfAt = performance.now()
    if (ENABLE_IMPUTATION_DEBUG_LOG) {
      const requestToResponseMs = modelRequestSentAtMs.value
        ? responsePerfAt - modelRequestSentAtMs.value
        : 0
      console.info('[imputation] request->response headers', {
        status: response.status,
        requestToResponseMs: Number(requestToResponseMs.toFixed(2)),
        clickToResponseMs: Number((responsePerfAt - clickPerfAt).toFixed(2)),
      })
    }

    if (!response.ok || !response.body) {
      const text = await response.text()
      throw new Error(text || `服务响应异常: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const state = { buffer: '' }
    let firstChunkLogged = false

    const parseSseEvent = (rawEvent) => {
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

    const normalizeIncomingRows = (value) => {
      return flattenNestedArray(value)
    }

    const mergeRowsByRange = (payload) => {
      const rawRows = Array.isArray(payload.rows)
        ? payload.rows
        : (Array.isArray(payload.final_rows) ? payload.final_rows : [])
      const incomingRows = normalizeIncomingRows(rawRows)
      if (!incomingRows.length) return

      const start = Number(payload.row_start)
      const hasExplicitRange = Number.isFinite(start) && start >= 0
      const shouldReplaceWholeTable = !hasExplicitRange || incomingRows.length >= rows.value.length

      if (shouldReplaceWholeTable) {
        rows.value = incomingRows.map((row) => (row && typeof row === 'object' ? { ...row } : row))
      } else {
        const nextRows = rows.value.slice()
        const baseIndex = hasExplicitRange ? start : 0

        for (let i = 0; i < incomingRows.length; i += 1) {
          const rowIdx = baseIndex + i
          const currentRow = nextRows[rowIdx]
          const incomingRow = incomingRows[i]
          if (!shouldAppendIncomingRow(currentRow, incomingRow)) {
            continue
          }
          nextRows[rowIdx] = mergeRowByIncomingMask(rowIdx, currentRow, incomingRow)
        }

        rows.value = nextRows
      }

      pulseTable()

      total.value = Number(payload.total_rows || payload.rows_count || rows.value.length || total.value)
      if (!fields.value.length && rows.value.length) {
        fields.value = Object.keys(rows.value[0] || {})
      }
    }

    const handleEvent = (payload) => {
      if (!payload || typeof payload !== 'object') return
      if (payload.event === 'meta') {
        streamMeta.value = payload
        if (Array.isArray(payload.mask_columns) && Array.isArray(payload.missing_mask)) {
          previewMaskColumns.value = payload.mask_columns
          previewMissingMask.value = payload.missing_mask
          captureMissingWriteMask()
        }
        resetProgressState()
        totalSteps.value = Number(payload.diff_steps || diffSteps.value || 0)
        return
      }
      if (payload.event === 'diffusion_step') {
        if (Array.isArray(payload.ground_truth)) {
          groundTruthRows.value = payload.ground_truth
        }
        if (!diffusionInferenceStartAtMs.value) {
          diffusionInferenceStartAtMs.value = performance.now()
        }
        diffusionInferenceEndAtMs.value = performance.now()
        const step = Number(payload.step || currentStep.value || 0)
        mergeRowsByRange(payload)
        currentStep.value = step
        totalSteps.value = Number(payload.total_steps || totalSteps.value || 0)
        streamStepText.value = `扩散步 ${payload.step || '--'} / ${payload.total_steps || '--'}`
        return
      }
      if (payload.event === 'done') {
        if (Array.isArray(payload.ground_truth) && payload.ground_truth.length) {
          groundTruthRows.value = payload.ground_truth
        }
        if (!diffusionInferenceStartAtMs.value) {
          diffusionInferenceStartAtMs.value = performance.now()
        }
        diffusionInferenceEndAtMs.value = performance.now()
        const doneStep = Number(payload.total_steps || currentStep.value || 0)
        mergeRowsByRange(payload)
        currentStep.value = doneStep
        totalSteps.value = Number(payload.total_steps || totalSteps.value || 0)
        if (diffusionInferenceStartAtMs.value > 0 && diffusionInferenceEndAtMs.value >= diffusionInferenceStartAtMs.value) {
          inferenceSeconds.value = (diffusionInferenceEndAtMs.value - diffusionInferenceStartAtMs.value) / 1000
        }
        computeDecileAccuracy()
        streamStepText.value = `修复完成`
        const remainingStats = getRemainingMissingStats()
        console.info('[imputation] done remaining missing counts', {
          qarId: qarId.value,
          modelName: repairModel.value,
          totalMissingCells: remainingStats.totalMissingCells,
          fieldMissingCounts: remainingStats.fieldMissingCounts,
        })
        message.value = '插补完成'
        return
      }
      if (payload.event === 'error') {
        throw new Error(payload.message || '上游插补服务返回错误')
      }
    }

    const consumeBuffer = (flush = false) => {
      state.buffer = state.buffer.replace(/\r\n/g, '\n')
      while (true) {
        const marker = state.buffer.indexOf('\n\n')
        if (marker < 0) break
        const rawEvent = state.buffer.slice(0, marker).trim()
        state.buffer = state.buffer.slice(marker + 2)
        if (!rawEvent) continue
        handleEvent(parseSseEvent(rawEvent))
      }
      if (flush && state.buffer.trim()) {
        handleEvent(parseSseEvent(state.buffer.trim()))
        state.buffer = ''
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      if (!firstChunkLogged) {
        firstChunkLogged = true
        const firstChunkPerfAt = performance.now()
        if (ENABLE_IMPUTATION_DEBUG_LOG) {
          console.info('[imputation] response->first chunk', {
            responseToFirstChunkMs: Number((firstChunkPerfAt - responsePerfAt).toFixed(2)),
            clickToFirstChunkMs: Number((firstChunkPerfAt - clickPerfAt).toFixed(2)),
            firstChunkBytes: value?.byteLength || 0,
          })
        }
      }
      state.buffer += decoder.decode(value, { stream: true })
      consumeBuffer(false)
    }
    state.buffer += decoder.decode()
    consumeBuffer(true)
  } catch (e) {
    if (e?.name !== 'AbortError') {
      message.value = e.message || '插补失败'
    }
  } finally {
    stopProgressState()
    repairing.value = false
    repairAbortController = null
  }
}

function toggleRepairStream() {
  if (repairing.value) {
    if (repairAbortController) {
      repairAbortController.abort()
      repairAbortController = null
    }
    stopProgressState()
    repairing.value = false
    message.value = '已停止流式插补'
    return
  }
  repair(performance.now())
}

preview()
loadModelOptions()

onMounted(() => {
  // no-op
})

onBeforeUnmount(() => {
  if (repairAbortController) {
    repairAbortController.abort()
    repairAbortController = null
  }
  if (tablePulseTimer) {
    clearTimeout(tablePulseTimer)
    tablePulseTimer = null
  }
})
</script>

<style scoped>
.imputation-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.summary-card {
  min-height: 118px;
  height: 118px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--panel-elevated) 88%, transparent) 0%,
    color-mix(in srgb, var(--surface-soft) 92%, transparent) 100%
  );
}

.summary-head {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 6px;
  font-weight: 600;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
}

.summary-subvalue {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.control-card .summary-body {
  height: calc(100% - 20px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.control-card .control-grid {
  grid-template-columns: 1fr;
  width: min(220px, 100%);
}

.inline-field {
  display: grid;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.action-card .summary-body {
  height: calc(100% - 20px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-row {
  display: flex;
  flex-direction: row;
  gap: 8px;
}

.compact-actions .btn {
  min-height: 34px;
  padding: 6px 12px;
}

.icon-action-btn {
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

.chart-card {
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.panel-title {
  margin: 0;
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

.table-card {
  min-height: 0;
  overflow: hidden;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.realtime-table {
  margin-top: 10px;
  flex: 1;
  position: relative;
  border-radius: 14px;
  isolation: isolate;
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}

.realtime-table table {
  position: relative;
  z-index: 2;
}

.realtime-grid-layer {
  position: relative;
  z-index: 2;
  overflow: auto;
  height: 100%;
  min-height: 0;
}

.table-aurora-mask {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  background:
    radial-gradient(circle at 14% 18%, rgba(33, 236, 255, 0.18), transparent 38%),
    radial-gradient(circle at 78% 72%, rgba(255, 114, 206, 0.17), transparent 42%),
    linear-gradient(
      115deg,
      rgba(27, 188, 255, 0.2) 0%,
      rgba(105, 255, 218, 0.14) 36%,
      rgba(142, 141, 255, 0.16) 64%,
      rgba(255, 124, 198, 0.16) 100%
    );
  background-size: 100% 100%, 100% 100%, 220% 220%;
  background-position: center, center, 0% 50%;
  mix-blend-mode: screen;
  opacity: 0.72;
  z-index: 4;
  pointer-events: none;
  animation: table-aurora-flow 2.9s linear infinite;
}

.realtime-table.is-repairing .realtime-grid-table th,
.realtime-table.is-repairing .realtime-grid-table td {
  background-color: color-mix(in srgb, var(--panel-elevated) 78%, rgba(36, 203, 255, 0.22));
  animation: cell-breathe 1.1s ease-in-out infinite alternate;
}

.realtime-table.is-repairing .realtime-grid-table tbody tr:nth-child(even) td {
  background-color: color-mix(in srgb, var(--surface-soft) 76%, rgba(255, 120, 205, 0.16));
}

.realtime-grid-table td.missing-cell {
  background: transparent;
}

.realtime-grid-table td .missing-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 2px 10px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, #ff7aa8 62%, transparent);
  background: color-mix(in srgb, #ff7aa8 14%, var(--surface-soft));
  color: color-mix(in srgb, #ff4f8b 72%, #ffffff 28%);
  font-weight: 600;
}

.realtime-table.is-repairing .realtime-grid-table td .missing-chip {
  border-color: color-mix(in srgb, #ff84b3 74%, transparent);
  box-shadow: 0 0 0 1px rgba(255, 132, 179, 0.16);
}

.realtime-table.is-repairing::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 14px;
  background: conic-gradient(
    from 0deg,
    rgba(42, 224, 255, 1) 0deg,
    rgba(0, 176, 255, 0.98) 52deg,
    rgba(92, 250, 199, 1) 118deg,
    rgba(126, 138, 255, 1) 198deg,
    rgba(255, 109, 194, 0.98) 274deg,
    rgba(42, 224, 255, 1) 360deg
  );
  background-size: 140% 140%;
  padding: 3px;
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  z-index: 1;
  animation: siri-ring-spin 1.3s linear infinite, siri-ring-glow 1s ease-in-out infinite alternate;
  pointer-events: none;
}

.realtime-table.is-repairing::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 14px;
  background:
    radial-gradient(circle at 15% 20%, rgba(42, 224, 255, 0.34), transparent 42%),
    radial-gradient(circle at 82% 70%, rgba(255, 109, 194, 0.28), transparent 45%),
    conic-gradient(
      from 0deg,
      transparent 0deg,
      rgba(255, 255, 255, 0.92) 42deg,
      transparent 88deg,
      transparent 360deg
    );
  background-size: auto, auto, 200% 200%;
  background-position: center, center, 0% 50%;
  z-index: 0;
  filter: blur(12px);
  box-shadow:
    0 0 22px rgba(42, 224, 255, 0.62),
    0 0 32px rgba(0, 176, 255, 0.38),
    0 0 42px rgba(255, 109, 194, 0.3),
    inset 0 0 18px rgba(126, 138, 255, 0.2);
  animation:
    siri-ring-breathe 0.95s ease-in-out infinite alternate,
    siri-ring-sweep 1.6s linear infinite;
  pointer-events: none;
}

.table-card.pulse {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--brand) 35%, transparent),
    0 0 18px rgba(42, 224, 255, 0.36);
}

@keyframes siri-ring-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes siri-ring-glow {
  from {
    opacity: 0.78;
    filter: saturate(1) brightness(1);
  }
  to { opacity: 1; }
}

@keyframes siri-ring-breathe {
  from {
    opacity: 0.64;
    transform: scale(0.992);
  }
  to {
    opacity: 1;
    transform: scale(1.012);
  }
}

@keyframes siri-ring-sweep {
  from {
    background-position: center, center, 0% 50%;
  }
  to {
    background-position: center, center, 180% 50%;
  }
}

@keyframes table-aurora-flow {
  from {
    background-position: center, center, 0% 50%;
    filter: saturate(1) brightness(1);
  }
  50% {
    filter: saturate(1.18) brightness(1.06);
  }
  to {
    background-position: center, center, 180% 50%;
    filter: saturate(1) brightness(1);
  }
}

@keyframes cell-breathe {
  from {
    filter: brightness(0.98) saturate(1);
  }
  to {
    filter: brightness(1.06) saturate(1.14);
  }
}

@media (max-width: 1180px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .control-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .control-grid {
    grid-template-columns: 1fr;
  }
}
</style>
