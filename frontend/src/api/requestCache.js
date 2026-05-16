const requestCache = new Map()

function serializeParams(params = {}) {
  const keys = Object.keys(params).sort()
  return keys
    .map((key) => {
      const value = params[key]
      if (value === undefined || value === null || value === '') {
        return `${encodeURIComponent(key)}=`
      }
      if (Array.isArray(value)) {
        return `${encodeURIComponent(key)}=${encodeURIComponent(value.join(','))}`
      }
      if (typeof value === 'object') {
        return `${encodeURIComponent(key)}=${encodeURIComponent(JSON.stringify(value))}`
      }
      return `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`
    })
    .join('&')
}

export function buildRequestCacheKey(namespace, path, params = {}) {
  return `${namespace}:${path}?${serializeParams(params)}`
}

export async function cachedRequest({ key, ttlMs, fetcher }) {
  const now = Date.now()
  const cached = requestCache.get(key)

  if (cached?.data && cached.expireAt > now) {
    return cached.data
  }

  if (cached?.promise) {
    return cached.promise
  }

  const promise = Promise.resolve()
    .then(fetcher)
    .then((data) => {
      requestCache.set(key, {
        data,
        expireAt: Date.now() + ttlMs,
      })
      return data
    })
    .catch((error) => {
      requestCache.delete(key)
      throw error
    })

  requestCache.set(key, {
    data: cached?.data,
    expireAt: cached?.expireAt || 0,
    promise,
  })

  return promise
}

export function invalidateCacheByPrefix(prefix) {
  for (const key of requestCache.keys()) {
    if (key.startsWith(prefix)) {
      requestCache.delete(key)
    }
  }
}

export function clearRequestCache() {
  requestCache.clear()
}
