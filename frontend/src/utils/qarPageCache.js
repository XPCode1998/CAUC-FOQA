const CACHE_PREFIX = 'qar_page_cache:'
const DEFAULT_TTL_MS = 5 * 60 * 1000
const PERSIST_MAX_BYTES = 300000

const memoryCache = new Map()

function buildKey(pageKey, qarId, variant = '') {
  const normalizedPage = String(pageKey || '').trim()
  const normalizedQarId = String(qarId || '').trim()
  const normalizedVariant = String(variant || '').trim()
  return `${CACHE_PREFIX}${normalizedPage}:${normalizedQarId}:${normalizedVariant}`
}

function nowMs() {
  return Date.now()
}

function safeParse(text) {
  try {
    return JSON.parse(text)
  } catch (_) {
    return null
  }
}

function safeStringify(value) {
  try {
    return JSON.stringify(value)
  } catch (_) {
    return ''
  }
}

function readLocal(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? safeParse(raw) : null
  } catch (_) {
    return null
  }
}

function writeLocal(key, value) {
  try {
    const text = safeStringify(value)
    if (!text) return
    if (text.length > PERSIST_MAX_BYTES) return
    localStorage.setItem(key, text)
  } catch (_) {
    // ignore persistence errors
  }
}

function deleteLocal(key) {
  try {
    localStorage.removeItem(key)
  } catch (_) {
    // ignore persistence errors
  }
}

export function setQarPageCache(pageKey, qarId, variant, payload, ttlMs = DEFAULT_TTL_MS) {
  const key = buildKey(pageKey, qarId, variant)
  const record = {
    expireAt: nowMs() + Math.max(1000, Number(ttlMs) || DEFAULT_TTL_MS),
    payload,
  }
  memoryCache.set(key, record)
  writeLocal(key, record)
}

export function getQarPageCache(pageKey, qarId, variant = '') {
  const key = buildKey(pageKey, qarId, variant)
  const current = nowMs()

  const mem = memoryCache.get(key)
  if (mem && mem.expireAt > current) {
    return mem.payload
  }

  const local = readLocal(key)
  if (local && local.expireAt > current) {
    memoryCache.set(key, local)
    return local.payload
  }

  memoryCache.delete(key)
  deleteLocal(key)
  return null
}

export function clearQarPageCache(pageKey, qarId, variant = '') {
  const key = buildKey(pageKey, qarId, variant)
  memoryCache.delete(key)
  deleteLocal(key)
}
