import http from './http'

export async function apiLogin(payload) {
  const { data } = await http.post('/auth/login', payload)
  return data
}

export async function apiRegister(payload) {
  const { data } = await http.post('/auth/register', payload)
  return data
}

export async function apiMe() {
  const { data } = await http.get('/auth/me')
  return data
}

export async function apiResetPassword(payload) {
  const { data } = await http.post('/auth/reset-password', payload)
  return data
}
