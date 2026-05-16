<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="qarIdInput" @search="handleSearch" />
      </div>
    </template>

    <div class="grid flight-preview-grid">
      <div v-if="errorMessage" class="card flight-preview-error">
        {{ errorMessage }}
      </div>

      <div class="card flight-preview-layout-card">
        <div class="flight-preview-layout-shell">
          <aside class="flight-preview-category-aside">
            <button
              v-for="category in categories"
              :key="category.key"
              class="btn flight-preview-category-btn"
              :class="activeCategoryKey === category.key ? 'btn-primary' : 'btn-ghost'"
              @click="switchCategory(category.key)"
            >
              {{ category.name }}
            </button>
          </aside>

          <main class="flight-preview-main">
            <div class="flight-preview-head">
              <div>
                <div class="flight-preview-head-title">图表说明</div>
                <div class="flight-preview-head-desc">{{ activeCategory?.description }}</div>
              </div>

              <div class="flight-preview-head-tools">
                <div v-if="showFieldSelector" class="flight-preview-field-select-wrap">
                <div ref="fieldDropdownRef" class="flight-preview-field-dropdown-root">
                  <button
                    type="button"
                    class="input flight-preview-field-trigger"
                    :disabled="!activeFieldOptions.length"
                    :aria-expanded="isFieldDropdownOpen"
                    @click="toggleFieldDropdown"
                  >
                    <span class="flight-preview-field-trigger-label">{{ fieldDropdownLabel }}</span>
                    <span class="flight-preview-field-trigger-action">{{ isFieldDropdownOpen ? '收起' : '展开' }}</span>
                  </button>

                  <div
                    v-if="isFieldDropdownOpen"
                    class="flight-preview-field-dropdown-panel"
                  >
                    <div class="flight-preview-field-dropdown-actions">
                      <button class="btn btn-ghost flight-preview-field-dropdown-btn" @click="selectAllFields">全选</button>
                      <button class="btn btn-ghost flight-preview-field-dropdown-btn" @click="resetFieldSelection">重置</button>
                    </div>
                    <div class="flight-preview-field-dropdown-list">
                      <label
                        v-for="field in activeFieldOptions"
                        :key="field.key"
                        class="flight-preview-field-dropdown-item"
                      >
                        <input v-model="activeFieldKeys" type="checkbox" :value="field.key" @change="syncActiveFieldSelection" />
                        <span class="flight-preview-field-dropdown-item-label">{{ field.label }}{{ field.unit ? ` · ${field.unit}` : '' }}</span>
                      </label>
                    </div>
                    <div class="flight-preview-field-dropdown-tip">支持多选，点击空白处可收起下拉面板。</div>
                  </div>
                </div>
              </div>
              </div>
            </div>

            <div class="flight-preview-chart-stage" :class="{ 'flight-preview-chart-stage-single': isLineChartMode || isPfdMode }">
              <div v-if="isLineChartMode" ref="chartRef" class="flight-preview-chart-canvas"></div>

              <div v-else-if="isPfdMode" class="speed-pfd-combo">
                <div class="pfd-wrap pfd-wrap-portrait">
                  <div class="pfd-screen pfd-screen-compact">
                  <section class="pfd-tape pfd-speed-tape">
                    <div class="pfd-tape-title pfd-tape-title-alert">SPD SEL</div>
                    <div class="pfd-tape-scale">
                      <div
                        v-for="tick in pfdSpeedTicks"
                        :key="`spd-${tick}`"
                        class="pfd-tape-tick"
                        :style="{ top: `calc(var(--pfd-tape-center, 50%) + ${(pfdState.iasKt - tick) * 2.2}px)` }"
                      >
                        <span class="pfd-tape-tick-line"></span>
                        <span class="pfd-tape-tick-label">{{ Math.round(tick) }}</span>
                      </div>
                      <div class="pfd-tape-current-marker">
                        <span class="pfd-tape-current-marker-segment pfd-tape-current-marker-left"></span>
                        <span class="pfd-tape-current-marker-segment pfd-tape-current-marker-right"></span>
                      </div>
                    </div>
                  </section>

                  <section class="pfd-center-panel">
                    <div class="pfd-roll-scale">
                      <div
                        v-for="mark in pfdRollMarks"
                        :key="`roll-${mark}`"
                        class="pfd-roll-mark"
                        :style="{ transform: `translateX(-50%) rotate(${mark}deg)` }"
                      ></div>
                      <div class="pfd-roll-pointer"></div>
                    </div>

                    <div class="pfd-attitude-window">
                      <div class="pfd-horizon" :style="{ transform: pfdHorizonTransform }">
                        <div class="pfd-sky"></div>
                        <div class="pfd-ground"></div>
                        <div class="pfd-horizon-line"></div>

                        <div
                          v-for="line in pfdPitchLines"
                          :key="`pitch-${line.deg}`"
                          class="pfd-pitch-line"
                          :class="{ major: line.major }"
                          :style="{ transform: `translate(-50%, ${line.offset}px)` }"
                        >
                          <span class="pfd-pitch-label pfd-pitch-label-left">{{ line.label }}</span>
                          <span class="pfd-pitch-center"></span>
                          <span class="pfd-pitch-label pfd-pitch-label-right">{{ line.label }}</span>
                        </div>
                      </div>

                      <div class="pfd-aircraft-symbol">
                        <span class="pfd-wing pfd-wing-left"></span>
                        <span class="pfd-fuselage"></span>
                        <span class="pfd-wing pfd-wing-right"></span>
                      </div>

                      <div class="pfd-slip-scale">
                        <div class="pfd-slip-center"></div>
                        <div class="pfd-slip-ball" :style="{ transform: `translateX(${pfdSlipOffsetPx}px)` }"></div>
                      </div>
                    </div>

                    <div class="pfd-heading-strip">
                      <div
                        v-for="tick in pfdHeadingTicks"
                        :key="`hdg-${tick.value}`"
                        class="pfd-heading-tick"
                        :class="{ major: tick.major }"
                        :style="{ left: `${tick.left}%` }"
                      >
                        <span class="pfd-heading-tick-line"></span>
                        <span v-if="tick.major" class="pfd-heading-tick-label">{{ tick.label }}</span>
                      </div>
                      <div class="pfd-heading-bug">{{ pfdHeadingLabel }}</div>
                    </div>

                    <div class="pfd-info-row">
                      <div class="pfd-info-item">
                        <span class="pfd-info-item-label">Mach</span>
                        <span class="pfd-info-item-value">{{ pfdState.mach.toFixed(2) }}</span>
                      </div>
                      <div class="pfd-info-item">
                        <span class="pfd-info-item-label">Pitch</span>
                        <span class="pfd-info-item-value">{{ pfdState.pitchDeg.toFixed(1) }}°</span>
                      </div>
                      <div class="pfd-info-item">
                        <span class="pfd-info-item-label">Roll</span>
                        <span class="pfd-info-item-value">{{ pfdState.rollDeg.toFixed(1) }}°</span>
                      </div>
                      <div class="pfd-info-item">
                        <span class="pfd-info-item-label">VS</span>
                        <span class="pfd-info-item-value">{{ Math.round(pfdState.vsFpm) }}</span>
                      </div>
                    </div>
                  </section>

                  <section class="pfd-tape pfd-alt-tape">
                    <div class="pfd-tape-title pfd-tape-title-alert">ALT SEL</div>
                    <div class="pfd-tape-scale">
                      <div
                        v-for="tick in pfdAltitudeTicks"
                        :key="`alt-${tick}`"
                        class="pfd-tape-tick"
                        :style="{ top: `calc(var(--pfd-tape-center, 50%) + ${(pfdState.altitudeFt - tick) * 0.22}px)` }"
                      >
                        <span class="pfd-tape-tick-line"></span>
                        <span class="pfd-tape-tick-label">{{ Math.round(tick) }}</span>
                      </div>
                      <div class="pfd-tape-current-marker">
                        <span class="pfd-tape-current-marker-segment pfd-tape-current-marker-left"></span>
                        <span class="pfd-tape-current-marker-segment pfd-tape-current-marker-right"></span>
                      </div>
                    </div>
                  </section>
                  </div>
                </div>

                <div class="gauge-grid-wrap speed-pfd-gauges">
                  <div class="gauge-grid speed-pfd-gauge-grid">
                    <div v-for="(field, idx) in pfdGaugeFieldDefs" :key="field.key" class="gauge-card">
                      <div class="gauge-card-title">{{ field.label }}{{ field.unit ? ` (${field.unit})` : '' }}</div>
                      <div class="gauge-card-canvas" :ref="(el) => setGaugePanelRef(field.key, el)"></div>
                      <div class="gauge-card-index">#{{ idx + 1 }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else-if="isGaugeMode" class="gauge-grid-wrap">
                <div class="gauge-grid">
                  <div v-for="(field, idx) in selectedFieldDefs" :key="field.key" class="gauge-card">
                    <div class="gauge-card-title">{{ field.label }}{{ field.unit ? ` (${field.unit})` : '' }}</div>
                    <div class="gauge-card-canvas" :ref="(el) => setGaugePanelRef(field.key, el)"></div>
                    <div class="gauge-card-index">#{{ idx + 1 }}</div>
                  </div>
                </div>
              </div>

              <div v-else-if="isPositionHeightMode" class="position-height-grid-wrap">
                <div class="position-height-grid">
                  <div class="position-height-left-stack">
                    <div class="position-height-card">
                      <div class="position-height-card-title">二维轨迹图</div>
                      <div class="position-height-card-canvas" :ref="(el) => setPositionHeightPanelRef('xy', el)"></div>
                    </div>

                    <div class="position-height-card">
                      <div class="position-height-card-title">海拔高度 / 离地高度</div>
                      <div class="position-height-card-bottom-canvas" :ref="(el) => setPositionHeightPanelRef('height', el)"></div>
                    </div>
                  </div>

                  <div class="position-height-card position-height-card-right">
                    <div class="position-height-card-title">三维坐标轨迹</div>
                    <div class="position-height-card-canvas" :ref="(el) => setPositionHeightPanelRef('xyz', el)"></div>
                  </div>
                </div>
              </div>

              <div v-else class="aircraft-load-grid-wrap">
                <div class="aircraft-load-grid">
                  <div class="aircraft-load-card aircraft-load-card-bottom">
                    <div class="aircraft-load-card-title">三轴过载时间曲线 (dNx/dNy/dNz)</div>
                    <div class="aircraft-load-card-bottom-canvas" :ref="(el) => setAircraftLoadPanelRef('timeline', el)"></div>
                  </div>
                  <div class="aircraft-load-card aircraft-load-card-top">
                    <div class="aircraft-load-card-title">三维包线图 (dNx-dNy-dNz)</div>
                    <div class="aircraft-load-card-canvas" :ref="(el) => setAircraftLoadPanelRef('gg', el)"></div>
                  </div>
                </div>
              </div>

              <div v-if="!hasData && !loading" class="flight-preview-empty-overlay">
                <div>
                  <div class="flight-preview-empty-title">请先输入 QARID 并点击“查看”</div>
                  <div class="flight-preview-empty-desc">左侧切换类别，右上角下拉多选参数，底部拖动时间轴。</div>
                </div>
              </div>

              <div v-if="loading" class="flight-preview-loading-overlay">
                正在加载飞行参数数据...
              </div>
            </div>

            <div class="flight-preview-footer-row">
              <div v-if="isGaugeMode || isPfdMode" class="gauge-controls-row">
                <div class="gauge-controls">
                  <button class="media-btn media-btn-primary" :disabled="!timeLabels.length" @click="toggleGaugePlayback" title="播放/暂停">
                    <span v-if="!isGaugePlaying">▶</span>
                    <span v-else>❚❚</span>
                  </button>
                  <button
                    class="media-btn media-btn-ghost media-btn-speed"
                    :disabled="!timeLabels.length"
                    @click="cyclePlaybackRate"
                    title="点击切换倍速"
                  >
                    {{ playbackRateLabel }}
                  </button>
                  <div class="gauge-progress-box" :class="{ disabled: !timeLabels.length || gaugePlayMax <= gaugePlayMin }">
                    <input
                      class="gauge-progress-input"
                      type="range"
                      :min="gaugePlayMin"
                      :max="gaugePlayMax"
                      step="1"
                      :disabled="!timeLabels.length || gaugePlayMax <= gaugePlayMin"
                      :value="gaugeCursorIndex"
                      :style="gaugeProgressStyle"
                      @input="onGaugeProgressInput"
                    />
                    <div class="gauge-progress-endpoint">{{ gaugeProgressLabel }}</div>
                  </div>
                </div>
              </div>
              <div v-if="!isGaugeMode && !isPfdMode" class="range-filter" :class="{ disabled: !timeLabels.length }">
                <div class="range-filter-head">
                  <div>开始: <strong>{{ startLabel2 }}</strong></div>
                  <div>结束: <strong>{{ endLabel2 }}</strong></div>
                </div>

                <div class="range-track-wrap">
                  <div class="range-track"></div>
                  <div class="range-track-active" :style="activeTrackStyle"></div>

                  <input
                    class="range-input"
                    type="range"
                    min="0"
                    :max="maxRangeIndex"
                    step="1"
                    :disabled="!timeLabels.length"
                    :value="startIndex"
                    @input="onStartRangeInput"
                  />
                  <input
                    class="range-input"
                    type="range"
                    min="0"
                    :max="maxRangeIndex"
                    step="1"
                    :disabled="!timeLabels.length"
                    :value="endIndex"
                    @input="onEndRangeInput"
                  />
                </div>
              </div>
            </div>

          </main>
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { use, init as initChart } from 'echarts/core'
import { GaugeChart, LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'

import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { apiDataQarIds } from '../api/dataApi'
import { apiFlightCharts } from '../api/flightApi'
import { getQarPageCache, setQarPageCache } from '../utils/qarPageCache'
import 'echarts-gl'

use([LineChart, GaugeChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const qarIdInput = ref(String(route.query.qar_id || '').trim())
const loading = ref(false)
const errorMessage = ref('')
const hasData = ref(false)

const chartRef = ref(null)
const fieldDropdownRef = ref(null)
const gaugePanelRefs = new Map()
let chartInstance = null
const gaugePanelInstances = new Map()
const positionHeightPanelRefs = new Map()
const positionHeightPanelInstances = new Map()
const aircraftLoadPanelRefs = new Map()
const aircraftLoadPanelInstances = new Map()

const startIndex = ref(0)
const endIndex = ref(0)
const activeCategoryKey = ref('speed-acceleration')
const isFieldDropdownOpen = ref(false)
const gaugeCursorIndex = ref(0)
const isGaugePlaying = ref(false)
const gaugePlaybackBaseInterval = 100
const playbackRateOptions = [1, 2, 5, 10]
const playbackRate = ref(1)
const isCategorySwitching = ref(false)
let gaugePlaybackTimer = null
let themeClassObserver = null

function readThemeVar(name, fallback = '') {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function colorWithAlpha(hexColor, alpha) {
  if (typeof hexColor !== 'string') return `rgba(15,123,255,${alpha})`
  const hex = hexColor.trim().replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return `rgba(15,123,255,${alpha})`
  const r = Number.parseInt(hex.slice(0, 2), 16)
  const g = Number.parseInt(hex.slice(2, 4), 16)
  const b = Number.parseInt(hex.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function getChartThemeTokens() {
  return {
    primary: readThemeVar('--chart-primary', '#0f7bff'),
    secondary: readThemeVar('--chart-secondary', '#20b486'),
    danger: readThemeVar('--chart-danger', '#d64545'),
    axis: readThemeVar('--chart-axis', '#c7d4e7'),
    muted: readThemeVar('--chart-muted', '#5e6d88'),
    text: readThemeVar('--chart-text', '#1d2a3a'),
    grid: readThemeVar('--chart-grid', 'rgba(130,146,172,0.28)'),
    tooltipBg: readThemeVar('--chart-tooltip-bg', 'rgba(255,255,255,0.95)'),
    tooltipBorder: readThemeVar('--chart-tooltip-border', '#d9e4f3'),
  }
}

const categories = [
  {
    key: 'speed-acceleration',
    name: '速度与加速度',
    description: '关注航迹速度、真空速、马赫数以及速度变化率等参数',
    fields: [
      { key: 'dGroundspeed', label: '航迹速度', unit: 'kt' },
      { key: 'dTAS', label: '真空速', unit: 'kt' },
      { key: 'dMach', label: '马赫数', unit: 'Mach' },
      { key: 'dU', label: '空速X分量', unit: 'm/s' },
      { key: 'dV', label: '空速Y分量', unit: 'm/s' },
      { key: 'dW', label: '空速Z分量', unit: 'm/s' },
      { key: 'dUkDot', label: 'X轴线加速度', unit: 'm/s²' },
      { key: 'dVkDot', label: 'Y轴线加速度', unit: 'm/s²' },
      { key: 'dWkDot', label: 'Z轴线加速度', unit: 'm/s²' },
    ],
  },
  {
    key: 'attitude-angle',
    name: '姿态角',
    description: '观察迎角、侧滑角、滚转角、俯仰角和航向变化',
    fields: [
      { key: 'dAlpha', label: '迎角', unit: '°' },
      { key: 'dBeta', label: '侧滑角', unit: '°' },
      { key: 'dPhi', label: '滚转角', unit: '°' },
      { key: 'dTheta', label: '俯仰角', unit: '°' },
      { key: 'dPsi', label: '偏航角', unit: '°' },
      { key: 'dChi', label: '航迹方位角', unit: '°' },
      { key: 'dGamma', label: '航迹爬升角', unit: '°' },
    ],
  },
  {
    key: 'position-height',
    name: '位置与高度',
    description: '展示经纬度、海拔与机体位置坐标的时序变化',
    fields: [
      { key: 'dLongitude', label: '经度', unit: '°' },
      { key: 'dLatitude', label: '纬度', unit: '°' },
      { key: 'dASL', label: '海拔高度', unit: 'm' },
      { key: 'dAGL', label: '离地高度', unit: 'm' },
      { key: 'dPosXg', label: '地轴X坐标', unit: 'm' },
      { key: 'dPosYg', label: '地轴Y坐标', unit: 'm' },
      { key: 'dPosZg', label: '地轴Z坐标', unit: 'm' },
    ],
  },
  {
    key: 'external-control',
    name: '飞控外部系统',
    description: '观察操纵面和起落架等飞控外部系统状态',
    fields: [
      { key: 'dtx', label: '副翼偏度', unit: '°' },
      { key: 'dty', label: '方向舵偏度', unit: '°' },
      { key: 'dtz', label: '升降舵偏度', unit: '°' },
      { key: 'LGPos', label: '起落架位置', unit: '%' },
      { key: 'dFlap', label: '襟翼偏度', unit: '°' },
    ],
  },
  {
    key: 'aircraft-load',
    name: '飞行器过载',
    description: '查看机体轴三个方向的过载分量',
    fields: [
      { key: 'dNx', label: 'X轴过载', unit: 'g' },
      { key: 'dNy', label: 'Y轴过载', unit: 'g' },
      { key: 'dNz', label: 'Z轴过载', unit: 'g' },
    ],
  },
  {
    key: 'fuel-engine',
    name: '燃油与发动机',
    description: '涵盖油量、耗油和发动机运行状态。',
    fields: [
      { key: 'gfuel', label: '剩余油量', unit: 'kg' },
      { key: 'gfused', label: '耗油量', unit: 'kg' },
      { key: 'dGtNormal', label: '燃油消耗率', unit: 'kg/s' },
      { key: 'dGfNormal', label: '燃油消耗量', unit: 'kg' },
      { key: 'dGFuel', label: '余油量', unit: 'kg' },
      { key: 'pe_t1', label: '油门杆位置1', unit: '%' },
      { key: 'pe_t2', label: '油门杆位置2', unit: '%' },
      { key: 'rot1', label: '发动机转速1', unit: 'rpm' },
      { key: 'rot2', label: '发动机转速2', unit: 'rpm' },
      { key: 'thrust', label: '发动机推力', unit: 'N' },
    ],
  },
]

const activeFieldKeys = ref(categories[0]?.fields?.map((item) => item.key) || [])
const pfdRequiredFields = [
  'dGroundspeed',
  'dTAS',
  'dMach',
  'dPhi',
  'dTheta',
  'dPsi',
  'dChi',
  'dASL',
  'dAGL',
  'dBeta',
]
const pfdCoveredGaugeKeys = new Set(['dGroundspeed', 'dTAS', 'dMach'])
const pfdGaugePriority = [
  'dUkDot',
  'dVkDot',
  'dWkDot',
  'dU',
  'dV',
  'dW',
]
const pfdGaugePriorityMap = new Map(pfdGaugePriority.map((key, index) => [key, index]))
const pfdRollMarks = [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60]

const activeCategory = computed(() => categories.find((item) => item.key === activeCategoryKey.value) || categories[0])
const activeFieldOptions = computed(() => activeCategory.value?.fields || [])
const gaugeCategoryKeys = new Set(['fuel-engine'])
const isSpeedAccelerationCategory = computed(() => activeCategoryKey.value === 'speed-acceleration')
const isPfdMode = computed(() => isSpeedAccelerationCategory.value)
const isGaugeMode = computed(() => gaugeCategoryKeys.has(activeCategoryKey.value))
const isPositionHeightMode = computed(() => activeCategoryKey.value === 'position-height')
const isAircraftLoadMode = computed(() => activeCategoryKey.value === 'aircraft-load')
const isLineChartMode = computed(() => !isGaugeMode.value && !isPositionHeightMode.value && !isAircraftLoadMode.value && !isPfdMode.value)
const showFieldSelector = computed(() => isLineChartMode.value)
const effectiveFieldKeys = computed(() => {
  if (isPfdMode.value) {
    return Array.from(new Set([...pfdRequiredFields, ...activeFieldOptions.value.map((item) => item.key)]))
  }
  if (isGaugeMode.value) {
    return activeFieldOptions.value.map((item) => item.key)
  }
  if (isPositionHeightMode.value) {
    return activeFieldOptions.value.map((item) => item.key)
  }
  if (isAircraftLoadMode.value) {
    return activeFieldOptions.value.map((item) => item.key)
  }
  return activeFieldKeys.value
})
const fieldDropdownLabel = computed(() => {
  if (!activeFieldOptions.value.length) return '暂无可选参数'
  const selectedCount = activeFieldKeys.value.filter((key) => activeFieldOptions.value.some((item) => item.key === key)).length
  return selectedCount ? `已选择 ${selectedCount} 个参数` : '请选择参数'
})
const selectedFieldDefs = computed(() => {
  const selectedKeys = new Set(effectiveFieldKeys.value)
  const valid = activeFieldOptions.value.filter((item) => selectedKeys.has(item.key))

  if (valid.length) return valid
  const fallback = activeFieldOptions.value[0]
  return fallback ? [fallback] : []
})
const pfdGaugeFieldDefs = computed(() => {
  if (!isPfdMode.value) return selectedFieldDefs.value
  return selectedFieldDefs.value
    .filter((item) => !pfdCoveredGaugeKeys.has(item.key))
    .slice()
    .sort((a, b) => {
      const aRank = pfdGaugePriorityMap.has(a.key) ? pfdGaugePriorityMap.get(a.key) : Number.MAX_SAFE_INTEGER
      const bRank = pfdGaugePriorityMap.has(b.key) ? pfdGaugePriorityMap.get(b.key) : Number.MAX_SAFE_INTEGER
      if (aRank !== bRank) return aRank - bRank
      return a.label.localeCompare(b.label, 'zh-CN')
    })
})

const chartData = ref({ time_label: [], series: {} })

const timeLabels = computed(() => chartData.value.time_label || [])

const rangeStart = computed(() => Math.min(startIndex.value, endIndex.value))
const rangeEnd = computed(() => Math.max(startIndex.value, endIndex.value))
const maxRangeIndex = computed(() => Math.max(0, timeLabels.value.length - 1))
const gaugePlayMin = computed(() => 0)
const gaugePlayMax = computed(() => Math.max(0, timeLabels.value.length - 1))

function formatPlaybackTime(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '00.00'
  return numeric.toFixed(2).padStart(5, '0')
}

const gaugeEndLabel = computed(() => {
  if (!timeLabels.value.length) return '00.00'
  const raw = timeLabels.value[gaugePlayMax.value]
  return formatPlaybackTime(raw)
})
const gaugeCurrentLabel = computed(() => {
  if (!timeLabels.value.length) return '00.00'
  const clamped = clampValue(gaugeCursorIndex.value, gaugePlayMin.value, gaugePlayMax.value)
  const raw = timeLabels.value[clamped]
  return formatPlaybackTime(raw)
})
const gaugeProgressLabel = computed(() => `${gaugeCurrentLabel.value}/${gaugeEndLabel.value}`)
const gaugeProgressStyle = computed(() => {
  if (!timeLabels.value.length || gaugePlayMax.value <= gaugePlayMin.value) {
    return { '--gauge-progress-percent': '0%' }
  }

  const clamped = clampValue(gaugeCursorIndex.value, gaugePlayMin.value, gaugePlayMax.value)
  const progress = ((clamped - gaugePlayMin.value) / (gaugePlayMax.value - gaugePlayMin.value)) * 100
  return { '--gauge-progress-percent': `${progress.toFixed(2)}%` }
})
const playbackRateLabel = computed(() => `${playbackRate.value}x`)

const startLabel = computed(() => {
  if (!timeLabels.value.length) return '-'
  return String(timeLabels.value[rangeStart.value])
})

const endLabel = computed(() => {
  if (!timeLabels.value.length) return '-'
  return String(timeLabels.value[rangeEnd.value])
})

const startLabel2 = computed(() => formatTwoDecimals(timeLabels.value[rangeStart.value]))
const endLabel2 = computed(() => formatTwoDecimals(timeLabels.value[rangeEnd.value]))

const activeTrackStyle = computed(() => {
  if (!maxRangeIndex.value) {
    return { left: '0%', width: '0%' }
  }

  const left = (rangeStart.value / maxRangeIndex.value) * 100
  const right = (rangeEnd.value / maxRangeIndex.value) * 100
  return {
    left: `${left}%`,
    width: `${Math.max(0, right - left)}%`,
  }
})

const filteredLabels = computed(() => {
  if (!timeLabels.value.length) return []
  return timeLabels.value.slice(rangeStart.value, rangeEnd.value + 1)
})

function clampValue(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function normalizeHeading(value) {
  const base = Number(value)
  if (!Number.isFinite(base)) return 0
  return ((base % 360) + 360) % 360
}

function getSeriesNumber(key, index, fallback = 0) {
  const values = chartData.value.series?.[key]
  const value = Array.isArray(values) ? Number(values[index]) : NaN
  return Number.isFinite(value) ? value : fallback
}

const pfdCursorIndex = computed(() => clampValue(gaugeCursorIndex.value, gaugePlayMin.value, gaugePlayMax.value))
const pfdState = computed(() => {
  if (!timeLabels.value.length) {
    return {
      iasKt: 0,
      gsKt: 0,
      mach: 0,
      pitchDeg: 0,
      rollDeg: 0,
      slipDeg: 0,
      headingDeg: 0,
      altitudeFt: 0,
      radioAltFt: 0,
      vsFpm: 0,
    }
  }

  const idx = pfdCursorIndex.value
  const prevIdx = Math.max(0, idx - 1)
  const iasKt = getSeriesNumber('dTAS', idx, getSeriesNumber('dGroundspeed', idx, 0))
  const gsKt = getSeriesNumber('dGroundspeed', idx, iasKt)
  const mach = getSeriesNumber('dMach', idx, 0)
  const pitchDeg = getSeriesNumber('dTheta', idx, 0)
  const rollDeg = getSeriesNumber('dPhi', idx, 0)
  const slipDeg = getSeriesNumber('dBeta', idx, 0)
  const headingDeg = normalizeHeading(getSeriesNumber('dPsi', idx, getSeriesNumber('dChi', idx, 0)))

  const altitudeM = getSeriesNumber('dASL', idx, 0)
  const prevAltitudeM = getSeriesNumber('dASL', prevIdx, altitudeM)
  const radioAltM = getSeriesNumber('dAGL', idx, 0)
  const deltaTime = Number(timeLabels.value[idx]) - Number(timeLabels.value[prevIdx])
  const verticalSpeedMs = idx > 0 && Number.isFinite(deltaTime) && deltaTime > 0 ? (altitudeM - prevAltitudeM) / deltaTime : 0

  return {
    iasKt,
    gsKt,
    mach,
    pitchDeg,
    rollDeg,
    slipDeg,
    headingDeg,
    altitudeFt: altitudeM * 3.2808399,
    radioAltFt: radioAltM * 3.2808399,
    vsFpm: verticalSpeedMs * 196.850394,
  }
})

function buildCenteredTicks(value, step, halfCount) {
  const center = Math.round(value / step) * step
  return Array.from({ length: halfCount * 2 + 1 }, (_, index) => center + (index - halfCount) * step)
}

const pfdSpeedTicks = computed(() => buildCenteredTicks(pfdState.value.iasKt, 10, 6))
const pfdAltitudeTicks = computed(() => buildCenteredTicks(pfdState.value.altitudeFt, 100, 6))
const pfdHeadingLabel = computed(() => String(Math.round(pfdState.value.headingDeg)).padStart(3, '0'))
const pfdSlipOffsetPx = computed(() => clampValue(pfdState.value.slipDeg * 2.2, -36, 36))
const pfdHorizonTransform = computed(() => {
  const roll = clampValue(pfdState.value.rollDeg, -65, 65)
  const pitch = clampValue(pfdState.value.pitchDeg, -25, 25)
  return `translate(-50%, -50%) rotate(${roll}deg) translateY(${pitch * 3}px)`
})
const pfdPitchLines = computed(() => {
  const marks = []
  for (let deg = -30; deg <= 30; deg += 5) {
    if (deg === 0) continue
    const offset = (pfdState.value.pitchDeg - deg) * 3
    if (offset < -150 || offset > 150) continue
    marks.push({
      deg,
      offset,
      major: deg % 10 === 0,
      label: String(Math.abs(deg)),
    })
  }
  return marks
})
const pfdHeadingTicks = computed(() => {
  const list = []
  const center = pfdState.value.headingDeg
  for (let diff = -30; diff <= 30; diff += 5) {
    const value = normalizeHeading(center + diff)
    const rounded = Math.round(value)
    let label = String(rounded)
    if (rounded === 0) label = 'N'
    if (rounded === 90) label = 'E'
    if (rounded === 180) label = 'S'
    if (rounded === 270) label = 'W'
    list.push({
      value: `${rounded}-${diff}`,
      left: ((diff + 30) / 60) * 100,
      major: diff % 10 === 0,
      label,
    })
  }
  return list
})

function normalizeChartsPayload(raw) {
  const source = raw?.charts && typeof raw.charts === 'object' ? raw.charts : raw || {}
  const time_label = Array.isArray(source.time_label)
    ? source.time_label
    : Array.isArray(source.timeLabel)
      ? source.timeLabel
      : []

  const series = {}
  Object.entries(source).forEach(([key, value]) => {
    if (key === 'time_label' || key === 'timeLabel' || key === 'labels') return
    series[key] = Array.isArray(value) ? value : []
  })

  return { time_label, series }
}

function formatTwoDecimals(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(2) : String(value ?? '-')
}

function waitForNextFrame() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

function ensureChart() {
  if (!chartRef.value) return null
  if (chartInstance && chartInstance.getDom && chartInstance.getDom() !== chartRef.value) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (!chartInstance) {
    chartInstance = initChart(chartRef.value, null, { renderer: 'canvas' })
  }
  return chartInstance
}

function setGaugePanelRef(key, element) {
  if (!key) return
  if (element) {
    gaugePanelRefs.set(key, element)
    return
  }
  gaugePanelRefs.delete(key)
}

function disposeGaugePanels(exceptKeys = []) {
  const keep = new Set(exceptKeys)
  Array.from(gaugePanelInstances.keys()).forEach((key) => {
    if (keep.has(key)) return
    const instance = gaugePanelInstances.get(key)
    instance?.dispose()
    gaugePanelInstances.delete(key)
  })
}

function ensureGaugePanelChart(key) {
  const container = gaugePanelRefs.get(key)
  if (!container) return null

  let instance = gaugePanelInstances.get(key)
  if (!instance) {
    instance = initChart(container, null, { renderer: 'canvas' })
    gaugePanelInstances.set(key, instance)
  }
  return instance
}

function setPositionHeightPanelRef(key, element) {
  if (!key) return
  if (element) {
    positionHeightPanelRefs.set(key, element)
    return
  }
  positionHeightPanelRefs.delete(key)
}

function disposePositionHeightPanels(exceptKeys = []) {
  const keep = new Set(exceptKeys)
  Array.from(positionHeightPanelInstances.keys()).forEach((key) => {
    if (keep.has(key)) return
    const instance = positionHeightPanelInstances.get(key)
    instance?.dispose()
    positionHeightPanelInstances.delete(key)
  })
}

function ensurePositionHeightPanelChart(key) {
  const container = positionHeightPanelRefs.get(key)
  if (!container) return null

  let instance = positionHeightPanelInstances.get(key)
  if (!instance) {
    instance = initChart(container, null, { renderer: 'canvas' })
    positionHeightPanelInstances.set(key, instance)
  }
  return instance
}

function setAircraftLoadPanelRef(key, element) {
  if (!key) return
  if (element) {
    aircraftLoadPanelRefs.set(key, element)
    return
  }
  aircraftLoadPanelRefs.delete(key)
}

function disposeAircraftLoadPanels(exceptKeys = []) {
  const keep = new Set(exceptKeys)
  Array.from(aircraftLoadPanelInstances.keys()).forEach((key) => {
    if (keep.has(key)) return
    const instance = aircraftLoadPanelInstances.get(key)
    instance?.dispose()
    aircraftLoadPanelInstances.delete(key)
  })
}

function ensureAircraftLoadPanelChart(key) {
  const container = aircraftLoadPanelRefs.get(key)
  if (!container) return null

  let instance = aircraftLoadPanelInstances.get(key)
  if (!instance) {
    instance = initChart(container, null, { renderer: 'canvas' })
    aircraftLoadPanelInstances.set(key, instance)
  }
  return instance
}

function toNumericSeries(values, start = 0, end = values?.length ? values.length - 1 : -1) {
  if (!Array.isArray(values) || end < start) return []
  return values.slice(start, end + 1).map((value) => {
    const numeric = Number(value)
    return Number.isFinite(numeric) ? numeric : null
  })
}

function buildPositionHeight2DOption(fields) {
  const theme = getChartThemeTokens()
  const longitudeField = fields.find((item) => item.key === 'dLongitude')
  const latitudeField = fields.find((item) => item.key === 'dLatitude')
  const longitudeValues = toNumericSeries(chartData.value.series?.[longitudeField?.key], rangeStart.value, rangeEnd.value)
  const latitudeValues = toNumericSeries(chartData.value.series?.[latitudeField?.key], rangeStart.value, rangeEnd.value)
  const points = longitudeValues.map((lng, idx) => [lng, latitudeValues[idx]])
    .filter((item) => Number.isFinite(item[0]) && Number.isFinite(item[1]))

  if (!points.length) return null

  const lngValues = points.map((item) => item[0])
  const latValues = points.map((item) => item[1])
  const lngMin = Math.min(...lngValues)
  const lngMax = Math.max(...lngValues)
  const latMin = Math.min(...latValues)
  const latMax = Math.max(...latValues)

  return {
    animation: true,
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.text },
      formatter: (params) => {
        const data = params?.data || []
        return [
          `经度: ${formatTwoDecimals(data[0])}`,
          `纬度: ${formatTwoDecimals(data[1])}`,
        ].join('<br/>')
      },
    },
    grid: { left: 54, right: 24, top: 18, bottom: 46 },
    xAxis: {
      type: 'value',
      min: lngMin,
      max: lngMax,
      axisLine: { lineStyle: { color: theme.axis } },
      splitLine: { lineStyle: { color: theme.grid } },
      axisLabel: { color: theme.muted, formatter: (value) => formatTwoDecimals(value) },
    },
    yAxis: {
      type: 'value',
      min: latMin,
      max: latMax,
      axisLine: { lineStyle: { color: theme.axis } },
      splitLine: { lineStyle: { color: theme.grid } },
      axisLabel: { color: theme.muted, formatter: (value) => formatTwoDecimals(value) },
    },
    series: [
      {
        type: 'line',
        data: points,
        smooth: false,
        showSymbol: false,
        lineStyle: { color: theme.primary, width: 2 },
        itemStyle: { color: theme.primary },
      },
    ],
  }
}

function buildPositionHeight3DOption(fields) {
  const theme = getChartThemeTokens()
  const xField = fields.find((item) => item.key === 'dPosXg')
  const yField = fields.find((item) => item.key === 'dPosYg')
  const zField = fields.find((item) => item.key === 'dPosZg')
  const xs = toNumericSeries(chartData.value.series?.[xField?.key], rangeStart.value, rangeEnd.value)
  const ys = toNumericSeries(chartData.value.series?.[yField?.key], rangeStart.value, rangeEnd.value)
  const zs = toNumericSeries(chartData.value.series?.[zField?.key], rangeStart.value, rangeEnd.value)
  const points = xs.map((x, idx) => [x, ys[idx], zs[idx]])
    .filter((item) => Number.isFinite(item[0]) && Number.isFinite(item[1]) && Number.isFinite(item[2]))

  if (!points.length) return null

  return {
    animation: true,
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.text },
      formatter: (params) => {
        const data = params?.data || []
        return [
          `地轴X: ${formatTwoDecimals(data[0])}`,
          `地轴Y: ${formatTwoDecimals(data[1])}`,
          `地轴Z: ${formatTwoDecimals(data[2])}`,
        ].join('<br/>')
      },
    },
    grid3D: {
      show: true,
      boxWidth: 90,
      boxDepth: 90,
      viewControl: {
        projection: 'perspective',
        autoRotate: false,
      },
      axisLine: { lineStyle: { color: theme.axis } },
      axisLabel: { color: theme.muted, formatter: (value) => formatTwoDecimals(value) },
    },
    xAxis3D: { type: 'value', axisLabel: { formatter: (value) => formatTwoDecimals(value) } },
    yAxis3D: { type: 'value', axisLabel: { formatter: (value) => formatTwoDecimals(value) } },
    zAxis3D: { type: 'value', axisLabel: { formatter: (value) => formatTwoDecimals(value) } },
    series: [
      {
        type: 'line3D',
        data: points,
        lineStyle: { width: 4, color: theme.secondary },
      },
    ],
  }
}

function buildPositionHeightCurveOption(fields) {
  const theme = getChartThemeTokens()
  const aslField = fields.find((item) => item.key === 'dASL')
  const aglField = fields.find((item) => item.key === 'dAGL')
  const xLabels = filteredLabels.value
  const aslValues = toNumericSeries(chartData.value.series?.[aslField?.key], rangeStart.value, rangeEnd.value)
  const aglValues = toNumericSeries(chartData.value.series?.[aglField?.key], rangeStart.value, rangeEnd.value)
  const seriesLength = Math.min(xLabels.length, aslValues.length, aglValues.length)

  if (!seriesLength) return null

  const xAxisData = xLabels.slice(0, seriesLength)
  const chartSeries = [
    {
      name: aslField?.label || '海拔高度',
      type: 'line',
      data: aslValues.slice(0, seriesLength),
      smooth: true,
      showSymbol: false,
      itemStyle: { color: theme.primary },
      lineStyle: { color: theme.primary, width: 2 },
    },
    {
      name: aglField?.label || '离地高度',
      type: 'line',
      data: aglValues.slice(0, seriesLength),
      smooth: true,
      showSymbol: false,
      itemStyle: { color: theme.secondary },
      lineStyle: { color: theme.secondary, width: 2 },
    },
  ]

  const nonEmptySeries = chartSeries.filter((series) => Array.isArray(series.data) && series.data.some((value) => value !== null))
  if (!nonEmptySeries.length) return null

  return {
    animation: true,
    grid: { left: 54, right: 26, top: 24, bottom: 48 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.text },
      axisPointer: { type: 'line' },
      formatter: (params) => {
        const items = Array.isArray(params) ? params : [params]
        if (!items.length) return ''

        const header = formatTwoDecimals(items[0]?.axisValue)
        const lines = items
          .filter((item) => item && item.data !== null && item.data !== undefined)
          .map((item) => {
            const value = Array.isArray(item.data) ? item.data[1] : item.data
            return `${item.marker ?? ''}${item.seriesName}: ${formatTwoDecimals(value)}`
          })

        return [header, ...lines].join('<br/>')
      },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    legend: {
      type: 'scroll',
      top: 0,
      textStyle: { color: theme.text },
    },
    xAxis: {
      type: 'category',
      data: xAxisData,
      boundaryGap: false,
      axisLabel: {
        color: theme.muted,
        formatter: (value) => formatTwoDecimals(value),
      },
      axisLine: { lineStyle: { color: theme.axis } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: theme.muted,
        formatter: (value) => formatTwoDecimals(value),
      },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    series: chartSeries,
  }
}

function buildAircraftLoadGGOption(fields) {
  const theme = getChartThemeTokens()
  const nxField = fields.find((item) => item.key === 'dNx')
  const nyField = fields.find((item) => item.key === 'dNy')
  const nzField = fields.find((item) => item.key === 'dNz')
  const nxValues = toNumericSeries(chartData.value.series?.[nxField?.key], rangeStart.value, rangeEnd.value)
  const nyValues = toNumericSeries(chartData.value.series?.[nyField?.key], rangeStart.value, rangeEnd.value)
  const nzValues = toNumericSeries(chartData.value.series?.[nzField?.key], rangeStart.value, rangeEnd.value)
  const points = nxValues
    .map((value, idx) => [value, nyValues[idx], nzValues[idx]])
    .filter((item) => Number.isFinite(item[0]) && Number.isFinite(item[1]) && Number.isFinite(item[2]))

  if (!points.length) return null

  const nxLow = -3
  const nxHigh = 3
  const nyLow = -2
  const nyHigh = 2
  const nzLow = -1
  const nzHigh = 2.5

  const overLimit = points.filter(([nx, ny, nz]) => (
    nx < nxLow || nx > nxHigh || ny < nyLow || ny > nyHigh || nz < nzLow || nz > nzHigh
  ))

  const vertices = [
    [nxLow, nyLow, nzLow],
    [nxHigh, nyLow, nzLow],
    [nxHigh, nyHigh, nzLow],
    [nxLow, nyHigh, nzLow],
    [nxLow, nyLow, nzHigh],
    [nxHigh, nyLow, nzHigh],
    [nxHigh, nyHigh, nzHigh],
    [nxLow, nyHigh, nzHigh],
  ]
  const edgePairs = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ]
  const envelopeSeries = edgePairs.map(([from, to], idx) => ({
    name: idx === 0 ? '阈值包线' : '',
    type: 'line3D',
    data: [vertices[from], vertices[to]],
    lineStyle: { width: 2, color: theme.secondary, opacity: 0.95 },
    tooltip: { show: false },
  }))

  return {
    animation: true,
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.text },
      formatter: (params) => {
        if (params?.seriesType !== 'line3D' && params?.seriesType !== 'scatter3D') return ''
        const data = params?.data || []
        return [
          `dNx: ${formatTwoDecimals(data[0])} g`,
          `dNy: ${formatTwoDecimals(data[1])} g`,
          `dNz: ${formatTwoDecimals(data[2])} g`,
        ].join('<br/>')
      },
    },
    grid3D: {
      show: true,
      boxWidth: 90,
      boxDepth: 90,
      boxHeight: 70,
      axisLine: { lineStyle: { color: theme.axis } },
      axisPointer: { show: false },
      viewControl: {
        projection: 'perspective',
        autoRotate: false,
      },
      light: {
        main: { intensity: 1.1, shadow: false },
        ambient: { intensity: 0.45 },
      },
    },
    xAxis3D: {
      type: 'value',
      name: 'dNx',
      min: Math.min(nxLow, ...points.map((item) => item[0])),
      max: Math.max(nxHigh, ...points.map((item) => item[0])),
      axisLabel: { formatter: (value) => formatTwoDecimals(value) },
    },
    yAxis3D: {
      type: 'value',
      name: 'dNy',
      min: Math.min(nyLow, ...points.map((item) => item[1])),
      max: Math.max(nyHigh, ...points.map((item) => item[1])),
      axisLabel: { formatter: (value) => formatTwoDecimals(value) },
    },
    zAxis3D: {
      type: 'value',
      name: 'dNz',
      min: Math.min(nzLow, ...points.map((item) => item[2])),
      max: Math.max(nzHigh, ...points.map((item) => item[2])),
      axisLabel: { formatter: (value) => formatTwoDecimals(value) },
    },
    series: [
      {
        name: '过载轨迹',
        type: 'line3D',
        data: points,
        lineStyle: { width: 4, color: theme.primary },
      },
      {
        name: '超限点',
        type: 'scatter3D',
        data: overLimit,
        symbolSize: 8,
        itemStyle: { color: theme.danger },
      },
      ...envelopeSeries,
    ],
  }
}

function buildAircraftLoadTimelineOption(fields) {
  const theme = getChartThemeTokens()
  const labels = filteredLabels.value
  const nxField = fields.find((item) => item.key === 'dNx')
  const nyField = fields.find((item) => item.key === 'dNy')
  const nzField = fields.find((item) => item.key === 'dNz')
  const nxValues = toNumericSeries(chartData.value.series?.[nxField?.key], rangeStart.value, rangeEnd.value)
  const nyValues = toNumericSeries(chartData.value.series?.[nyField?.key], rangeStart.value, rangeEnd.value)
  const nzValues = toNumericSeries(chartData.value.series?.[nzField?.key], rangeStart.value, rangeEnd.value)
  const seriesLength = Math.min(labels.length, nxValues.length, nyValues.length, nzValues.length)

  if (!seriesLength) return null

  const xAxisData = labels.slice(0, seriesLength)
  const lineSeries = [
    {
      name: 'dNx',
      color: theme.primary,
      data: nxValues.slice(0, seriesLength),
      low: -3,
      high: 3,
    },
    {
      name: 'dNy',
      color: theme.secondary,
      data: nyValues.slice(0, seriesLength),
      low: -2,
      high: 2,
    },
    {
      name: 'dNz',
      color: theme.danger,
      data: nzValues.slice(0, seriesLength),
      low: -1,
      high: 2.5,
    },
  ]

  const chartSeries = lineSeries.map((item) => ({
    name: item.name,
    type: 'line',
    data: item.data,
    smooth: true,
    showSymbol: false,
    itemStyle: { color: item.color },
    lineStyle: { color: item.color, width: 2 },
    markArea: {
      silent: true,
      itemStyle: { color: colorWithAlpha(item.color, 0.16) },
      data: [[{ yAxis: item.low }, { yAxis: item.high }]],
    },
  }))

  const overLimitScatter = lineSeries.map((item) => ({
    name: `${item.name}超限`,
    type: 'scatter',
    data: item.data
      .map((value, idx) => ({ value: [xAxisData[idx], value] }))
      .filter((point) => Number.isFinite(point.value[1]) && (point.value[1] < item.low || point.value[1] > item.high)),
    symbolSize: 8,
    itemStyle: { color: item.color },
  }))

  return {
    animation: true,
    grid: { left: 54, right: 26, top: 24, bottom: 48 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.text },
      axisPointer: { type: 'line' },
      formatter: (params) => {
        const items = Array.isArray(params) ? params : [params]
        if (!items.length) return ''
        const header = formatTwoDecimals(items[0]?.axisValue)
        const lines = items
          .filter((item) => item && item.seriesName && !item.seriesName.includes('超限') && item.data !== null && item.data !== undefined)
          .map((item) => {
            const value = Array.isArray(item.data) ? item.data[1] : item.data
            return `${item.marker ?? ''}${item.seriesName}: ${formatTwoDecimals(value)}`
          })
        return [header, ...lines].join('<br/>')
      },
    },
    legend: { type: 'scroll', top: 0, textStyle: { color: theme.text } },
    xAxis: {
      type: 'category',
      data: xAxisData,
      boundaryGap: false,
      axisLabel: { color: theme.muted, formatter: (value) => formatTwoDecimals(value) },
      axisLine: { lineStyle: { color: theme.axis } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: theme.muted, formatter: (value) => formatTwoDecimals(value) },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    series: [...chartSeries, ...overLimitScatter],
  }
}

function renderAircraftLoadPanels(fields) {
  disposeGaugePanels([])
  disposePositionHeightPanels([])
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }

  const ggOption = buildAircraftLoadGGOption(fields)
  const timelineOption = buildAircraftLoadTimelineOption(fields)
  const panelOptions = [
    ['gg', ggOption],
    ['timeline', timelineOption],
  ]

  panelOptions.forEach(([key, option]) => {
    const instance = ensureAircraftLoadPanelChart(key)
    if (!instance) return
    if (!option) {
      instance.clear()
      return
    }
    instance.setOption(option, true)
    instance.resize()
  })
}

function renderPositionHeightPanels(fields) {
  disposeGaugePanels([])
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }

  const xyOption = buildPositionHeight2DOption(fields)
  const xyzOption = buildPositionHeight3DOption(fields)
  const curveOption = buildPositionHeightCurveOption(fields)

  const panelOptions = [
    ['xy', xyOption],
    ['xyz', xyzOption],
    ['height', curveOption],
  ]

  panelOptions.forEach(([key, option]) => {
    const instance = ensurePositionHeightPanelChart(key)
    if (!instance) return
    if (!option) {
      instance.clear()
      return
    }
    instance.setOption(option, true)
    instance.resize()
  })
}

function buildGaugePanelOption(field, color) {
  const theme = getChartThemeTokens()
  const values = chartData.value.series?.[field.key]
  const rangeValues = Array.isArray(values)
    ? values.slice(gaugePlayMin.value, gaugePlayMax.value + 1)
    : []
  const numeric = rangeValues
    .map((value) => {
      const n = Number(value)
      return Number.isFinite(n) ? n : null
    })
    .filter((value) => value !== null)

  if (!numeric.length) return null

  const cursor = Math.min(Math.max(gaugeCursorIndex.value, gaugePlayMin.value), gaugePlayMax.value)
  const cursorValue = Array.isArray(values) ? Number(values[cursor]) : NaN
  let current = Number.isFinite(cursorValue) ? cursorValue : null
  if (current === null) {
    for (let i = cursor; i >= gaugePlayMin.value; i -= 1) {
      const candidate = Number(values?.[i])
      if (Number.isFinite(candidate)) {
        current = candidate
        break
      }
    }
  }
  if (current === null) {
    current = numeric[numeric.length - 1]
  }

  let min = Math.min(...numeric)
  let max = Math.max(...numeric)
  if (min === max) {
    const gap = Math.abs(min || 1) * 0.2
    min -= gap
    max += gap
  } else {
    const gap = (max - min) * 0.1
    min -= gap
    max += gap
  }

  min = Math.floor(min)
  max = Math.ceil(max)
  if (max <= min) {
    max = min + 1
  }

  return {
    animation: true,
    series: [
      {
        type: 'gauge',
        min,
        max,
        center: ['50%', '58%'],
        radius: '86%',
        startAngle: 210,
        endAngle: -30,
        splitNumber: 5,
        axisLine: {
          lineStyle: {
            width: 10,
            color: [[1, color]],
          },
        },
        progress: {
          show: true,
          width: 10,
          itemStyle: { color },
        },
        pointer: {
          show: true,
          width: 4,
          length: '62%',
        },
        axisTick: {
          distance: -12,
          length: 4,
          lineStyle: { color: theme.muted },
        },
        splitLine: {
          distance: -12,
          length: 10,
          lineStyle: { color: theme.muted, width: 1 },
        },
        axisLabel: {
          distance: -22,
          color: theme.muted,
          fontSize: 10,
          formatter: (value) => String(Math.round(value)),
        },
        title: {
          show: false,
        },
        detail: {
          valueAnimation: true,
          color: theme.text,
          fontSize: 12,
          offsetCenter: [0, '84%'],
          formatter: (value) => `${Number(value).toFixed(2)}${field.unit ? ` ${field.unit}` : ''}`,
        },
        data: [{ value: current, name: field.label }],
      },
    ],
  }
}

function renderGaugePanels(fields, palette) {
  const keys = fields.map((field) => field.key)
  disposeGaugePanels(keys)

  fields.forEach((field, idx) => {
    const instance = ensureGaugePanelChart(field.key)
    if (!instance) return

    const option = buildGaugePanelOption(field, palette[idx % palette.length])
    if (!option) {
      instance.clear()
      return
    }
    instance.setOption(option, true)
    instance.resize()
  })
}

function renderChart() {
  const theme = getChartThemeTokens()
  const fields = selectedFieldDefs.value
  const labels = filteredLabels.value
  const palette = [theme.primary, theme.secondary, theme.danger, '#f59e0b', '#7c4dff', '#0ea5a4', '#ef4444', '#8b5cf6']

  if (isPfdMode.value) {
    disposePositionHeightPanels([])
    disposeAircraftLoadPanels([])
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    if (!labels.length || !pfdGaugeFieldDefs.value.length) {
      disposeGaugePanels([])
      return
    }
    renderGaugePanels(pfdGaugeFieldDefs.value, palette)
    return
  }

  if (isGaugeMode.value) {
    disposeAircraftLoadPanels([])
    disposePositionHeightPanels([])
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    if (!labels.length || !fields.length) {
      disposeGaugePanels([])
      return
    }
    renderGaugePanels(fields, palette)
    return
  }

  if (isPositionHeightMode.value) {
    disposeAircraftLoadPanels([])
    if (!labels.length || !fields.length) {
      disposeGaugePanels([])
      disposePositionHeightPanels([])
      return
    }
    renderPositionHeightPanels(fields)
    return
  }

  if (isAircraftLoadMode.value) {
    if (!labels.length || !fields.length) {
      disposeGaugePanels([])
      disposePositionHeightPanels([])
      disposeAircraftLoadPanels([])
      return
    }
    renderAircraftLoadPanels(fields)
    return
  }

  disposeGaugePanels([])
  disposePositionHeightPanels([])
  disposeAircraftLoadPanels([])

  const instance = ensureChart()
  if (!instance) return

  if (!labels.length || !fields.length) {
    instance.clear()
    return
  }

  const rawSeries = fields.map((field, idx) => {
    const values = chartData.value.series?.[field.key]
    const numeric = Array.isArray(values)
      ? values.map((value) => {
          const n = Number(value)
          return Number.isFinite(n) ? n : null
        })
      : []

    const sliced = numeric.slice(rangeStart.value, rangeEnd.value + 1)
    return {
      name: field.label,
      type: 'line',
      data: sliced,
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      itemStyle: { color: palette[idx % palette.length] },
      lineStyle: { color: palette[idx % palette.length], width: 2 },
    }
  })

  const nonEmptySeries = rawSeries.filter((series) => Array.isArray(series.data) && series.data.some((v) => v !== null))

  if (!nonEmptySeries.length) {
    instance.clear()
    return
  }

  const seriesLength = Math.min(
    labels.length,
    ...nonEmptySeries.map((series) => series.data.length || labels.length),
  )

  const xAxisData = labels.slice(0, seriesLength)
  const chartSeries = nonEmptySeries.map((series) => ({
    ...series,
    data: series.data.slice(0, seriesLength),
  }))

  const idx = Math.max(0, seriesLength - 1)

  instance.setOption(
    {
      animation: true,
      grid: { left: 54, right: 26, top: 28, bottom: 54 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.text },
        axisPointer: { type: 'line' },
        formatter: (params) => {
          const items = Array.isArray(params) ? params : [params]
          if (!items.length) return ''

          const header = formatTwoDecimals(items[0]?.axisValue)
          const lines = items
            .filter((item) => item && item.data !== null && item.data !== undefined)
            .map((item) => {
              const value = Array.isArray(item.data) ? item.data[1] : item.data
              return `${item.marker ?? ''}${item.seriesName}: ${formatTwoDecimals(value)}`
            })

          return [header, ...lines].join('<br/>')
        },
      },
      dataZoom: [{ type: 'inside', start: 0, end: 100 }],
      legend: {
        type: 'scroll',
        top: 0,
        textStyle: { color: theme.text },
      },
      xAxis: {
        type: 'category',
        data: xAxisData,
        boundaryGap: false,
        axisLine: { lineStyle: { color: theme.axis } },
        axisLabel: {
          color: theme.muted,
          formatter: (value) => formatTwoDecimals(value),
        },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: theme.grid } },
        axisLabel: {
          color: theme.muted,
          formatter: (value) => formatTwoDecimals(value),
        },
      },
      series: chartSeries,
    },
    true,
  )

  instance.resize()

  instance.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: idx })
}

function normalizeFieldSelection() {
  const validKeys = activeFieldOptions.value
    .filter((item) => activeFieldKeys.value.includes(item.key))
    .map((item) => item.key)

  if (validKeys.length) {
    if (validKeys.length !== activeFieldKeys.value.length || validKeys.some((key, index) => key !== activeFieldKeys.value[index])) {
      activeFieldKeys.value = validKeys
    }
    return
  }

  activeFieldKeys.value = activeFieldOptions.value.map((item) => item.key)
}

function syncActiveFieldSelection() {
  normalizeFieldSelection()
}

function toggleFieldDropdown() {
  if (!activeFieldOptions.value.length) return
  isFieldDropdownOpen.value = !isFieldDropdownOpen.value
}

function closeFieldDropdown() {
  isFieldDropdownOpen.value = false
}

function stopGaugePlayback() {
  if (gaugePlaybackTimer) {
    clearInterval(gaugePlaybackTimer)
    gaugePlaybackTimer = null
  }
  isGaugePlaying.value = false
}

function resetGaugePlayback() {
  stopGaugePlayback()
  gaugeCursorIndex.value = gaugePlayMin.value
}

function setPlaybackRate(rate) {
  const normalized = Number(rate)
  if (!playbackRateOptions.includes(normalized)) return
  playbackRate.value = normalized
}

function cyclePlaybackRate() {
  if (!timeLabels.value.length) return
  const currentIndex = playbackRateOptions.indexOf(playbackRate.value)
  const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % playbackRateOptions.length : 0
  setPlaybackRate(playbackRateOptions[nextIndex])
}

function startGaugePlaybackTimer() {
  if (gaugePlaybackTimer) {
    clearInterval(gaugePlaybackTimer)
    gaugePlaybackTimer = null
  }

  const interval = gaugePlaybackBaseInterval
  gaugePlaybackTimer = setInterval(() => {
    if (gaugeCursorIndex.value >= gaugePlayMax.value) {
      stopGaugePlayback()
      gaugeCursorIndex.value = gaugePlayMin.value
      return
    }

    const step = Math.max(1, Math.round(playbackRate.value))
    gaugeCursorIndex.value = Math.min(gaugePlayMax.value, gaugeCursorIndex.value + step)
  }, interval)
}

function toggleGaugePlayback() {
  if ((!isGaugeMode.value && !isPfdMode.value) || !timeLabels.value.length) return

  if (isGaugePlaying.value) {
    stopGaugePlayback()
    return
  }

  if (gaugeCursorIndex.value < gaugePlayMin.value || gaugeCursorIndex.value > gaugePlayMax.value) {
    gaugeCursorIndex.value = gaugePlayMin.value
  }

  isGaugePlaying.value = true
  startGaugePlaybackTimer()
}

async function loadFlightData() {
  const qarId = qarIdInput.value.trim()
  if (!qarId) {
    errorMessage.value = '请输入 QARID 后再查看。'
    hasData.value = false
    chartData.value = { time_label: [], series: {} }
    renderChart()
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const fields = effectiveFieldKeys.value.length
      ? effectiveFieldKeys.value
      : activeFieldOptions.value.slice(0, 1).map((item) => item.key)
    const cacheVariant = `${activeCategoryKey.value}:${fields.join(',')}`
    const cachedPayload = getQarPageCache('flight-visualization', qarId, cacheVariant)
    if (cachedPayload) {
      chartData.value = normalizeChartsPayload(cachedPayload)
      hasData.value = true
      startIndex.value = 0
      endIndex.value = Math.max(0, chartData.value.time_label.length - 1)
      gaugeCursorIndex.value = 0
      stopGaugePlayback()
      await nextTick()
      renderChart()
    }

    const res = await apiFlightCharts(qarId, 2200, fields)

    if (res.code !== 0) {
      throw new Error(res.message || '飞行参数加载失败')
    }

    qarIdInput.value = qarId
    chartData.value = normalizeChartsPayload(res.data)
    setQarPageCache('flight-visualization', qarId, cacheVariant, res.data)
    hasData.value = true
    startIndex.value = 0
    endIndex.value = Math.max(0, chartData.value.time_label.length - 1)
    gaugeCursorIndex.value = 0
    stopGaugePlayback()

    await nextTick()
    await waitForNextFrame()
    renderChart()
    chartInstance?.resize()
  } catch (error) {
    hasData.value = false
    chartData.value = { time_label: [], series: {} }
    stopGaugePlayback()
    errorMessage.value = error?.message || '飞行参数加载失败'
    await nextTick()
    await waitForNextFrame()
    renderChart()
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  loadFlightData()
}

async function switchCategory(key) {
  if (activeCategoryKey.value === key) return
  stopGaugePlayback()
  isCategorySwitching.value = true
  activeCategoryKey.value = key
  const allFields = categories.find((item) => item.key === key)?.fields?.map((item) => item.key) || []
  activeFieldKeys.value = allFields
  gaugeCursorIndex.value = gaugePlayMin.value
  closeFieldDropdown()

  try {
    if (qarIdInput.value.trim()) {
      await loadFlightData()
    } else {
      hasData.value = false
      chartData.value = { time_label: [], series: {} }
      await nextTick()
      await waitForNextFrame()
      renderChart()
    }
  } finally {
    isCategorySwitching.value = false
  }
}

function onCursorChange() {
  const instance = ensureChart()
  if (!instance) return

  const labels = filteredLabels.value
  if (!labels.length) return

  const idx = Math.max(0, labels.length - 1)
  instance.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: idx })
}

function onStartRangeInput(event) {
  const value = Number(event?.target?.value)
  if (!Number.isFinite(value)) return

  startIndex.value = Math.min(value, endIndex.value)
}

function onEndRangeInput(event) {
  const value = Number(event?.target?.value)
  if (!Number.isFinite(value)) return

  endIndex.value = Math.max(value, startIndex.value)
}

function onGaugeProgressInput(event) {
  const value = Number(event?.target?.value)
  if (!Number.isFinite(value)) return

  stopGaugePlayback()
  const clamped = Math.min(Math.max(value, gaugePlayMin.value), gaugePlayMax.value)
  gaugeCursorIndex.value = clamped
}

function selectAllFields() {
  const keys = activeFieldOptions.value.map((item) => item.key)
  activeFieldKeys.value = keys
}

function resetFieldSelection() {
  const first = activeFieldOptions.value[0]?.key
  activeFieldKeys.value = first ? [first] : []
}

function handleDocumentClick(event) {
  const fieldRoot = fieldDropdownRef.value
  if (isFieldDropdownOpen.value && fieldRoot && !fieldRoot.contains(event.target)) {
    closeFieldDropdown()
  }
}

async function loadDefaultQarId() {
  try {
    const res = await apiDataQarIds({ limit: 1 })
    const items = Array.isArray(res?.data?.items) ? res.data.items : []
    const firstQarId = String(items[0] || '').trim()

    if (!firstQarId) {
      errorMessage.value = '未找到可用的 QARID。'
      hasData.value = false
      chartData.value = { time_label: [], series: {} }
      renderChart()
      return
    }

    qarIdInput.value = firstQarId
    await router.replace({
      query: {
        ...route.query,
        qar_id: firstQarId,
      },
    })
    await loadFlightData()
  } catch (error) {
    errorMessage.value = error?.message || '默认 QARID 加载失败'
    hasData.value = false
    chartData.value = { time_label: [], series: {} }
    renderChart()
  }
}

function onResize() {
  chartInstance?.resize()
  gaugePanelInstances.forEach((instance) => instance?.resize())
  positionHeightPanelInstances.forEach((instance) => instance?.resize())
  aircraftLoadPanelInstances.forEach((instance) => instance?.resize())
}

function rerenderForThemeChange() {
  if (!hasData.value) return
  nextTick(() => {
    renderChart()
  })
}

watch(activeFieldKeys, async (keys) => {
  if (!keys.length && activeFieldOptions.value.length) {
    activeFieldKeys.value = [activeFieldOptions.value[0].key]
    return
  }

  if (isCategorySwitching.value) return

  if (isPositionHeightMode.value) {
    return
  }

  if (isAircraftLoadMode.value) {
    return
  }

  if (!isGaugeMode.value) {
    if (qarIdInput.value.trim()) {
      await loadFlightData()
      return
    }
    await nextTick()
    renderChart()
    return
  }

  await nextTick()
  renderChart()
  onCursorChange()
})

watch(activeFieldOptions, () => {
  normalizeFieldSelection()
})

watch(activeCategoryKey, (key) => {
  if (!gaugeCategoryKeys.has(key)) {
    stopGaugePlayback()
  }
})

watch(playbackRate, () => {
  if (!isGaugePlaying.value) return
  startGaugePlaybackTimer()
})

watch([startIndex, endIndex], async () => {
  if (!timeLabels.value.length) return

  const minIdx = isGaugeMode.value ? gaugePlayMin.value : rangeStart.value
  const maxIdx = isGaugeMode.value ? gaugePlayMax.value : rangeEnd.value
  if (gaugeCursorIndex.value < minIdx || gaugeCursorIndex.value > maxIdx) {
    gaugeCursorIndex.value = minIdx
  }

  await nextTick()
  renderChart()
  onCursorChange()
})

watch(gaugeCursorIndex, async () => {
  if ((!isGaugeMode.value && !isPfdMode.value) || !timeLabels.value.length) return
  await nextTick()
  renderChart()
})

onMounted(async () => {
  if (qarIdInput.value.trim()) {
    await loadFlightData()
  } else {
    await loadDefaultQarId()
  }

  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('resize', onResize)

  themeClassObserver = new MutationObserver((mutationList) => {
    const changed = mutationList.some((m) => m.type === 'attributes' && m.attributeName === 'class')
    if (changed) {
      rerenderForThemeChange()
    }
  })
  themeClassObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

onBeforeUnmount(() => {
  stopGaugePlayback()
  disposeGaugePanels([])
  disposePositionHeightPanels([])
  disposeAircraftLoadPanels([])
  document.removeEventListener('click', handleDocumentClick)
  window.removeEventListener('resize', onResize)
  themeClassObserver?.disconnect()
  themeClassObserver = null
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.flight-preview-grid {
  gap: 16px;
}

.flight-preview-error {
  padding: 12px 16px;
  color: var(--danger);
  font-size: 13px;
  font-weight: 600;
}

.flight-preview-layout-card {
  padding: 0;
  overflow: hidden;
  min-height: 640px;
  height: 100%;
}

.flight-preview-layout-shell {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  min-height: 100%;
  height: 100%;
}

.flight-preview-category-aside {
  border-right: 1px solid var(--border);
  background: linear-gradient(180deg, color-mix(in srgb, var(--panel) 94%, transparent) 0%, color-mix(in srgb, var(--surface-soft) 84%, transparent) 100%);
  padding: 12px 10px;
  display: grid;
  gap: 6px;
  align-content: start;
  overflow: auto;
}

.flight-preview-category-btn {
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  white-space: normal;
  line-height: 1.35;
  text-align: left;
  justify-content: flex-start;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}

.flight-preview-category-btn:hover {
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border-color: color-mix(in srgb, var(--border) 70%, transparent);
  color: var(--text);
}

.flight-preview-category-btn.btn-primary {
  background: color-mix(in srgb, var(--surface-soft) 94%, transparent);
  color: var(--brand);
  border-color: color-mix(in srgb, var(--brand) 26%, var(--border));
}

.flight-preview-category-btn.btn-ghost {
  background: transparent;
  color: var(--muted);
  border-color: transparent;
}

.flight-preview-main {
  padding: 16px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 14px;
}

.flight-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.flight-preview-head-title {
  font-size: 14px;
  font-weight: 700;
}

.flight-preview-head-desc {
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.flight-preview-head-tools {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
  margin-left: auto;
}

.flight-preview-field-select-wrap {
  min-width: 280px;
  max-width: 520px;
  width: 100%;
  display: grid;
  gap: 8px;
}

.flight-preview-field-dropdown-root {
  position: relative;
}

.flight-preview-field-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: var(--panel-elevated);
  cursor: pointer;
}

.flight-preview-field-trigger-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.flight-preview-field-trigger-action {
  flex: none;
  font-size: 12px;
  color: var(--muted);
}

.flight-preview-field-dropdown-panel {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 20;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 10px;
  display: grid;
  gap: 10px;
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.flight-preview-field-dropdown-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.flight-preview-field-dropdown-btn {
  padding: 6px 10px;
  min-height: 32px;
}

.flight-preview-field-dropdown-list {
  max-height: 240px;
  overflow: auto;
  display: grid;
  gap: 6px;
}

.flight-preview-field-dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  cursor: pointer;
}

.flight-preview-field-dropdown-item-label {
  font-size: 13px;
  line-height: 1.4;
}

.flight-preview-field-dropdown-tip {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.flight-preview-chart-stage {
  position: relative;
  border: 0;
  min-height: 0;
  height: 100%;
}

.flight-preview-chart-stage-single {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0;
}

.flight-preview-chart-canvas {
  width: 100%;
  height: 100%;
}

.pfd-wrap {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.speed-pfd-combo {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 12px;
  align-items: stretch;
}

.pfd-wrap-portrait {
  min-height: 0;
  container-type: size;
  --pfd-scale: clamp(0.9, calc(1.1vw + 0.55), 1.45);
  --pfd-fs: calc(10px * var(--pfd-scale));
  background: linear-gradient(180deg, rgba(15, 22, 48, 0.96) 0%, rgba(10, 16, 38, 0.96) 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 12px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03), 0 10px 24px rgba(0, 0, 0, 0.22);
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.pfd-screen {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 6fr) minmax(0, 2fr);
  gap: 10px;
  align-items: stretch;
}

.pfd-screen-compact {
  --pfd-tape-center: 53%;
  font-size: var(--pfd-fs);
  grid-template-columns: minmax(0, 2fr) minmax(0, 6fr) minmax(0, 2fr);
  gap: 0.68em;
}

@supports (width: 1cqi) {
  .pfd-wrap-portrait {
    --pfd-scale: clamp(0.86, calc((100cqi + 72cqb) / 760), 1.72);
    --pfd-fs: calc(10px * var(--pfd-scale));
  }

  .pfd-screen-compact {
    gap: calc(0.56em + 0.2cqi);
  }
}

.speed-pfd-gauges {
  min-height: 0;
}

.speed-pfd-gauge-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
}

@media (min-width: 1600px) {
  .speed-pfd-gauge-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.pfd-tape {
  border: 0;
  border-radius: 1em;
  background: linear-gradient(180deg, rgba(90, 69, 121, 0.95) 0%, rgba(69, 56, 103, 0.95) 100%);
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 0.5em;
  padding: 0.5em;
  min-height: 0;
  box-shadow: none;
  clip-path: polygon(4% 0, 96% 0, 100% 100%, 0 100%);
  align-self: center;
  height: 92%;
}

.pfd-tape-title {
  text-align: center;
  font-size: 0.9em;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 0.06em;
}

.pfd-tape-title-alert {
  color: #ff2a2a;
  font-size: 1.02em;
  letter-spacing: 0.08em;
}

.pfd-tape-scale {
  position: relative;
  min-height: 0;
  overflow: hidden;
  border-radius: 0.5em;
  background: rgba(35, 28, 54, 0.35);
}

.pfd-tape-current-marker {
  position: absolute;
  left: 50%;
  top: var(--pfd-tape-center, 50%);
  transform: translate(-50%, -50%);
  width: 100%;
  height: 0.34em;
  z-index: 2;
  pointer-events: none;
}

.pfd-tape-current-marker-segment {
  position: absolute;
  top: 50%;
  width: 1.15em;
  height: 0.22em;
  border-radius: 999px;
  background: #ffe400;
  box-shadow: 0 0 0 1px rgba(255, 228, 0, 0.25);
  transform: translateY(-50%);
}

.pfd-tape-current-marker-left {
  left: 0.1em;
}

.pfd-tape-current-marker-right {
  right: 0.1em;
}

.pfd-tape-tick {
  position: absolute;
  left: 0.6em;
  right: 0.6em;
  height: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pfd-tape-tick-line {
  width: 1.45em;
  border-top: 2px solid rgba(255, 255, 255, 0.96);
}

.pfd-tape-tick-label {
  font-size: 0.88em;
  color: #ffffff;
  font-weight: 700;
}

.pfd-center-panel {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0.4em 0.15em 0.4em;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  gap: 0.35em;
  min-height: 0;
}

.pfd-roll-scale {
  position: relative;
  height: 2.2em;
  overflow: hidden;
}

.pfd-roll-mark {
  position: absolute;
  left: 50%;
  bottom: -0.22em;
  width: 0.14em;
  height: 0.85em;
  transform-origin: 50% -8.2em;
  background: rgba(255, 255, 255, 0.9);
}

.pfd-roll-pointer {
  position: absolute;
  left: 50%;
  bottom: 0.14em;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 0.6em solid transparent;
  border-right: 0.6em solid transparent;
  border-top: 0.9em solid #ffd93a;
}

.pfd-attitude-window {
  position: relative;
  overflow: hidden;
  border-radius: 999px;
  border: 0;
  background: #342fb0;
  min-height: 0;
  aspect-ratio: 1.42 / 1.8;
  width: 100%;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  justify-self: stretch;
  align-self: center;
  margin-block: auto;
}

.pfd-fd-label {
  position: absolute;
  left: 1.1em;
  top: 1.2em;
  z-index: 4;
  color: #ff2a2a;
  font-size: 1.15em;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.pfd-horizon {
  position: absolute;
  width: 220%;
  height: 220%;
  left: 50%;
  top: 50%;
  transform-origin: 50% 50%;
}

.pfd-sky,
.pfd-ground {
  position: absolute;
  left: 0;
  right: 0;
}

.pfd-sky {
  top: 0;
  bottom: 50%;
  background: linear-gradient(180deg, #4288e2 0%, #2e73ca 60%, #1e5ab2 100%);
}

.pfd-ground {
  top: 50%;
  bottom: 0;
  background: linear-gradient(180deg, #8e4f2e 0%, #7c4426 100%);
}

.pfd-horizon-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-top: 3px solid rgba(255, 255, 255, 0.95);
}

.pfd-pitch-line {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 8.7em;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.56em;
  color: #ffffff;
  font-size: 0.82em;
  font-weight: 700;
}

.pfd-pitch-line.major .pfd-pitch-center {
  border-top-width: 3px;
}

.pfd-pitch-center {
  border-top: 2px solid rgba(255, 255, 255, 0.95);
}

.pfd-pitch-label-left {
  text-align: right;
}

.pfd-pitch-label-right {
  text-align: left;
}

.pfd-aircraft-symbol {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 8.2em;
  height: 1.4em;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.18em;
  pointer-events: none;
}

.pfd-wing {
  width: 2.8em;
  border-top: 4px solid #ffe400;
}

.pfd-fuselage {
  width: 1em;
  border-top: 4px solid #ffe400;
}

.pfd-slip-scale {
  position: absolute;
  left: 50%;
  bottom: 0.7em;
  transform: translateX(-50%);
  width: 6.8em;
  height: 0.9em;
}

.pfd-slip-center {
  position: absolute;
  left: 0;
  right: 0;
  top: 0.34em;
  border-top: 2px solid rgba(255, 255, 255, 0.88);
}

.pfd-slip-ball {
  position: absolute;
  left: 50%;
  top: 0;
  margin-left: -0.56em;
  width: 1.12em;
  height: 0.7em;
  border-radius: 0.56em;
  background: #ffc92c;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
}

.pfd-heading-strip {
  position: relative;
  height: 2.9em;
  overflow: hidden;
  border-radius: 0.35em;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: #343051;
}

.pfd-heading-tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
  width: 2px;
  display: grid;
  justify-items: center;
  gap: 2px;
}

.pfd-heading-tick-line {
  width: 2px;
  height: 0.8em;
  background: rgba(255, 255, 255, 0.9);
}

.pfd-heading-tick.major .pfd-heading-tick-line {
  height: 1.05em;
}

.pfd-heading-tick-label {
  color: rgba(255, 255, 255, 0.94);
  font-size: 0.72em;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 0.15em;
}

.pfd-heading-bug {
  position: absolute;
  left: 50%;
  top: 0;
  transform: translateX(-50%);
  min-width: 3.7em;
  text-align: center;
  padding: 0.25em 0.5em;
  border-radius: 0 0 0.5em 0.5em;
  background: #fbdb38;
  color: #1c1a08;
  font-size: 0.78em;
  font-weight: 800;
}

.pfd-info-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5em;
  font-size: 0.74em;
  color: rgba(255, 255, 255, 0.94);
  font-weight: 600;
}

.pfd-info-item {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 0.5em;
  padding: 0.4em 0.5em;
  display: grid;
  grid-template-rows: auto auto;
  justify-items: center;
  gap: 0.1em;
  background: rgba(25, 25, 35, 0.9);
}

.pfd-info-item-label {
  line-height: 1.1;
}

.pfd-info-item-value {
  line-height: 1.2;
  font-weight: 700;
}

.flight-preview-empty-overlay,
.flight-preview-loading-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.flight-preview-empty-overlay {
  text-align: center;
  padding: 24px;
  color: var(--muted);
  background: var(--overlay-bg);
}

.flight-preview-empty-title {
  font-weight: 700;
  color: var(--text);
}

.flight-preview-empty-desc {
  margin-top: 6px;
  font-size: 12px;
}

.flight-preview-loading-overlay {
  background: var(--overlay-loading-bg);
  color: var(--text);
  font-weight: 700;
}

.flight-preview-footer-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.gauge-grid-wrap {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: auto;
}

.gauge-grid {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: 12px;
  align-content: stretch;
}

.gauge-card {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 85%, transparent) 0%, color-mix(in srgb, var(--surface-hover) 85%, transparent) 100%);
  padding: 10px;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 6px;
}

.gauge-card-title {
  font-size: 12px;
  color: var(--chart-text);
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gauge-card-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.gauge-card-index {
  font-size: 11px;
  color: var(--chart-muted);
  text-align: right;
}

.position-height-grid-wrap {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
}

.position-height-grid {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 12px;
}

.position-height-left-stack {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 12px;
}

.position-height-card {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 85%, transparent) 0%, color-mix(in srgb, var(--surface-hover) 85%, transparent) 100%);
  padding: 10px;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 6px;
  min-height: 0;
}

.position-height-card-right {
  min-height: 0;
}

.position-height-card-title {
  font-size: 12px;
  color: var(--chart-text);
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.position-height-card-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.position-height-card-bottom-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.aircraft-load-grid-wrap {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  box-sizing: border-box;
}

.aircraft-load-grid {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}

.aircraft-load-card {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 85%, transparent) 0%, color-mix(in srgb, var(--surface-hover) 85%, transparent) 100%);
  padding: 10px;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 6px;
  min-height: 0;
  height: 100%;
}

.aircraft-load-card-title {
  font-size: 12px;
  color: var(--chart-text);
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.aircraft-load-card-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.aircraft-load-card-bottom-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.gauge-controls-row {
  width: 100%;
  display: flex;
  justify-content: flex-end;
}

.gauge-controls {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
}

.media-btn-speed {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  padding: 0;
  font-size: 12px;
  font-weight: 700;
}

.media-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 0;
}

.media-btn-primary {
  background: var(--brand);
  color: var(--on-primary);
  box-shadow: 0 6px 14px color-mix(in srgb, var(--brand) 30%, transparent);
}

.media-btn-ghost {
  background: var(--surface-soft);
  color: var(--text);
  border-color: var(--border);
}

.media-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.gauge-progress-box {
  flex: 1 1 auto;
  min-width: 260px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.gauge-progress-box.disabled {
  opacity: 0.5;
}

.gauge-progress-endpoint {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  white-space: nowrap;
  min-width: 12ch;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace;
}

.gauge-progress-input {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  margin: 0;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--brand) 20%, var(--border));
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--brand) 84%, #ffffff) 0%,
    color-mix(in srgb, var(--brand) 84%, #ffffff) var(--gauge-progress-percent, 0%),
    color-mix(in srgb, var(--surface-soft) 90%, #ffffff) var(--gauge-progress-percent, 0%),
    color-mix(in srgb, var(--surface-soft) 90%, #ffffff) 100%
  );
  cursor: pointer;
}

.gauge-progress-input::-webkit-slider-runnable-track {
  -webkit-appearance: none;
  appearance: none;
  height: 8px;
  border-radius: 999px;
  background: transparent;
}

.gauge-progress-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -3px;
  border-radius: 50%;
  border: 2px solid var(--brand);
  background: #ffffff;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 22%, transparent);
}

.gauge-progress-input::-moz-range-track {
  height: 8px;
  border-radius: 999px;
  background: transparent;
}

.gauge-progress-input::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--brand);
  background: #ffffff;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 22%, transparent);
}

.gauge-progress-input:disabled {
  cursor: not-allowed;
}

.range-filter {
  flex: 1 1 360px;
  min-width: 320px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
}

.range-filter.disabled {
  opacity: 0.6;
}

.range-filter-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}

.range-filter-head strong {
  color: var(--text);
  font-weight: 700;
}

.range-track-wrap {
  position: relative;
  height: 24px;
}

.range-track,
.range-track-active {
  position: absolute;
  top: 10px;
  height: 4px;
  border-radius: 999px;
}

.range-track {
  left: 0;
  right: 0;
  background: var(--track-bg);
}

.range-track-active {
  background: var(--brand);
}

.range-input {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 24px;
  margin: 0;
  background: transparent;
  pointer-events: none;
  -webkit-appearance: none;
  appearance: none;
}

.range-input::-webkit-slider-runnable-track {
  height: 4px;
  background: transparent;
}

.range-input::-webkit-slider-thumb {
  pointer-events: auto;
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--thumb-bg);
  border: 2px solid var(--brand);
  margin-top: -6px;
  cursor: pointer;
}

.range-input::-moz-range-track {
  height: 4px;
  background: transparent;
}

.range-input::-moz-range-thumb {
  pointer-events: auto;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--thumb-bg);
  border: 2px solid var(--brand);
  cursor: pointer;
}

@media (max-width: 1100px) {
  .flight-preview-layout-shell {
    grid-template-columns: 1fr;
  }

  .flight-preview-category-aside {
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .pfd-screen {
    grid-template-columns: minmax(0, 2fr) minmax(0, 6fr) minmax(0, 2fr);
  }

  .speed-pfd-combo {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(380px, 1fr) minmax(0, 1fr);
  }

  .pfd-screen-compact {
    grid-template-columns: minmax(0, 2fr) minmax(0, 6fr) minmax(0, 2fr);
  }

  .speed-pfd-gauge-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pfd-info-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .position-height-grid {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(0, auto) minmax(360px, 1fr);
  }

  .position-height-left-stack {
    grid-template-rows: minmax(260px, 1fr) minmax(260px, 1fr);
  }
}
</style>