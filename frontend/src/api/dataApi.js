import http from './http'
import { buildRequestCacheKey, cachedRequest, invalidateCacheByPrefix } from './requestCache'

const DATA_CACHE_NS = 'data'

const DATA_TTL_MS = {
  preview: 45_000,
  qarIds: 300_000,
  management: 30_000,
  thresholds: 120_000,
  parameterDimensions: 120_000,
  imputationPreview: 45_000,
  imputationModels: 30_000,
  imputationTrainHyperparams: 300_000,
}

export async function apiDataPreview(params) {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/preview', params)
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.preview,
    fetcher: async () => {
      const { data } = await http.get('/data/preview', { params })
      return data
    },
  })
}

export async function apiDataPreviewUpdate(payload) {
  const { data } = await http.put('/data/preview', payload)
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/preview?`)
  return data
}

export async function apiDataQarIds(params = {}) {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/qar-ids', params)
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.qarIds,
    fetcher: async () => {
      const { data } = await http.get('/data/qar-ids', { params })
      return data
    },
  })
}

export async function apiDataQarManagementList(params = {}) {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/qar-management', params)
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.management,
    fetcher: async () => {
      const { data } = await http.get('/data/qar-management', { params })
      return data
    },
  })
}

export async function apiDataUploadRaw(formData, options = {}) {
  const params = {}
  if (options?.skipPostProcess) {
    params.skip_post_process = 1
  }
  if (options?.chunkIndex !== undefined) {
    params.chunk_index = options.chunkIndex
  }
  if (options?.chunkCount !== undefined) {
    params.chunk_count = options.chunkCount
  }
  const { data } = await http.post('/data/upload-raw', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
  })
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/`)
  return data
}

export async function apiDataUploadRawFinalize(qarId) {
  const { data } = await http.post('/data/upload-raw/finalize', { qar_id: qarId })
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/`)
  return data
}

export async function apiDataDeleteQar(qarId) {
  const { data } = await http.delete('/data/qar', {
    data: { qar_id: qarId },
    timeout: 180000,
  })
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/`)
  invalidateCacheByPrefix('flight:/flight/')
  return data
}

export async function apiDataThresholds(monitoredOnly = false) {
  const params = { monitored_only: monitoredOnly ? 1 : 0 }
  const { data } = await http.get('/data/thresholds', {
    params,
  })
  return data
}

export async function apiDataParameterDimensions() {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/parameter-dimensions')
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.parameterDimensions,
    fetcher: async () => {
      const { data } = await http.get('/data/parameter-dimensions')
      return data
    },
  })
}

export async function apiDataSaveParameterDimensions(items) {
  const { data } = await http.put('/data/parameter-dimensions', { items })
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/parameter-dimensions?`)
  return data
}

export async function apiDataSaveThresholds(items) {
  const { data } = await http.put('/data/thresholds', { items })
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/thresholds?`)
  return data
}

export async function apiDataImputationPreview(params) {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/imputation/preview', params)
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.imputationPreview,
    fetcher: async () => {
      const { data } = await http.get('/data/imputation/preview', { params })
      return data
    },
  })
}

export async function apiDataImputationRepair(payload) {
  const { data } = await http.post('/data/imputation/repair', payload)
  invalidateCacheByPrefix(`${DATA_CACHE_NS}:/data/imputation/preview?`)
  return data
}

export async function apiDataImputationTrainHyperparams() {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/imputation/train/hyperparams')
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.imputationTrainHyperparams,
    fetcher: async () => {
      const { data } = await http.get('/data/imputation/train/hyperparams')
      return data
    },
  })
}

export async function apiDataImputationModels(params = {}) {
  const key = buildRequestCacheKey(DATA_CACHE_NS, '/data/imputation/models', params)
  return cachedRequest({
    key,
    ttlMs: DATA_TTL_MS.imputationModels,
    fetcher: async () => {
      const { data } = await http.get('/data/imputation/models', { params })
      return data
    },
  })
}

export async function apiDataImputationTrain(payload = {}) {
  const { data } = await http.post('/data/imputation/train', payload)
  return data
}

export async function apiDataImputationTrainStop() {
  const { data } = await http.post('/data/imputation/stream/train/stop', {})
  return data
}
