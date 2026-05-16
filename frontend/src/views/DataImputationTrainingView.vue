<template>
  <MainLayout>
    <div class="training-page">
      <div class="card card-pad training-card">
        <div class="training-head">
          <h3 class="panel-title">模型训练配置</h3>
          <div class="training-actions compact-actions">
            <button
              class="btn icon-action-btn"
              :class="streamTraining ? 'btn-danger' : 'btn-primary'"
              type="button"
              @click="toggleStreamTrain"
              :title="streamTraining ? '停止训练' : '开始训练'"
              :aria-label="streamTraining ? '停止训练' : '开始训练'"
            >
              <span class="material-symbols-outlined" aria-hidden="true">{{ streamTraining ? 'stop_circle' : 'handyman' }}</span>
            </button>
            <button
              class="btn btn-ghost icon-action-btn"
              type="button"
              @click="resetForm"
              :disabled="streamTraining"
              title="重置参数"
              aria-label="重置参数"
            >
              <span class="material-symbols-outlined" aria-hidden="true">settings_backup_restore</span>
            </button>
          </div>
        </div>

        <div class="form-grid">
          <label class="form-item">
            <span>模型</span>
            <select v-model="form.model" class="input">
              <option value="LGTDM">LGTDM</option>
              <option value="I2TDM">I2TDM</option>
              <option value="CSDI">CSDI</option>
            </select>
          </label>

          <label class="form-item">
            <span>扩散步数 diff_steps</span>
            <input v-model.number="form.diff_steps" class="input" type="number" min="1" step="1" />
          </label>

          <label class="form-item">
            <span>扩散层数 diff_layers</span>
            <input v-model.number="form.diff_layers" class="input" type="number" min="1" step="1" />
          </label>

  
          <label class="form-item">
            <span>嵌入维度 res_channels</span>
            <input v-model.number="form.res_channels" class="input" type="number" min="1" step="1" />
          </label>

          <label class="form-item">
            <span>时序注意力维度 d_model</span>
            <input v-model.number="form.d_model" class="input" type="number" min="1" step="1" />
          </label>

          <label class="form-item">
            <span>噪声生成方式 beta_schedule</span>
            <select v-model="form.beta_schedule" class="input">
              <option value="quad">quad</option>
              <option value="linear">linear</option>
              <option value="cosine">cosine</option>
            </select>
          </label>

          <label class="form-item">
            <span>噪声区间起点 beta_start</span>
            <input v-model.number="form.beta_start" class="input" type="number" min="0" step="0.0001" />
          </label>

          <label class="form-item">
            <span>噪声区间终点 beta_end</span>
            <input v-model.number="form.beta_end" class="input" type="number" min="0" step="0.0001" />
          </label>

          <label class="form-item">
            <span>序列长度 seq_len</span>
            <input v-model.number="form.seq_len" class="input" type="number" min="1" step="1" />
          </label>

          <label class="form-item">
            <span>只填充缺失部位 only_generate_missing</span>
            <select v-model.number="form.only_generate_missing" class="input">
              <option :value="1">True</option>
              <option :value="0">False</option>
            </select>
          </label>


          <label class="form-item">
            <span>批量大小 batch_size</span>
            <input v-model.number="form.batch_size" class="input" type="number" min="1" step="1" />
          </label>

          
          <label class="form-item">
            <span>训练轮数 train_epochs</span>
            <input v-model.number="form.train_epochs" class="input" type="number" min="1" step="1" />
          </label>

          <label class="form-item">
            <span>损失函数 loss</span>
            <select v-model="form.loss" class="input">
              <option value="l1">l1</option>
              <option value="l2">l2</option>
              <option value="huber">huber</option>
            </select>
          </label>

          <label class="form-item">
            <span>学习率 learning_rate</span>
            <input v-model.number="form.learning_rate" class="input" type="number" min="0.000001" step="0.0001" />
          </label>

          <label class="form-item">
            <span>数据集（QARIDs）</span>
            <input v-model="form.qar_ids_text" class="input" type="text" placeholder="例如: 10001,10002,10003" />
          </label>
        </div>

        <div class="note-text feedback">{{ message }}</div>
      </div>

      <div class="card card-pad monitor-card">
        <h3 class="panel-title">训练过程监控</h3>
        <div class="monitor-grid">
          <div class="monitor-left">
            <div class="monitor-title">训练状态</div>
            <div class="stage-overview">
              <div class="stage-overview-head">
                <span class="stage-badge" :class="{ running: streamTraining }">{{ currentStageLabel }}</span>
                <span class="stage-percent">{{ stageProgressPercent }}%</span>
              </div>
              <div class="stage-progress-track">
                <div class="stage-progress-fill" :style="{ width: `${stageProgressPercent}%` }"></div>
              </div>
            </div>
            <div class="stage-flow-wrap">
              <div class="stage-line-track"></div>
              <div class="stage-line-fill" :style="{ transform: `scaleX(${stageLinePercent / 100})` }"></div>
              <div class="stage-list">
                <div
                  v-for="(stage, idx) in stageDisplayList"
                  :key="stage.key"
                  class="stage-node"
                  :class="{
                    active: stage.key === currentStageKey,
                    done: stageRank(stage.key) < stageRank(currentStageKey),
                  }"
                >
                  <span class="node-circle">{{ idx + 1 }}</span>
                  <span class="node-label">{{ stage.label }}</span>
                </div>
              </div>
            </div>

            <div class="status-log-wrap">
              <div class="status-title">训练状态流</div>
              <div class="status-log-list">
                <div v-for="(item, idx) in statusEvents" :key="idx" class="status-log-item">
                  <span class="status-stage">{{ item.stage || item.event }}</span>
                  <span class="status-text">{{ item.text }}</span>
                </div>
                <div v-if="!statusEvents.length" class="status-log-empty">等待训练日志...</div>
              </div>
            </div>

          </div>

          <div class="monitor-right">
            <div class="monitor-title">指标可视化</div>
            <div class="metrics-kpi-row">
              <div class="metrics-kpi-card">
                <div class="kpi-name">当前 Epoch</div>
                <div class="kpi-value">{{ latestEpochText }}</div>
              </div>
              <div class="metrics-kpi-card">
                <div class="kpi-name">当前 Loss</div>
                <div class="kpi-value">{{ latestLossText }}</div>
              </div>
              <div class="metrics-kpi-card">
                <div class="kpi-name">当前 Val Loss</div>
                <div class="kpi-value">{{ latestValLossText }}</div>
              </div>
            </div>
            <div ref="metricsChartRef" class="metrics-chart"></div>
          </div>
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { init as initChart, use } from 'echarts/core'
import MainLayout from '../layouts/MainLayout.vue'
import { apiDataImputationTrainHyperparams } from '../api/dataApi'
import {
  imputationTrainStreamState,
  startImputationTrainStream,
  stopImputationTrainStream,
} from '../services/dataImputationTrainStream'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const defaultForm = {
  model: 'LGTDM',
  diff_steps: 30,
  diff_layers: 4,
  d_model: 128,
  res_channels: 64,
  beta_schedule: 'quad',
  beta_start: 0.0001,
  beta_end: 0.5,
  qar_ids_text: 'all',
  seq_len: 150,
  batch_size: 4,
  only_generate_missing: 1,
  train_epochs: 1,
  loss: 'l2',
  learning_rate: 0.001,
}

const form = ref({ ...defaultForm })
const message = computed(() => imputationTrainStreamState.message)
const resultText = computed(() => imputationTrainStreamState.resultText)
const streamTraining = computed(() => imputationTrainStreamState.streamTraining)
const streamMeta = computed(() => imputationTrainStreamState.streamMeta)
const streamProgressText = computed(() => imputationTrainStreamState.streamProgressText)
const statusEvents = computed(() => imputationTrainStreamState.statusEvents)
const metricsChartRef = ref(null)
let metricsChartInstance = null
let metricsResizeObserver = null

const stageDisplayList = [
  { key: 'dataset', label: '数据集构建' },
  { key: 'model', label: '模型构建' },
  { key: 'training', label: '训练中' },
  { key: 'done', label: '训练完毕' },
]

const stageOrder = ['dataset', 'model', 'training', 'done']

const currentStageKey = computed(() => {
  if (!statusEvents.value.length) return streamTraining.value ? 'dataset' : ''
  const latest = statusEvents.value[statusEvents.value.length - 1]
  return normalizeStage(latest.stage || latest.event || '')
})

const currentStageLabel = computed(() => {
  const hit = stageDisplayList.find((item) => item.key === currentStageKey.value)
  if (hit) return hit.label
  return streamTraining.value ? '准备中' : '待开始'
})

const stageProgressPercent = computed(() => {
  const rank = stageRank(currentStageKey.value)
  if (rank < 0) return 0
  const ratio = (rank + 1) / stageDisplayList.length
  return Number((ratio * 100).toFixed(1))
})

const stageLinePercent = computed(() => {
  const rank = stageRank(currentStageKey.value)
  if (rank < 0) return 0
  if (stageDisplayList.length <= 1) return 100
  return Number(((rank / (stageDisplayList.length - 1)) * 100).toFixed(1))
})

const metricPoints = computed(() => {
  const points = []
  for (const item of statusEvents.value) {
    const hasEpoch = Number.isFinite(item.epoch)
    const hasLoss = Number.isFinite(item.loss)
    const hasValLoss = Number.isFinite(item.val_loss)
    if (!hasEpoch && !hasLoss && !hasValLoss) continue
    points.push({
      epoch: hasEpoch ? item.epoch : points.length + 1,
      loss: hasLoss ? item.loss : null,
      val_loss: hasValLoss ? item.val_loss : null,
      avg_loss: Number.isFinite(item.avg_loss) ? item.avg_loss : null,
    })
  }
  return points
})

const latestMetric = computed(() => {
  for (let i = statusEvents.value.length - 1; i >= 0; i -= 1) {
    const item = statusEvents.value[i]
    if (Number.isFinite(item.epoch) || Number.isFinite(item.loss) || Number.isFinite(item.val_loss)) {
      return item
    }
  }
  return null
})

const latestEpochText = computed(() => {
  if (!latestMetric.value || !Number.isFinite(latestMetric.value.epoch)) return '--'
  const total = Number.isFinite(latestMetric.value.total_epochs) ? `/${latestMetric.value.total_epochs}` : ''
  return `${latestMetric.value.epoch}${total}`
})

const latestLossText = computed(() => {
  if (!latestMetric.value || !Number.isFinite(latestMetric.value.loss)) return '--'
  return latestMetric.value.loss.toFixed(4)
})

const latestValLossText = computed(() => {
  if (!latestMetric.value || !Number.isFinite(latestMetric.value.val_loss)) return '--'
  return latestMetric.value.val_loss.toFixed(4)
})

function stageRank(stageKey) {
  const idx = stageOrder.indexOf(stageKey)
  return idx >= 0 ? idx : -1
}

function normalizeStage(input) {
  const text = String(input || '').toLowerCase()
  if (text.includes('stop')) return 'training'
  if (text.includes('done') || text.includes('finish') || text.includes('complete')) return 'done'
  if (text.includes('train') || text.includes('epoch') || text.includes('batch')) return 'training'
  if (text.includes('model') || text.includes('build_model') || text.includes('model_build')) return 'model'
  if (text.includes('data') || text.includes('dataset') || text.includes('prepare')) return 'dataset'
  return streamTraining.value ? 'training' : ''
}

function resetForm() {
  form.value = { ...defaultForm }
  imputationTrainStreamState.message = '已重置为默认训练参数。'
}

function buildPayload() {
  const qarInput = String(form.value.qar_ids_text || '').trim().toLowerCase()
  const qarIds = String(form.value.qar_ids_text || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)

  // 后端约束 qar_ids 为整型数组；输入 all 时用空数组表达“全量数据集”。
  const parsedQarIds = qarInput === 'all'
    ? []
    : qarIds
      .map((id) => Number(id))
      .filter((id) => Number.isInteger(id))

  return {
    model: form.value.model,
    train_epochs: Number(form.value.train_epochs || 1),
    qar_ids: parsedQarIds,
    hyperparams: {
      diff_steps: Number(form.value.diff_steps || 30),
      diff_layers: Number(form.value.diff_layers || 4),
      d_model: Number(form.value.d_model || 128),
      res_channels: Number(form.value.res_channels || 64),
      beta_schedule: form.value.beta_schedule || 'quad',
      beta_start: Number(form.value.beta_start || 0.0001),
      beta_end: Number(form.value.beta_end || 0.5),
      seq_len: Number(form.value.seq_len || 150),
      batch_size: Number(form.value.batch_size || 4),
      only_generate_missing: Number(form.value.only_generate_missing ? 1 : 0),
      train_qar_ids: parsedQarIds,
      train_epochs: Number(form.value.train_epochs || 1),
      loss: form.value.loss || 'l2',
      learning_rate: Number(form.value.learning_rate || 0.001),
    },
  }
}

async function loadDefaultHyperparams() {
  try {
    const res = await apiDataImputationTrainHyperparams()
    if (res.code !== 0) return
    const defaults = res?.data?.defaults || {}
    form.value = {
      ...form.value,
      diff_steps: Number(defaults.diff_steps ?? form.value.diff_steps),
      diff_layers: Number(defaults.diff_layers ?? form.value.diff_layers),
      d_model: Number(defaults.d_model ?? form.value.d_model),
      res_channels: Number(defaults.res_channels ?? form.value.res_channels),
      beta_schedule: String(defaults.beta_schedule ?? form.value.beta_schedule),
      beta_start: Number(defaults.beta_start ?? form.value.beta_start),
      beta_end: Number(defaults.beta_end ?? form.value.beta_end),
      only_generate_missing: Number(
        defaults.only_generate_missing !== undefined
          ? (defaults.only_generate_missing ? 1 : 0)
          : form.value.only_generate_missing,
      ),
      seq_len: Number(defaults.seq_len ?? form.value.seq_len),
      batch_size: Number(defaults.batch_size ?? form.value.batch_size),
      train_epochs: Number(defaults.train_epochs ?? form.value.train_epochs),
      loss: String(defaults.loss ?? form.value.loss),
      learning_rate: Number(defaults.learning_rate ?? form.value.learning_rate),
    }
  } catch (_) {
    // Ignore default loading failure and keep local defaults.
  }
}

function renderMetricsChart() {
  if (!metricsChartRef.value) return
  if (!metricsChartInstance) metricsChartInstance = initChart(metricsChartRef.value)

  if (!metricPoints.value.length) {
    metricsChartInstance.setOption({
      animation: false,
      grid: { top: 36, right: 16, bottom: 36, left: 42, containLabel: true },
      xAxis: { type: 'category', data: [] },
      yAxis: { type: 'value' },
      series: [],
      graphic: [{ type: 'text', left: 'center', top: 'middle', style: { text: '', fill: '#7b88a1', fontSize: 14 } }],
    })
    return
  }

  metricsChartInstance.setOption({
    animation: true,
    animationDurationUpdate: 260,
    grid: { top: 40, right: 16, bottom: 40, left: 50, containLabel: true },
    legend: { top: 8 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: metricPoints.value.map((p, idx) => `E${p.epoch || idx + 1}`),
      axisLabel: { color: 'var(--muted)' },
    },
    yAxis: {
      type: 'value',
      name: 'Loss',
      axisLabel: { color: 'var(--muted)' },
    },
    series: [
      {
        name: 'loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#0f7bff' },
        data: metricPoints.value.map((p) => (Number.isFinite(p.loss) ? p.loss : null)),
      },
      {
        name: 'val_loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#22a06b' },
        data: metricPoints.value.map((p) => (Number.isFinite(p.val_loss) ? p.val_loss : null)),
      },
      {
        name: 'avg_loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#f79009' },
        data: metricPoints.value.map((p) => (Number.isFinite(p.avg_loss) ? p.avg_loss : null)),
      },
    ],
    graphic: [],
  })
}

async function toggleStreamTrain() {
  if (streamTraining.value) {
    await stopImputationTrainStream()
    return
  }
  await startImputationTrainStream(buildPayload())
}

onMounted(() => {
  loadDefaultHyperparams()
  renderMetricsChart()
  if (typeof ResizeObserver !== 'undefined') {
    metricsResizeObserver = new ResizeObserver(() => {
      metricsChartInstance?.resize()
    })
    if (metricsChartRef.value) metricsResizeObserver.observe(metricsChartRef.value)
  }
})

watch(statusEvents, () => {
  renderMetricsChart()
})

onBeforeUnmount(() => {
  if (metricsResizeObserver && metricsChartRef.value) {
    metricsResizeObserver.unobserve(metricsChartRef.value)
    metricsResizeObserver.disconnect()
    metricsResizeObserver = null
  }
  if (metricsChartInstance) {
    metricsChartInstance.dispose()
    metricsChartInstance = null
  }
})
</script>

<style scoped>
.training-page {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 4fr) minmax(0, 6fr);
  gap: 10px;
  overflow: hidden;
}

.training-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 0;
  overflow: hidden;
}

.training-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.panel-title {
  margin: 0;
}

.training-actions {
  margin-top: 0;
  display: inline-flex;
  align-items: center;
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

.monitor-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
  overflow: hidden;
}

.monitor-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.85fr) minmax(0, 2fr);
  gap: 10px;
  min-height: 0;
  align-items: stretch;
}

.monitor-left,
.monitor-right {
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  border-radius: 10px;
  padding: 10px;
  background: color-mix(in srgb, var(--surface-soft) 62%, transparent);
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.monitor-left {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.monitor-right {
  display: flex;
  flex-direction: column;
}

.monitor-title {
  font-size: 12px;
  color: var(--muted);
  font-weight: 700;
  margin-bottom: 10px;
}

.stage-overview {
  margin-bottom: 10px;
}

.stage-overview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.stage-badge {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--muted);
  background: color-mix(in srgb, var(--surface-elevated) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
}

.stage-badge.running {
  color: color-mix(in srgb, var(--brand) 88%, #fff 12%);
  border-color: color-mix(in srgb, var(--brand) 34%, transparent);
  background: color-mix(in srgb, var(--brand) 10%, transparent);
}

.stage-percent {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
}

.stage-progress-track {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: color-mix(in srgb, var(--surface-elevated) 78%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
}

.stage-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #0f7bff 0%, #22a06b 100%);
  transition: width 0.35s ease;
  position: relative;
}

.stage-progress-fill::after {
  content: '';
  position: absolute;
  top: 0;
  left: -26%;
  width: 26%;
  height: 100%;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.62) 100%);
  animation: stage-sweep 1.4s linear infinite;
}

.metrics-chart {
  flex: 1 1 auto;
  min-height: 300px;
  height: auto;
}

.metrics-kpi-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}

.metrics-kpi-card {
  min-height: 54px;
  border: 1px solid color-mix(in srgb, var(--border) 78%, transparent);
  border-radius: 8px;
  padding: 8px;
  background: color-mix(in srgb, var(--surface-elevated) 88%, transparent);
}

.kpi-name {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}

.kpi-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.stage-flow-wrap {
  position: relative;
  margin: 12px 0 10px;
  padding-top: 6px;
}

.stage-line-track,
.stage-line-fill {
  position: absolute;
  top: 24px;
  left: 12.5%;
  right: 12.5%;
  height: 4px;
  border-radius: 999px;
}

.stage-line-track {
  background: color-mix(in srgb, var(--border) 72%, transparent);
}

.stage-line-fill {
  background: linear-gradient(90deg, #0f7bff 0%, #22a06b 100%);
  transform-origin: left center;
  transform: scaleX(0);
  transition: transform 0.35s ease;
}

.stage-list {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.stage-node {
  display: grid;
  justify-items: center;
  gap: 8px;
}

.node-circle {
  width: 44px;
  height: 44px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  border: 2px solid color-mix(in srgb, var(--border) 75%, transparent);
  background: color-mix(in srgb, var(--surface-elevated) 90%, transparent);
  transition: all 0.25s ease;
}

.node-label {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  line-height: 1.15;
}

.stage-node.active .node-circle {
  color: #fff;
  border-color: color-mix(in srgb, var(--brand) 55%, transparent);
  background: color-mix(in srgb, var(--brand) 86%, #0f7bff 14%);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--brand) 20%, transparent);
  animation: stage-dot-pulse 0.9s ease-in-out infinite alternate;
}

.stage-node.active .node-label {
  color: color-mix(in srgb, var(--brand) 88%, #fff 12%);
  font-weight: 600;
}

.stage-node.done .node-circle {
  color: #fff;
  border-color: color-mix(in srgb, #22a06b 65%, transparent);
  background: #22a06b;
}

.stage-node.done .node-label {
  color: #22a06b;
}

.status-log-wrap {
  margin-top: 10px;
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-soft) 60%, transparent);
  padding: 8px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
}

.status-log-list {
  display: grid;
  gap: 6px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.status-log-item {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
}

.status-log-empty {
  color: var(--muted);
  font-size: 12px;
  min-height: 28px;
  display: inline-flex;
  align-items: center;
}

.feedback {
  margin-top: 2px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px 10px;
}

.form-item {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}

.form-item .input {
  width: 100%;
  max-width: 100%;
  min-height: 34px;
}

.form-item-span-2 {
  grid-column: span 2;
}

.action-row {
  display: flex;
  gap: 8px;
}

.result-box {
  margin: 0;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 70%, transparent);
  color: var(--text);
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
}

.status-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  margin-bottom: 8px;
}

.status-stage {
  color: var(--brand);
  font-weight: 600;
}

.status-text {
  color: var(--text);
}

@keyframes stage-dot-pulse {
  from { transform: scale(1); }
  to { transform: scale(1.12); }
}

@keyframes stage-sweep {
  0% { left: -30%; }
  100% { left: 104%; }
}

@media (max-width: 980px) {
  .form-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .monitor-grid {
    grid-template-columns: 1fr;
  }

  .metrics-kpi-row {
    grid-template-columns: 1fr;
  }

  .stage-list {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .training-head {
    align-items: center;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-item-span-2 {
    grid-column: auto;
  }

  .status-log-item {
    grid-template-columns: 1fr;
  }
}
</style>
