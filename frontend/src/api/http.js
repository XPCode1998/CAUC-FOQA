import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status
    const original = error.config || {}

    if (status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const r = await axios.post('/api/v1/auth/refresh', { refresh })
          const nextAccess = r?.data?.access
          if (nextAccess) {
            localStorage.setItem('access_token', nextAccess)
            original.headers = original.headers || {}
            original.headers.Authorization = `Bearer ${nextAccess}`
            return http(original)
          }
        } catch (_) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
        }
      }
    }

    return Promise.reject(error)
  }
)

export default http
