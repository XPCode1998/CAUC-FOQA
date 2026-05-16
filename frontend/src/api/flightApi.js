import http from './http'
import { buildRequestCacheKey, cachedRequest } from './requestCache'

const FLIGHT_CACHE_NS = 'flight'

const FLIGHT_TTL_MS = {
  overview: 45_000,
  charts: 60_000,
  trajectory: 60_000,
  replay: 45_000,
  risk: 30_000,
}

export async function apiFlightOverview(qarId) {
  const params = { qar_id: qarId }
  const key = buildRequestCacheKey(FLIGHT_CACHE_NS, '/flight/overview', params)
  return cachedRequest({
    key,
    ttlMs: FLIGHT_TTL_MS.overview,
    fetcher: async () => {
      const { data } = await http.get('/flight/overview', { params })
      return data
    },
  })
}

export async function apiFlightCharts(qarId, maxPoints = 1200, fields = []) {
  const params = { qar_id: qarId, max_points: maxPoints }
  if (Array.isArray(fields) && fields.length) {
    params.fields = fields.join(',')
  }
  const key = buildRequestCacheKey(FLIGHT_CACHE_NS, '/flight/charts', params)
  return cachedRequest({
    key,
    ttlMs: FLIGHT_TTL_MS.charts,
    fetcher: async () => {
      const { data } = await http.get('/flight/charts', { params })
      return data
    },
  })
}

export async function apiFlightTrajectory(qarId, maxPoints = 2200) {
  const params = { qar_id: qarId, max_points: maxPoints }
  const key = buildRequestCacheKey(FLIGHT_CACHE_NS, '/flight/trajectory', params)
  return cachedRequest({
    key,
    ttlMs: FLIGHT_TTL_MS.trajectory,
    fetcher: async () => {
      const { data } = await http.get('/flight/trajectory', { params })
      return data
    },
  })
}

export async function apiFlightReplay(qarId, maxPoints = 30000) {
  const params = { qar_id: qarId, max_points: maxPoints }
  const key = buildRequestCacheKey(FLIGHT_CACHE_NS, '/flight/replay', params)
  return cachedRequest({
    key,
    ttlMs: FLIGHT_TTL_MS.replay,
    fetcher: async () => {
      const { data } = await http.get('/flight/replay', { params })
      return data
    },
  })
}

export async function apiFlightRiskOverlimit(qarId) {
  const params = { qar_id: qarId }
  const key = buildRequestCacheKey(FLIGHT_CACHE_NS, '/flight/risk/overlimit', params)
  return cachedRequest({
    key,
    ttlMs: FLIGHT_TTL_MS.risk,
    fetcher: async () => {
      const { data } = await http.get('/flight/risk/overlimit', { params })
      return data
    },
  })
}
