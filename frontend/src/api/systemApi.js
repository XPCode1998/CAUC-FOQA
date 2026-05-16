import http from './http'

export async function apiSystemMetrics() {
  const { data } = await http.get('/system/metrics')
  return data
}

export async function apiSystemBackupList() {
  const { data } = await http.get('/system/backup/list')
  return data
}

export async function apiSystemBackupRun() {
  const { data } = await http.post('/system/backup/run', {})
  return data
}

export async function apiSystemBackupJobStatus(params = {}) {
  const { data } = await http.get('/system/backup/job/status', { params })
  return data
}

export async function apiSystemBackupPrecheck(params) {
  const { data } = await http.get('/system/backup/precheck', { params })
  return data
}

export async function apiSystemBackupRestore(payload) {
  const { data } = await http.post('/system/backup/restore', payload)
  return data
}

export async function apiSystemOpsLogs(params = {}) {
  const { data } = await http.get('/system/ops/logs', { params })
  return data
}

export async function apiSystemTestRun(payload = {}) {
  const { data } = await http.post('/system/test/run', payload)
  return data
}

export async function apiSystemTestStatus(params = {}) {
  const { data } = await http.get('/system/test/status', { params })
  return data
}

export async function apiSystemTestMetricUpdate(payload = {}) {
  const { data } = await http.post('/system/test/metric/update', payload)
  return data
}

export async function apiSystemTestUploadProbe(formData) {
  const { data } = await http.post('/system/test/upload-probe', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 600000,
  })
  return data
}
