<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="selectedQarId" @search="loadReplay" />
      </div>
    </template>

    <div class="replay-page">
      <div class="grid replay-grid">
        <div class="card card-pad replay-main-card">
          <div class="replay-head-row">
            <h3 class="replay-title">三维飞行回放</h3>
            <div class="control-row replay-view-actions">
              <button
                class="btn"
                :class="cameraMode === 'cockpit' ? 'btn-primary' : 'btn-ghost'"
                @click="switchToCockpitView"
                :disabled="!replayPoints.length"
              >
                驾驶舱视角
              </button>
              <button
                class="btn"
                :class="cameraMode === 'ground' ? 'btn-primary' : 'btn-ghost'"
                @click="switchToGroundView"
                :disabled="!replayPoints.length"
              >
                俯视视角
              </button>
              <button
                class="btn"
                :class="cameraMode === 'side' ? 'btn-primary' : 'btn-ghost'"
                @click="switchToSideView"
                :disabled="!replayPoints.length"
              >
                侧面视角
              </button>
            </div>
          </div>
          <div ref="trajectoryRef" class="replay-canvas"></div>

          <div class="replay-control-panel">
            <div class="gauge-controls-row">
              <div class="gauge-controls">
                <button class="media-btn media-btn-primary" :disabled="!replayPoints.length" @click="togglePlay" title="播放/暂停">
                  <span v-if="!playing">▶</span>
                  <span v-else>❚❚</span>
                </button>
                <button
                  class="media-btn media-btn-ghost media-btn-speed"
                  :disabled="!replayPoints.length"
                  @click="cyclePlaybackSpeed"
                  title="点击切换倍速"
                >
                  {{ playbackSpeedLabel }}
                </button>
                <div class="gauge-progress-box" :class="{ disabled: !replayPoints.length || replayPlayMax <= replayPlayMin }">
                  <input
                    class="gauge-progress-input"
                    type="range"
                    :min="replayPlayMin"
                    :max="replayPlayMax"
                    step="1"
                    :disabled="!replayPoints.length || replayPlayMax <= replayPlayMin"
                    :value="currentIndex"
                    :style="replayProgressStyle"
                    @input="onReplayProgressInput"
                  />
                  <div class="gauge-progress-endpoint">{{ replayProgressLabel }}</div>
                </div>
              </div>
            </div>

          </div>
        </div>

        <div class="card card-pad replay-metrics-card">
          <div class="metrics-head">
            <h4 class="metrics-title">状态指标</h4>
            <span class="metrics-badge">实时</span>
          </div>
          <div class="replay-metrics-list">
            <div class="metrics-hero">
              <div class="metrics-hero-top">
                <div class="metrics-hero-title">回放进度</div>
                <div class="metrics-hero-value">{{ replayCompletion.toFixed(1) }}%</div>
              </div>
              <div class="metrics-progress-track">
                <div ref="metricsProgressActiveRef" class="metrics-progress-active"></div>
              </div>
              <div class="metrics-hero-sub">{{ currentIndex + 1 }} / {{ replayPoints.length }} · {{ currentPoint.t.toFixed(2) }} / {{ durationText }}</div>
            </div>

            <div class="metrics-grid">
              <div class="metric-tile">
                <div class="metric-label">当前时刻</div>
                <div class="metric-value">{{ currentPoint.t.toFixed(2) }} s</div>
                <div class="metric-sub">总时长 {{ durationText }}</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">播放倍率</div>
                <div class="metric-value">{{ playbackSpeed.toFixed(1) }}x</div>
                <div class="metric-sub">{{ playing ? '播放中' : '已暂停' }}</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">当前高度</div>
                <div class="metric-value">{{ currentPoint.asl.toFixed(2) }} m</div>
                <div class="metric-sub">爬升率 {{ climbRate.toFixed(2) }} m/s</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">当前速度</div>
                <div class="metric-value">{{ currentPoint.tas.toFixed(2) }} kt</div>
                <div class="metric-sub">{{ speedTier }}</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">俯仰角</div>
                <div class="metric-value">{{ currentPoint.pitch.toFixed(2) }} °</div>
                <div class="metric-sub">机头上下姿态</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">滚转角</div>
                <div class="metric-value">{{ currentPoint.roll.toFixed(2) }} °</div>
                <div class="metric-sub">机翼横向姿态</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">机头朝向</div>
                <div class="metric-value">{{ currentPoint.heading.toFixed(2) }} °</div>
                <div class="metric-sub">{{ headingDirection }}</div>
              </div>

              <div class="metric-tile">
                <div class="metric-label">姿态稳定度</div>
                <div class="metric-value">{{ attitudeScore.toFixed(0) }}</div>
                <div class="metric-sub">{{ attitudeLevel }} · P{{ currentPoint.pitch.toFixed(1) }} / R{{ currentPoint.roll.toFixed(1) }}</div>
              </div>

              <div class="metric-tile span-2">
                <div class="metric-label">当前位置</div>
                <div class="metric-value">{{ currentPoint.lon.toFixed(6) }}, {{ currentPoint.lat.toFixed(6) }}</div>
                <div class="metric-sub">地理坐标 · WGS84</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as Cesium from 'cesium'

import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { apiFlightReplay } from '../api/flightApi'

const trajectoryRef = ref(null)
const metricsProgressActiveRef = ref(null)
let viewer = null
let aircraftEntity = null
let replayStartTime = null
let replayStopTime = null
let shouldSyncFromClock = true
let isSyncingFromClockTick = false
let smoothedSideCameraDestination = null
let smoothedSideCameraDirection = null
let smoothedSideCameraUp = null

const selectedQarId = ref('')
const replayPoints = ref([])
const totalPoints = ref(0)
const samplePoints = ref(0)
const duration = ref(0)

const currentIndex = ref(0)
const playing = ref(false)
const playbackSpeed = ref(5)
const cameraMode = ref('cockpit')
const MODEL_FORWARD_AXIS_OFFSET_DEG = -90
const playbackSpeedOptions = [1, 2, 5, 10]

const currentPoint = computed(() => {
  if (!replayPoints.value.length) {
    return { t: 0, asl: 0, tas: 0, lon: 0, lat: 0, heading: 0, pitch: 0, roll: 0 }
  }
  return replayPoints.value[Math.min(currentIndex.value, replayPoints.value.length - 1)]
})

const durationText = computed(() => `${duration.value.toFixed(2)} s`)
const replayPlayMin = computed(() => 0)
const replayPlayMax = computed(() => Math.max(0, replayPoints.value.length - 1))
const playbackSpeedLabel = computed(() => `${playbackSpeed.value}x`)

function formatPlaybackTime(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '00.00'
  return numeric.toFixed(2).padStart(5, '0')
}

const replayCurrentTimeLabel = computed(() => formatPlaybackTime(currentPoint.value.t))
const replayDurationLabel = computed(() => formatPlaybackTime(duration.value))
const replayProgressLabel = computed(() => `${replayCurrentTimeLabel.value}/${replayDurationLabel.value}`)
const replayProgressStyle = computed(() => {
  if (!replayPoints.value.length || replayPlayMax.value <= replayPlayMin.value) {
    return { '--gauge-progress-percent': '0%' }
  }

  const clamped = Math.max(replayPlayMin.value, Math.min(replayPlayMax.value, currentIndex.value))
  const progress = ((clamped - replayPlayMin.value) / (replayPlayMax.value - replayPlayMin.value)) * 100
  return { '--gauge-progress-percent': `${progress.toFixed(2)}%` }
})

const replayCompletion = computed(() => {
  if (!duration.value || !Number.isFinite(currentPoint.value.t)) return 0
  return Math.max(0, Math.min(100, (currentPoint.value.t / duration.value) * 100))
})
const headingDirection = computed(() => {
  const dirs = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
  const heading = ((Number(currentPoint.value.heading) % 360) + 360) % 360
  const idx = Math.round(heading / 45) % 8
  return dirs[idx]
})
const speedTier = computed(() => {
  const speed = Number(currentPoint.value.tas || 0)
  if (speed < 140) return '低速段'
  if (speed < 260) return '巡航段'
  return '高速段'
})
const climbRate = computed(() => {
  if (!replayPoints.value.length || currentIndex.value <= 0) return 0
  const curr = replayPoints.value[currentIndex.value]
  const prev = replayPoints.value[Math.max(0, currentIndex.value - 1)]
  const dt = Number(curr.t) - Number(prev.t)
  if (!Number.isFinite(dt) || dt <= 0) return 0
  return (Number(curr.asl || 0) - Number(prev.asl || 0)) / dt
})
const attitudeScore = computed(() => {
  const pitch = Math.abs(Number(currentPoint.value.pitch || 0))
  const roll = Math.abs(Number(currentPoint.value.roll || 0))
  const score = 100 - pitch * 1.8 - roll * 1.1
  return Math.max(0, Math.min(100, score))
})
const attitudeLevel = computed(() => {
  if (attitudeScore.value >= 80) return '稳定'
  if (attitudeScore.value >= 60) return '轻微波动'
  return '剧烈波动'
})

function initializeViewer() {
  if (!trajectoryRef.value || viewer) return

  viewer = new Cesium.Viewer(trajectoryRef.value, {
    animation: false,
    timeline: false,
    imageryProvider: new Cesium.OpenStreetMapImageryProvider({
      url: 'https://tile.openstreetmap.org/',
    }),
    baseLayerPicker: true,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    selectionIndicator: false,
    infoBox: false,
    shouldAnimate: false,
  })

  viewer.scene.globe.depthTestAgainstTerrain = false
  viewer.resize()
  viewer.scene.requestRender()
  viewer.clock.onTick.addEventListener(() => {
    if (!shouldSyncFromClock || !replayStartTime || !replayPoints.value.length) return

    const elapsed = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, replayStartTime)
    const idx = Math.max(0, Math.min(replayPoints.value.length - 1, Math.floor(elapsed)))
    isSyncingFromClockTick = true
    currentIndex.value = idx
    isSyncingFromClockTick = false

    if (cameraMode.value === 'cockpit') {
      updateCockpitCamera()
    } else if (cameraMode.value === 'side') {
      updateSideCamera()
    }
  })
}

function getActiveReplayPoint() {
  if (!replayPoints.value.length) return null
  return replayPoints.value[Math.min(currentIndex.value, replayPoints.value.length - 1)]
}

function updateCockpitCamera() {
  if (!viewer) return
  const point = getActiveReplayPoint()
  if (!point) return

  const headingRad = Cesium.Math.toRadians(point.heading)
  const pitchRad = Cesium.Math.toRadians(point.pitch)
  const rollRad = Cesium.Math.toRadians(point.roll)
  const aircraftPos = Cesium.Cartesian3.fromDegrees(point.lon, point.lat, point.asl)
  const forwardEnu = new Cesium.Cartesian3(
    Math.sin(headingRad) * Math.cos(pitchRad),
    Math.cos(headingRad) * Math.cos(pitchRad),
    Math.sin(pitchRad)
  )
  Cesium.Cartesian3.normalize(forwardEnu, forwardEnu)

  const upEnu = new Cesium.Cartesian3(0, 0, 1)
  const rightEnu = Cesium.Cartesian3.cross(forwardEnu, upEnu, new Cesium.Cartesian3())
  Cesium.Cartesian3.normalize(rightEnu, rightEnu)

  // Place camera near cockpit (not ahead of nose) so nose contour stays visible.
  const noseForwardOffset = Cesium.Cartesian3.multiplyByScalar(forwardEnu, 2.2, new Cesium.Cartesian3())
  const upOffset = Cesium.Cartesian3.multiplyByScalar(upEnu, 2.0, new Cesium.Cartesian3())
  const sideOffset = Cesium.Cartesian3.multiplyByScalar(rightEnu, 0.0, new Cesium.Cartesian3())
  const enuOffset = Cesium.Cartesian3.add(noseForwardOffset, upOffset, new Cesium.Cartesian3())
  Cesium.Cartesian3.add(enuOffset, sideOffset, enuOffset)

  const enuTransform = Cesium.Transforms.eastNorthUpToFixedFrame(aircraftPos)
  const cameraWorld = Cesium.Matrix4.multiplyByPointAsVector(enuTransform, enuOffset, new Cesium.Cartesian3())
  Cesium.Cartesian3.add(aircraftPos, cameraWorld, cameraWorld)

  viewer.camera.setView({
    destination: cameraWorld,
    orientation: {
      heading: headingRad,
      pitch: pitchRad,
      roll: rollRad,
    },
  })
}

function updateGroundCamera() {
  if (!viewer) return
  const point = getActiveReplayPoint()
  if (!point) return

  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(point.lon, point.lat, point.asl + 12000),
    orientation: {
      heading: 0,
      pitch: Cesium.Math.toRadians(-90),
      roll: 0,
    },
  })
}

function updateSideCamera() {
  if (!viewer) return
  const point = getActiveReplayPoint()
  if (!point) return

  const headingRad = Cesium.Math.toRadians(point.heading)
  const aircraftPos = Cesium.Cartesian3.fromDegrees(point.lon, point.lat, point.asl)
  const forwardEnu = new Cesium.Cartesian3(Math.sin(headingRad), Math.cos(headingRad), 0)
  Cesium.Cartesian3.normalize(forwardEnu, forwardEnu)

  const upEnu = new Cesium.Cartesian3(0, 0, 1)
  const rightEnu = Cesium.Cartesian3.cross(forwardEnu, upEnu, new Cesium.Cartesian3())
  Cesium.Cartesian3.normalize(rightEnu, rightEnu)

  const sideOffset = Cesium.Cartesian3.multiplyByScalar(rightEnu, 2600.0, new Cesium.Cartesian3())
  const enuOffset = Cesium.Cartesian3.clone(sideOffset)
  const lookEnu = Cesium.Cartesian3.negate(enuOffset, new Cesium.Cartesian3())

  const enuTransform = Cesium.Transforms.eastNorthUpToFixedFrame(aircraftPos)
  const cameraWorld = Cesium.Matrix4.multiplyByPointAsVector(enuTransform, enuOffset, new Cesium.Cartesian3())
  Cesium.Cartesian3.add(aircraftPos, cameraWorld, cameraWorld)

  const lookDirection = Cesium.Cartesian3.normalize(
    Cesium.Matrix4.multiplyByPointAsVector(enuTransform, lookEnu, new Cesium.Cartesian3()),
    new Cesium.Cartesian3()
  )
  const lookUp = Cesium.Cartesian3.normalize(
    Cesium.Matrix4.multiplyByPointAsVector(enuTransform, upEnu, new Cesium.Cartesian3()),
    new Cesium.Cartesian3()
  )

  if (!smoothedSideCameraDestination || !smoothedSideCameraDirection || !smoothedSideCameraUp) {
    smoothedSideCameraDestination = Cesium.Cartesian3.clone(cameraWorld)
    smoothedSideCameraDirection = Cesium.Cartesian3.clone(lookDirection)
    smoothedSideCameraUp = Cesium.Cartesian3.clone(lookUp)
  } else {
    Cesium.Cartesian3.lerp(smoothedSideCameraDestination, cameraWorld, 0.01, smoothedSideCameraDestination)

    const blendedDirection = Cesium.Cartesian3.lerp(smoothedSideCameraDirection, lookDirection, 0.01, new Cesium.Cartesian3())
    const blendedUp = Cesium.Cartesian3.lerp(smoothedSideCameraUp, lookUp, 0.01, new Cesium.Cartesian3())
    Cesium.Cartesian3.normalize(blendedDirection, smoothedSideCameraDirection)
    Cesium.Cartesian3.normalize(blendedUp, smoothedSideCameraUp)
  }

  viewer.camera.setView({
    destination: smoothedSideCameraDestination,
    orientation: {
      direction: smoothedSideCameraDirection,
      up: smoothedSideCameraUp,
      roll: 0,
    },
  })
}

function switchToCockpitView() {
  cameraMode.value = 'cockpit'
  if (viewer) {
    viewer.trackedEntity = undefined
    applyAircraftVisualMode()
    updateCockpitCamera()
  }
}

function switchToGroundView() {
  cameraMode.value = 'ground'
  if (viewer) {
    viewer.trackedEntity = undefined
    applyAircraftVisualMode()
    updateGroundCamera()
  }
}

function switchToSideView() {
  cameraMode.value = 'side'
  smoothedSideCameraDestination = null
  smoothedSideCameraDirection = null
  smoothedSideCameraUp = null
  if (viewer) {
    viewer.trackedEntity = undefined
    applyAircraftVisualMode()
    updateSideCamera()
  }
}

function applyAircraftVisualMode() {
  if (!aircraftEntity?.model) return

  if (cameraMode.value === 'cockpit') {
    aircraftEntity.model.show = false
  } else {
    aircraftEntity.model.show = true
    aircraftEntity.model.color = Cesium.Color.WHITE
  }
}

function normalizeReplayPoints(points) {
  if (!points.length) return []

  const normalized = []
  let fallbackHeading = 0
  const firstTime = Number(points[0].t || 0)
  for (let i = 0; i < points.length; i++) {
    const point = points[i]
    const next = points[i + 1]
    const prev = points[i - 1]

    let heading = Number(point.heading || 0)
    if (!heading && next) {
      heading = estimateHeading(point.lon, point.lat, next.lon, next.lat)
    } else if (!heading && prev) {
      heading = estimateHeading(prev.lon, prev.lat, point.lon, point.lat)
    }
    if (!heading) heading = fallbackHeading
    fallbackHeading = heading

    normalized.push({
      t: Math.max(0, Number(point.t || 0) - firstTime),
      lon: Number(point.lon || 0),
      lat: Number(point.lat || 0),
      asl: Number(point.asl || 0),
      tas: Number(point.tas || 0),
      heading,
      pitch: Number(point.pitch || 0),
      roll: Number(point.roll || 0),
    })
  }

  return normalized
}

function estimateHeading(lon1, lat1, lon2, lat2) {
  const dLon = Cesium.Math.toRadians(Number(lon2 || 0) - Number(lon1 || 0))
  const y = Math.sin(dLon) * Math.cos(Cesium.Math.toRadians(Number(lat2 || 0)))
  const x =
    Math.cos(Cesium.Math.toRadians(Number(lat1 || 0))) * Math.sin(Cesium.Math.toRadians(Number(lat2 || 0))) -
    Math.sin(Cesium.Math.toRadians(Number(lat1 || 0))) *
      Math.cos(Cesium.Math.toRadians(Number(lat2 || 0))) *
      Math.cos(dLon)

  const headingRad = Math.atan2(y, x)
  const headingDeg = (Cesium.Math.toDegrees(headingRad) + 360) % 360
  return Number.isFinite(headingDeg) ? headingDeg : 0
}

function buildCesiumPath() {
  if (!viewer || !replayPoints.value.length) return

  viewer.entities.removeAll()

  const start = Cesium.JulianDate.now()
  replayStartTime = start
  replayStopTime = Cesium.JulianDate.addSeconds(start, replayPoints.value.length - 1, new Cesium.JulianDate())

  const positionProperty = new Cesium.SampledPositionProperty()
  const orientationProperty = new Cesium.SampledProperty(Cesium.Quaternion)
  const allPositions = []

  replayPoints.value.forEach((point, idx) => {
    const sampleTime = Cesium.JulianDate.addSeconds(start, idx, new Cesium.JulianDate())
    const position = Cesium.Cartesian3.fromDegrees(point.lon, point.lat, point.asl)
    // Align glTF model's intrinsic forward axis with real track heading.
    const correctedHeading = point.heading + MODEL_FORWARD_AXIS_OFFSET_DEG
    const hpr = new Cesium.HeadingPitchRoll(
      Cesium.Math.toRadians(correctedHeading),
      Cesium.Math.toRadians(point.pitch),
      Cesium.Math.toRadians(point.roll)
    )
    const quaternion = Cesium.Transforms.headingPitchRollQuaternion(position, hpr)

    positionProperty.addSample(sampleTime, position)
    orientationProperty.addSample(sampleTime, quaternion)
    allPositions.push(position)
  })

  viewer.entities.add({
    name: '全流程航迹',
    polyline: {
      positions: allPositions,
      width: 2,
      material: Cesium.Color.fromCssColorString('#9db0c7').withAlpha(0.6),
    },
  })

  aircraftEntity = viewer.entities.add({
    name: '飞机模型',
    availability: new Cesium.TimeIntervalCollection([
      new Cesium.TimeInterval({ start: replayStartTime, stop: replayStopTime }),
    ]),
    position: positionProperty,
    orientation: orientationProperty,
    model: {
      uri: '/models/Cesium_Air.glb',
      minimumPixelSize: 64,
      maximumScale: 200,
      scale: 1.2,
      color: Cesium.Color.WHITE,
    },
    path: {
      resolution: 1,
      leadTime: 0,
      trailTime: 120,
      width: 4,
      material: Cesium.Color.fromCssColorString('#0f7bff').withAlpha(0.95),
    },
  })

  applyAircraftVisualMode()

  viewer.clock.startTime = replayStartTime.clone()
  viewer.clock.stopTime = replayStopTime.clone()
  viewer.clock.currentTime = replayStartTime.clone()
  viewer.clock.clockRange = Cesium.ClockRange.CLAMPED
  viewer.clock.multiplier = playbackSpeed.value
  viewer.clock.shouldAnimate = false

  if (cameraMode.value === 'cockpit') {
    updateCockpitCamera()
  } else if (cameraMode.value === 'ground') {
    updateGroundCamera()
  } else if (cameraMode.value === 'side') {
    updateSideCamera()
  }
}

function stopPlayback() {
  playing.value = false
  if (viewer) viewer.clock.shouldAnimate = false
}

function startPlayback() {
  if (!viewer || !replayPoints.value.length) return
  playing.value = true
  viewer.clock.multiplier = playbackSpeed.value
  viewer.clock.shouldAnimate = true
}

function togglePlay() {
  if (playing.value) {
    stopPlayback()
  } else {
    startPlayback()
  }
}

function cyclePlaybackSpeed() {
  if (!replayPoints.value.length) return
  const currentOptionIndex = playbackSpeedOptions.indexOf(playbackSpeed.value)
  const nextOptionIndex = currentOptionIndex >= 0 ? (currentOptionIndex + 1) % playbackSpeedOptions.length : 0
  playbackSpeed.value = playbackSpeedOptions[nextOptionIndex]
}

function onProgressDrag() {
  if (!viewer || !replayStartTime) return
  if (playing.value) stopPlayback()

  const sampleTime = Cesium.JulianDate.addSeconds(replayStartTime, currentIndex.value, new Cesium.JulianDate())
  shouldSyncFromClock = false
  viewer.clock.currentTime = sampleTime
  shouldSyncFromClock = true

  if (aircraftEntity) {
    viewer.scene.requestRender()
  }
}

function onReplayProgressInput(event) {
  const nextValue = Number(event?.target?.value)
  if (!Number.isFinite(nextValue)) return
  currentIndex.value = Math.max(replayPlayMin.value, Math.min(replayPlayMax.value, nextValue))
  onProgressDrag()
}

async function loadReplay() {
  stopPlayback()
  const res = await apiFlightReplay(selectedQarId.value, 30000)
  if (res.code !== 0) {
    throw new Error(res.message || '回放加载失败')
  }

  selectedQarId.value = res.data.qar_id
  replayPoints.value = normalizeReplayPoints(res.data.replay || [])
  totalPoints.value = res.data.total_points || replayPoints.value.length
  samplePoints.value = res.data.sample_points || replayPoints.value.length
  duration.value = Number(res.data.duration || 0)

  currentIndex.value = 0
  await nextTick()
  buildCesiumPath()
  viewer?.resize()
  viewer?.scene.requestRender()
}

function onResize() {
  if (viewer) {
    viewer.resize()
    viewer.scene.requestRender()
  }
}

watch(currentIndex, () => {
  if (!viewer || !replayStartTime) return

  // During playback, Cesium clock is the single source of truth.
  // Avoid snapping currentTime back to sampled points to reduce camera/model flicker.
  if (playing.value) {
    if (cameraMode.value === 'cockpit') {
      updateCockpitCamera()
    } else if (cameraMode.value === 'ground') {
      updateGroundCamera()
    } else if (cameraMode.value === 'side') {
      updateSideCamera()
    }
    return
  }

  if (isSyncingFromClockTick) return
  const sampleTime = Cesium.JulianDate.addSeconds(replayStartTime, currentIndex.value, new Cesium.JulianDate())
  shouldSyncFromClock = false
  viewer.clock.currentTime = sampleTime
  shouldSyncFromClock = true

  if (cameraMode.value === 'cockpit') {
    updateCockpitCamera()
  } else if (cameraMode.value === 'ground') {
    updateGroundCamera()
  } else if (cameraMode.value === 'side') {
    updateSideCamera()
  }
})

watch(playbackSpeed, () => {
  if (viewer) {
    viewer.clock.multiplier = playbackSpeed.value
  }
})

watch(
  replayCompletion,
  (value) => {
    if (!metricsProgressActiveRef.value) return
    const clamped = Math.max(0, Math.min(100, Number(value) || 0))
    metricsProgressActiveRef.value.style.width = `${clamped}%`
  },
  { immediate: true }
)

onMounted(async () => {
  initializeViewer()
  try {
    await loadReplay()
  } catch (_) {
    // Keep the page stable when backend has no data for the selected QAR ID.
  }
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  stopPlayback()
  window.removeEventListener('resize', onResize)
  if (viewer) {
    viewer.destroy()
    viewer = null
  }
})
</script>

<style scoped>
.replay-page {
  height: 100%;
  min-height: 0;
  padding: 4px 0 0;
  display: flex;
  flex-direction: column;
}

.replay-grid {
  flex: 1;
  min-height: 0;
  grid-template-columns: minmax(0, 2fr) minmax(260px, 0.58fr);
  gap: 16px;
  align-items: stretch;
}

.replay-main-card,
.replay-metrics-card {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.replay-head-row {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.replay-title,
.metrics-title {
  margin: 0;
}

.replay-view-actions {
  justify-content: flex-end;
}

.replay-canvas {
  flex: 1;
  min-height: 320px;
  border-radius: 12px;
  overflow: hidden;
}

.replay-control-panel {
  margin-top: 14px;
  padding: 4px 0 0;
  display: grid;
  gap: 8px;
}

.replay-metrics-list {
  display: grid;
  gap: 10px;
  overflow: auto;
  min-height: 0;
}

.metrics-head {
  margin: 0 0 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.metrics-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--chip-text);
  background: var(--chip-bg);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 9px;
}

.metrics-hero {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 85%, transparent) 0%, color-mix(in srgb, var(--surface-hover) 85%, transparent) 100%);
}

.metrics-hero-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.metrics-hero-title {
  font-size: 12px;
  color: var(--muted);
}

.metrics-hero-value {
  font-size: 18px;
  font-weight: 800;
  color: var(--chart-text);
}

.metrics-progress-track {
  margin-top: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--track-bg);
  overflow: hidden;
}

.metrics-progress-active {
  height: 100%;
  background: linear-gradient(90deg, var(--chart-primary) 0%, var(--chart-secondary) 100%);
}

.metrics-hero-sub {
  margin-top: 8px;
  font-size: 12px;
  color: var(--chart-muted);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-tile {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-soft);
  padding: 10px;
}

.metric-tile.span-2 {
  grid-column: 1 / -1;
}

.metric-label {
  font-size: 12px;
  color: var(--muted);
}

.metric-value {
  margin-top: 4px;
  font-size: 16px;
  font-weight: 800;
  color: var(--chart-text);
}

.metric-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--chart-muted);
}

.gauge-controls-row {
  width: 100%;
  display: flex;
  justify-content: stretch;
}

.gauge-controls {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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

.media-btn-speed {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  padding: 0;
  font-size: 12px;
  font-weight: 700;
}

@media (max-width: 1200px) {
  .replay-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
