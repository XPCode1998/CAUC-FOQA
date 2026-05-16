<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="qarId" @search="handleSearch" />
      </div>
    </template>

    

    <div class="risk-page">
      <div class="stats-grid">
        <div class="card card-pad stat-card">
          <div class="stat-label">超限区间总数</div>
          <div class="stat-value">{{ rows.length }}</div>
        </div>
        <div class="card card-pad stat-card danger">
          <div class="stat-label">高风险区间</div>
          <div class="stat-value">{{ highRiskCount }}</div>
        </div>
        <div class="card card-pad stat-card">
          <div class="stat-label">涉及参数</div>
          <div class="stat-value">{{ parameterCount }}</div>
        </div>
        <div class="card card-pad stat-card">
          <div class="stat-label">最长超限时长</div>
          <div class="stat-value">{{ maxDuration.toFixed(2) }}s</div>
        </div>
      </div>

      <div class="card card-pad risk-analysis-card">
        <div class="risk-analysis-head">
          <div>
            <h3 class="timeline-title">QAR超限分析</h3>

          </div>
          <div class="control-row risk-view-actions">
            <button class="btn" :class="viewMode === 'timeline' ? 'btn-primary' : 'btn-ghost'" @click="switchViewMode('timeline')">
              图表视角
            </button>
            <button class="btn" :class="viewMode === 'table' ? 'btn-primary' : 'btn-ghost'" @click="switchViewMode('table')">
              表格视角
            </button>
          </div>
        </div>

        <div class="risk-analysis-body" :class="`mode-${viewMode}`">
          <section v-show="viewMode !== 'table'" class="timeline-panel">
            <div class="timeline-head">
              <h4 class="timeline-panel-title">参数超限时间分布图</h4>
              <div class="timeline-legend">
                <span v-for="item in legendItems" :key="item.key" class="legend-item">
                  <i class="legend-dot" :style="{ backgroundColor: item.color }"></i>
                  {{ item.label }}
                </span>
              </div>
            </div>

            <div ref="timelineChartRef" class="timeline-chart"></div>
          </section>

          <section v-show="viewMode !== 'timeline'" class="table-panel">
            <div class="table-head">参数超限表格</div>
            <div class="table-shell">
              <table class="plain-table">
                <thead>
                  <tr>
                    <th>参数</th>
                    <th>超限类型</th>
                    <th>风险等级</th>
                    <th>开始时间(s)</th>
                    <th>结束时间(s)</th>
                    <th>时长(s)</th>
                    <th>峰值</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in rows" :key="`${row.parameter}-${row.start_time}-${idx}`">
                    <td>{{ resolveParameterName(row) }}</td>
                    <td>{{ row.exceed_type || '未知类型' }}</td>
                    <td>
                      <span class="severity-chip" :class="severityClass(row.severity)">{{ row.severity || '未标注' }}</span>
                    </td>
                    <td>{{ formatNumber(row.start_time) }}</td>
                    <td>{{ formatNumber(row.end_time) }}</td>
                    <td>{{ formatNumber(row.duration) }}</td>
                    <td>{{ formatValue(row.peak_value, row.unit) }}</td>
                  </tr>
                  <tr v-if="loading">
                    <td colspan="7" class="empty-cell">正在加载超限区间数据...</td>
                  </tr>
                  <tr v-else-if="errorMessage">
                    <td colspan="7" class="empty-cell error">{{ errorMessage }}</td>
                  </tr>
                  <tr v-else-if="hasLoaded && rows.length === 0">
                    <td colspan="7" class="empty-cell">当前 QAR 未检测到超限区间</td>
                  </tr>
                  <tr v-else-if="!qarId">
                    <td colspan="7" class="empty-cell">请先通过顶部“QAR查看”选择 QAR 数据</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { graphic, use, init as initChart } from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components'

import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { apiFlightRiskOverlimit } from '../api/flightApi'
import { formatTableCellValue } from '../utils/tableFormat'
import { getQarPageCache, setQarPageCache } from '../utils/qarPageCache'

use([CustomChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const timelineChartRef = ref(null)
const rows = ref([])
const loading = ref(false)
const hasLoaded = ref(false)
const errorMessage = ref('')
const viewMode = ref('timeline')

const qarId = ref(String(route.query?.qar_id || '').trim())

let chartInstance = null
let chartResizeObserver = null

const comboPalette = ['#c1121f', '#f77f00', '#0081a7', '#1b9aaa', '#4a4e69', '#8338ec', '#3a86ff', '#3a5a40']

const highRiskCount = computed(() => rows.value.filter((item) => item.severity === '高').length)

const parameterCount = computed(() => {
  const set = new Set(rows.value.map((item) => resolveParameterName(item)).filter(Boolean))
  return set.size
})

const maxDuration = computed(() => {
  if (!rows.value.length) return 0
  return rows.value.reduce((acc, item) => Math.max(acc, Number(item.duration) || 0), 0)
})

const parameterAxis = computed(() => {
  return [...new Set(rows.value.map((item) => resolveParameterName(item)).filter(Boolean))]
})

const legendItems = computed(() => {
  const map = new Map()
  rows.value.forEach((item) => {
    const type = item.exceed_type || '未知类型'
    const severity = item.severity || '未标注'
    const key = `${type}-${severity}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: `${type} / ${severity}`,
        color: comboPalette[map.size % comboPalette.length],
      })
    }
  })
  return [...map.values()]
})

const timelineBlocks = computed(() => {
  const colorMap = new Map(legendItems.value.map((item) => [item.key, item.color]))
  const yIndexMap = new Map(parameterAxis.value.map((name, idx) => [name, idx]))

  return rows.value
    .map((item) => {
      const start = Number(item.start_time)
      const end = Number(item.end_time)
      const paramName = resolveParameterName(item)
      if (!Number.isFinite(start) || !Number.isFinite(end) || !paramName) return null

      const s = Math.min(start, end)
      const e = Math.max(start, end)
      const key = `${item.exceed_type || '未知类型'}-${item.severity || '未标注'}`
      return {
        start: s,
        end: e === s ? s + 0.05 : e,
        parameter: paramName,
        yIndex: yIndexMap.get(paramName),
        color: colorMap.get(key) || '#3a86ff',
        exceedType: item.exceed_type || '未知类型',
        severity: item.severity || '未标注',
        duration: Number(item.duration) || 0,
        unit: item.unit || '',
        startValue: item.start_value,
        endValue: item.end_value,
        peakValue: item.peak_value,
      }
    })
    .filter((item) => item && Number.isInteger(item.yIndex))
})

function severityClass(level) {
  if (!level) return 'is-unknown'
  const value = String(level).toLowerCase()
  if (value === '高' || value === 'high') return 'is-high'
  if (value === '中' || value === 'medium') return 'is-medium'
  if (value === '低' || value === 'low') return 'is-low'
  return 'is-unknown'
}

function formatNumber(value) {
  return formatTableCellValue(value, 4, '--')
}

function formatValue(value, unit) {
  const formatted = formatTableCellValue(value, 4, '--')
  if (formatted === '--') return formatted
  return `${formatted} ${unit || ''}`.trim()
}

function resolveParameterName(item) {
  if (!item) return '--'
  return item.parameter || item.parameter_name || '--'
}

function switchViewMode(mode) {
  if (!['timeline', 'table'].includes(mode)) return
  viewMode.value = mode
}

function renderTimeline() {
  if (!timelineChartRef.value) return

  if (!chartInstance) {
    chartInstance = initChart(timelineChartRef.value)
  }

  if (!timelineBlocks.value.length) {
    chartInstance.setOption({
      animation: false,
      grid: { top: 32, right: 14, bottom: 40, left: 14, containLabel: true },
      xAxis: { type: 'value', name: '时间 (s)', min: 0, max: 1 },
      yAxis: { type: 'category', data: parameterAxis.value },
      series: [],
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: loading.value ? '加载中...' : '暂无可视化超限区间',
            fill: '#7b88a1',
            fontSize: 14,
          },
        },
      ],
    })
    return
  }

  const data = timelineBlocks.value.map((item) => [
    item.start,
    item.end,
    item.yIndex,
    item.color,
    item.parameter,
    item.exceedType,
    item.severity,
    item.duration,
    item.unit,
    item.startValue,
    item.endValue,
    item.peakValue,
  ])

  const minStart = Math.min(...timelineBlocks.value.map((item) => item.start))
  const maxEnd = Math.max(...timelineBlocks.value.map((item) => item.end))

  chartInstance.setOption({
    animation: false,
    grid: {
      top: 24,
      right: 14,
      bottom: 62,
      left: 56,
      containLabel: false,
    },
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const v = params.value || []
        return [
          `参数: ${v[4]}`,
          `类型: ${v[5]}`,
          `等级: ${v[6]}`,
          `时间: ${formatNumber(v[0])} - ${formatNumber(v[1])} s`,
          `时长: ${formatNumber(v[7])} s`,
          `峰值: ${formatValue(v[11], v[8])}`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'value',
      name: '时间 (s)',
      min: minStart,
      max: maxEnd,
      splitLine: { lineStyle: { color: 'rgba(125,145,176,0.24)' } },
    },
    yAxis: {
      type: 'category',
      data: parameterAxis.value,
      axisLabel: {
        width: 52,
        margin: 4,
        overflow: 'truncate',
      },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, height: 22, bottom: 18 },
    ],
    series: [
      {
        type: 'custom',
        renderItem(params, api) {
          const categoryIndex = api.value(2)
          const start = api.coord([api.value(0), categoryIndex])
          const end = api.coord([api.value(1), categoryIndex])
          const height = api.size([0, 1])[1] * 0.62
          const width = Math.max(end[0] - start[0], 2)
          const shape = {
            x: start[0],
            y: start[1] - height / 2,
            width,
            height,
          }

          const rectShape = graphic.clipRectByRect(shape, {
            x: params.coordSys.x,
            y: params.coordSys.y,
            width: params.coordSys.width,
            height: params.coordSys.height,
          })

          return rectShape
            ? {
                type: 'rect',
                shape: rectShape,
                style: api.style({
                  fill: api.value(3),
                  stroke: '#ffffff',
                  lineWidth: 0.8,
                  opacity: 0.9,
                }),
              }
            : null
        },
        encode: {
          x: [0, 1],
          y: 2,
        },
        data,
      },
    ],
    graphic: [],
  })
}

async function load() {
  if (!qarId.value) {
    rows.value = []
    hasLoaded.value = false
    errorMessage.value = ''
    await nextTick()
    renderTimeline()
    return
  }

  loading.value = true
  errorMessage.value = ''

  const normalizedQarId = String(qarId.value || '').trim()
  const cachedRows = getQarPageCache('flight-overlimit', normalizedQarId)
  if (Array.isArray(cachedRows)) {
    rows.value = cachedRows
    hasLoaded.value = true
    await nextTick()
    renderTimeline()
  }

  try {
    const data = await apiFlightRiskOverlimit(qarId.value)
    if (data.code === 0) {
      rows.value = data?.data?.exceeded_records || []
      setQarPageCache('flight-overlimit', normalizedQarId, '', rows.value)
      hasLoaded.value = true
    } else {
      throw new Error(data.message || '超限区间数据加载失败')
    }
  } catch (e) {
    rows.value = []
    hasLoaded.value = true
    errorMessage.value = e?.message || '超限区间数据加载失败'
  } finally {
    loading.value = false
    await nextTick()
    renderTimeline()
  }
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
    return
  }

  await load()
}

watch(
  () => route.query?.qar_id,
  () => {
    qarId.value = String(route.query?.qar_id || '').trim()
    load()
  },
  { immediate: true },
)

watch(rows, async () => {
  await nextTick()
  renderTimeline()
})

watch(viewMode, async () => {
  await nextTick()
  renderTimeline()
  chartInstance?.resize()
})

function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (timelineChartRef.value && typeof ResizeObserver !== 'undefined') {
    chartResizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    chartResizeObserver.observe(timelineChartRef.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartResizeObserver) {
    chartResizeObserver.disconnect()
    chartResizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.header-card {
  margin-bottom: 14px;
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.header-title {
  margin: 0 0 6px;
  font-size: 22px;
  line-height: 1.25;
}

.header-meta {
  flex-shrink: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-soft) 86%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 86%, transparent);
  display: grid;
  gap: 2px;
}

.meta-label {
  color: var(--muted);
  font-size: 12px;
}

.meta-value {
  font-size: 14px;
  color: var(--text);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.risk-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.stat-card {
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.stat-card.danger {
  background: linear-gradient(
    120deg,
    color-mix(in srgb, var(--danger) 12%, var(--panel-elevated)) 0%,
    color-mix(in srgb, var(--surface-soft) 96%, transparent) 100%
  );
}

.stat-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  line-height: 1;
  font-weight: 700;
}

.risk-analysis-card {
  margin-bottom: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.risk-analysis-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.risk-analysis-subtitle {
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}

.risk-view-actions {
  justify-content: flex-end;
}

.risk-analysis-body {
  flex: 1;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: grid;
  gap: 12px;
}

.risk-analysis-body.mode-timeline,
.risk-analysis-body.mode-table {
  grid-template-rows: minmax(0, 1fr);
}

.timeline-panel,
.table-panel {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}

.timeline-panel-title,
.table-head {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.timeline-title {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  font-weight: 700;
  color: var(--text);
}

.timeline-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.timeline-chart {
  width: 100%;
  flex: 1 1 auto;
  min-height: 260px;
  height: 100%;
}

.table-shell {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow-x: auto;
  overflow-y: auto;
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  border-radius: 12px;
}

.plain-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
}

.plain-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--panel-elevated);
  text-align: left;
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  padding: 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.plain-table tbody td {
  padding: 10px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
}

.empty-cell {
  text-align: center;
  color: var(--muted);
  padding: 18px 8px;
}

.empty-cell.error {
  color: var(--danger);
}

.severity-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.severity-chip.is-high {
  color: #8f2b2b;
  background: color-mix(in srgb, var(--danger) 18%, #fff);
}

.severity-chip.is-medium {
  color: #7b5b05;
  background: #ffeec2;
}

.severity-chip.is-low {
  color: #146847;
  background: #d5f3e8;
}

.severity-chip.is-unknown {
  color: var(--muted);
  background: color-mix(in srgb, var(--surface-soft) 94%, transparent);
}

@media (max-width: 1100px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .timeline-chart {
    min-height: 300px;
  }
}

@media (max-width: 760px) {
  .header-main {
    flex-direction: column;
    align-items: stretch;
  }

  .header-meta {
    width: 100%;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .timeline-chart {
    min-height: 260px;
  }
}
</style>
