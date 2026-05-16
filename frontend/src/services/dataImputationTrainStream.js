import { reactive } from 'vue'
import { apiDataImputationTrainStop } from '../api/dataApi'

export const imputationTrainStreamState = reactive({
  streamTraining: false,
  streamMeta: null,
  streamProgressText: '',
  statusEvents: [],
  message: '',
  resultText: '',
})

let streamAbortController = null
let activeRunId = 0

function normalizeStage(input, isRunning) {
  const text = String(input || '').toLowerCase()
  if (text.includes('done') || text.includes('finish') || text.includes('complete')) return 'done'
  if (text.includes('train') || text.includes('epoch') || text.includes('batch')) return 'training'
  if (text.includes('model') || text.includes('build_model') || text.includes('model_build')) return 'model'
  if (text.includes('data') || text.includes('dataset') || text.includes('prepare')) return 'dataset'
  if (text.includes('stop')) return 'stopped'
  return isRunning ? 'training' : 'dataset'
}

function appendStatusEvent(payload) {
  const stage = normalizeStage(payload.stage || payload.event || 'status', imputationTrainStreamState.streamTraining)
  const textParts = []
  if (payload.epoch && payload.total_epochs) textParts.push(`epoch ${payload.epoch}/${payload.total_epochs}`)
  if (payload.batch && payload.total_batches) textParts.push(`batch ${payload.batch}/${payload.total_batches}`)
  if (payload.loss !== undefined) textParts.push(`loss ${Number(payload.loss).toFixed(4)}`)
  if (payload.avg_loss !== undefined) textParts.push(`avg ${Number(payload.avg_loss).toFixed(4)}`)
  if (payload.val_loss !== undefined) textParts.push(`val ${Number(payload.val_loss).toFixed(4)}`)
  if (payload.elapsed_seconds !== undefined) textParts.push(`${Number(payload.elapsed_seconds).toFixed(1)}s`)
  const text = textParts.join(' | ') || (payload.message || '')

  imputationTrainStreamState.statusEvents = [
    ...imputationTrainStreamState.statusEvents.slice(-199),
    {
      stage,
      text,
      epoch: payload.epoch !== undefined ? Number(payload.epoch) : NaN,
      total_epochs: payload.total_epochs !== undefined ? Number(payload.total_epochs) : NaN,
      batch: payload.batch !== undefined ? Number(payload.batch) : NaN,
      total_batches: payload.total_batches !== undefined ? Number(payload.total_batches) : NaN,
      loss: payload.loss !== undefined ? Number(payload.loss) : NaN,
      avg_loss: payload.avg_loss !== undefined ? Number(payload.avg_loss) : NaN,
      val_loss: payload.val_loss !== undefined ? Number(payload.val_loss) : NaN,
    },
  ]
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

function consumeSseBuffer(state, handler, flush = false) {
  state.buffer = state.buffer.replace(/\r\n/g, '\n')
  while (true) {
    const marker = state.buffer.indexOf('\n\n')
    if (marker < 0) break
    const rawEvent = state.buffer.slice(0, marker).trim()
    state.buffer = state.buffer.slice(marker + 2)
    if (!rawEvent) continue
    handler(parseSseEvent(rawEvent))
  }

  if (flush && state.buffer.trim()) {
    handler(parseSseEvent(state.buffer.trim()))
    state.buffer = ''
  }
}

export async function startImputationTrainStream(payload) {
  if (imputationTrainStreamState.streamTraining) return

  activeRunId += 1
  const runId = activeRunId

  imputationTrainStreamState.streamTraining = true
  imputationTrainStreamState.message = ''
  imputationTrainStreamState.resultText = ''
  imputationTrainStreamState.streamMeta = null
  imputationTrainStreamState.streamProgressText = ''
  imputationTrainStreamState.statusEvents = []

  streamAbortController = new AbortController()

  try {
    const token = localStorage.getItem('access_token')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`

    const response = await fetch('/api/v1/data/imputation/stream/train', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: streamAbortController.signal,
    })

    if (!response.ok || !response.body) {
      const text = await response.text()
      throw new Error(text || `服务响应异常: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const state = { buffer: '' }

    const onEvent = (data) => {
      if (!data || typeof data !== 'object') return
      if (data.event === 'meta') {
        imputationTrainStreamState.streamMeta = data
        imputationTrainStreamState.streamProgressText = '训练准备中...'
        appendStatusEvent({ stage: 'dataset', message: '已接收训练任务元信息' })
        return
      }
      if (data.event === 'status') {
        appendStatusEvent(data)
        imputationTrainStreamState.streamProgressText = `阶段: ${data.stage || 'training'}`
        return
      }
      if (data.event === 'done') {
        appendStatusEvent({ stage: 'done', message: '训练完成' })
        imputationTrainStreamState.message = '流式训练完成。'
        imputationTrainStreamState.resultText = JSON.stringify(data, null, 2)
        return
      }
      if (data.event === 'stopped') {
        appendStatusEvent({ stage: 'stopped', message: data.message || '训练已停止' })
        imputationTrainStreamState.message = data.message || '训练已停止。'
        return
      }
      if (data.event === 'error') {
        appendStatusEvent({ stage: 'error', message: data.message || '训练失败' })
        throw new Error(data.message || '训练失败')
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      state.buffer += decoder.decode(value, { stream: true })
      consumeSseBuffer(state, onEvent)
    }
    state.buffer += decoder.decode()
    consumeSseBuffer(state, onEvent, true)
  } catch (e) {
    if (e?.name !== 'AbortError') {
      imputationTrainStreamState.message = e.message || '流式训练失败'
    }
  } finally {
    if (runId === activeRunId) {
      imputationTrainStreamState.streamTraining = false
      streamAbortController = null
    }
  }
}

export async function stopImputationTrainStream() {
  let stopMessage = ''
  try {
    const res = await apiDataImputationTrainStop()
    stopMessage = res?.data?.message || res?.message || ''
  } catch (e) {
    stopMessage = e?.message || '停止训练请求失败'
  }

  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }

  activeRunId += 1
  imputationTrainStreamState.streamTraining = false
  imputationTrainStreamState.streamProgressText = '训练已停止'
  if (stopMessage) {
    imputationTrainStreamState.message = stopMessage
  } else if (!imputationTrainStreamState.message) {
    imputationTrainStreamState.message = '已手动停止流式训练。'
  }

  appendStatusEvent({ stage: 'stopped', message: imputationTrainStreamState.message })
}
