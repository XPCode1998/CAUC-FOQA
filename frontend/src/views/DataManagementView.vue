<template>
  <MainLayout>
    <div class="card manager-card">
      <div class="manager-head">
        <div>
          <h3 class="section-title">QAR 数据管理</h3>
          <div class="section-subtitle">QAR记录上传、预览与删除</div>

        </div>
        <button class="btn btn-primary" type="button" @click="openAddDialog">新增数据</button>
      </div>

      <div class="manager-table-wrap">
        <el-table v-loading="tableLoading" :data="tableRows" stripe border height="100%" class="manager-table">
          <el-table-column prop="qar_id" label="QARID" min-width="180" show-overflow-tooltip />
          <el-table-column label="飞行时长" min-width="120">
            <template #default="scope">{{ formatTableNumber(scope.row.flight_duration) }} s</template>
          </el-table-column>
          <el-table-column label="参数维度" min-width="100">
            <template #default="scope">{{ formatTableInteger(scope.row.parameter_dimension) }} 维</template>
          </el-table-column>
          <el-table-column label="超限比例" min-width="120">
            <template #default="scope">{{ formatTableNumber(scope.row.exceed_ratio) }}%</template>
          </el-table-column>
          <el-table-column label="数据缺失比例" min-width="130">
            <template #default="scope">{{ formatTableNumber(scope.row.missing_ratio) }}%</template>
          </el-table-column>
          <el-table-column label="后处理状态" min-width="130" show-overflow-tooltip>
            <template #default="scope">
              <span :class="statusTagClass(scope.row.post_process_status)">
                {{ formatPostProcessStatus(scope.row.post_process_status) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="risk_label" label="风险标签" min-width="120" />
          <el-table-column label="创建时间" min-width="170" show-overflow-tooltip>
            <template #default="scope">{{ formatDateTime(scope.row.created_time) }}</template>
          </el-table-column>
          <el-table-column label="修改时间" min-width="170" show-overflow-tooltip>
            <template #default="scope">{{ formatDateTime(scope.row.updated_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="92" fixed="right">
            <template #default="scope">
              <div class="row-actions">
                <button
                  class="row-icon-btn row-icon-btn-preview"
                  type="button"
                  title="预览"
                  aria-label="预览"
                  @click="viewDetail(scope.row.qar_id)"
                >
                  <span class="material-symbols-outlined" aria-hidden="true">visibility</span>
                </button>
                <button
                  class="row-icon-btn row-icon-btn-delete"
                  type="button"
                  title="删除"
                  aria-label="删除"
                  :disabled="deleting"
                  @click="deleteByRow(scope.row)"
                >
                  <span class="material-symbols-outlined" aria-hidden="true">delete</span>
                </button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="manager-footer">
        <div class="upload-tip" :class="{ error: tableError }">{{ tableMessage }}</div>
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="tableTotal"
          :current-page="tablePage"
          :page-size="tablePageSize"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="handleTablePageChange"
          @size-change="handleTablePageSizeChange"
        />
      </div>
    </div>

    <teleport to="body">
      <div v-if="addDialogVisible" class="upload-modal-mask" @click="closeAddDialog">
        <div class="upload-modal card" @click.stop>
          <div class="upload-head">
            <div>
              <h3 style="margin: 0;">数据上传</h3>
              <div class="status-chip" :class="statusClass">{{ statusText }}</div>
            </div>
            <button class="icon-btn icon-btn-close" type="button" @click="closeAddDialog" aria-label="关闭" title="关闭">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18.3 5.71a1 1 0 0 0-1.42 0L12 10.59 7.12 5.7A1 1 0 0 0 5.7 7.13L10.58 12l-4.9 4.88a1 1 0 0 0 1.43 1.42L12 13.41l4.88 4.89a1 1 0 0 0 1.42-1.43L13.41 12l4.89-4.88a1 1 0 0 0 0-1.41z" />
              </svg>
            </button>
          </div>

          <div class="grid upload-form-grid">
            <div
              class="upload-dropzone"
              :class="{ active: dragOver, invalid: file && !isFileTypeValid }"
              @dragover.prevent="onDragOver"
              @dragleave.prevent="onDragLeave"
              @drop.prevent="onDrop"
              @click="triggerPickFile"
            >
              <input
                ref="fileInputRef"
                type="file"
                accept=".csv,.txt"
                style="display: none;"
                @change="onFileChange"
              />

              <div class="dropzone-icon">&#8682;</div>
              <div class="dropzone-title">拖拽文件到此处，或点击选择文件</div>
              <div class="dropzone-subtitle">支持 .csv / .txt</div>

              <div v-if="file" class="file-meta">
                <div class="file-name" :title="file.name">{{ file.name }}</div>
                <div class="file-info">{{ fileExtension.toUpperCase() || 'UNKNOWN' }} · {{ fileSizeText }}</div>
              </div>
            </div>

            <div class="upload-group">
              <div class="upload-label">风险标签</div>
              <div class="label-switch">
                <button
                  v-for="option in labelOptions"
                  :key="String(option.value)"
                  class="btn"
                  :class="label === option.value ? 'btn-primary' : 'btn-ghost'"
                  type="button"
                  @click="label = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>
          </div>

          <div class="upload-actions">
            <div class="upload-tip" :class="{ error: isError }">{{ message }}</div>
            <button class="btn btn-ghost" type="button" :disabled="loading" @click="closeAddDialog">取消</button>
            <button class="btn btn-primary" type="button" :disabled="!canSubmit" @click="submit">
              {{ loading ? '上传中...' : '确定' }}
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <teleport to="body">
      <div v-if="deleteDialogVisible" class="upload-modal-mask" @click="closeDeleteDialog">
        <div class="delete-confirm-modal card" @click.stop>
          <div class="upload-head delete-confirm-head">
            <h3 style="margin: 0;">删除确认</h3>
            <button class="icon-btn icon-btn-close" type="button" @click="closeDeleteDialog" aria-label="关闭" title="关闭">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18.3 5.71a1 1 0 0 0-1.42 0L12 10.59 7.12 5.7A1 1 0 0 0 5.7 7.13L10.58 12l-4.9 4.88a1 1 0 0 0 1.43 1.42L12 13.41l4.88 4.89a1 1 0 0 0 1.42-1.43L13.41 12l4.89-4.88a1 1 0 0 0 0-1.41z" />
              </svg>
            </button>
          </div>
          <p class="delete-confirm-text">
            确认删除 QAR ID: {{ deleteTargetQarId }} 的全部记录吗？此操作不可撤销。
          </p>
          <div class="upload-actions delete-confirm-actions">
            <button class="btn btn-ghost" type="button" :disabled="deleting" @click="closeDeleteDialog">取消</button>
            <button class="btn btn-primary" type="button" :disabled="deleting" @click="confirmDelete">
              {{ deleting ? '删除中...' : '确定删除' }}
            </button>
          </div>
        </div>
      </div>
    </teleport>
  </MainLayout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import {
  apiDataDeleteQar,
  apiDataQarManagementList,
  apiDataUploadRaw,
  apiDataUploadRawFinalize,
} from '../api/dataApi'
import { useDataQarContextStore } from '../stores/dataQarContext'
import { formatTableCellValue } from '../utils/tableFormat'

const router = useRouter()
const qarContextStore = useDataQarContextStore()

const label = ref(null)
const file = ref(null)
const loading = ref(false)
const message = ref('请先选择文件并设置标签。')
const isError = ref(false)
const dragOver = ref(false)
const fileInputRef = ref(null)
const result = ref(null)
const addDialogVisible = ref(false)
const deleteDialogVisible = ref(false)
const deleteTargetQarId = ref('')

const deleting = ref(false)
const tableLoading = ref(false)
const tableError = ref(false)
const tableMessage = ref('')
const tableRows = ref([])
const tableTotal = ref(0)
const tablePage = ref(1)
const tablePageSize = ref(20)

const labelOptions = [
  { value: null, label: '未选择' },
  { value: 0, label: '正常状态' },
  { value: 1, label: '结冰状态' },
  { value: 2, label: '单发失效' },
  { value: 3, label: '双发失效' },
  { value: 4, label: '低能量' },
]
const allowedExt = new Set(['csv', 'txt'])
const LARGE_FILE_THRESHOLD_BYTES = 50 * 1024 * 1024
const CSV_ROWS_PER_CHUNK = 6000
const CHUNK_CONCURRENCY = 4

const fileExtension = computed(() => {
  if (!file.value?.name) return ''
  const segments = file.value.name.split('.')
  return segments.length > 1 ? segments[segments.length - 1].toLowerCase() : ''
})

const isFileTypeValid = computed(() => {
  if (!file.value) return true
  return allowedExt.has(fileExtension.value)
})

const fileSizeText = computed(() => {
  if (!file.value?.size) return '0 B'
  const size = file.value.size
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(2)} MB`
})

const canSubmit = computed(() => !!file.value && !loading.value && isFileTypeValid.value)

const statusText = computed(() => {
  if (loading.value) return '上传中'
  if (result.value?.code === 0) return '已完成'
  if (isError.value) return '异常'
  return '待上传'
})

const statusClass = computed(() => {
  if (loading.value) return 'working'
  if (result.value?.code === 0) return 'ok'
  if (isError.value) return 'error'
  return 'idle'
})

function formatTableNumber(value) {
  return formatTableCellValue(value, 4, '-')
}

function formatTableInteger(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return String(Math.round(numeric))
}

function formatPostProcessStatus(value) {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'pending') return '待处理'
  if (normalized === 'running') return '处理中'
  if (normalized === 'success') return '成功'
  if (normalized === 'failed') return '失败'
  return '未知'
}

function statusTagClass(value) {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'success') return 'post-status post-status-success'
  if (normalized === 'failed') return 'post-status post-status-failed'
  if (normalized === 'running') return 'post-status post-status-running'
  if (normalized === 'pending') return 'post-status post-status-pending'
  return 'post-status'
}

function openAddDialog() {
  addDialogVisible.value = true
}

function closeAddDialog() {
  if (loading.value) return
  addDialogVisible.value = false
}

function triggerPickFile() {
  if (loading.value) return
  fileInputRef.value?.click()
}

function setFile(nextFile) {
  file.value = nextFile || null
  result.value = null

  if (!file.value) {
    message.value = '请先选择文件并设置标签。'
    isError.value = false
    return
  }

  if (!isFileTypeValid.value) {
    message.value = '仅支持上传 .csv 或 .txt 文件。'
    isError.value = true
    return
  }

  message.value = '文件已就绪，可开始上传。'
  isError.value = false
}

function onFileChange(e) {
  setFile(e.target.files?.[0] || null)
}

function onDragOver() {
  if (loading.value) return
  dragOver.value = true
}

function onDragLeave() {
  dragOver.value = false
}

function onDrop(e) {
  if (loading.value) return
  dragOver.value = false
  setFile(e.dataTransfer?.files?.[0] || null)
}

function clearForm() {
  if (loading.value) return
  label.value = null
  setFile(null)
  message.value = '表单已清空。'
  isError.value = false
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

async function submit() {
  if (!file.value) {
    message.value = '请先选择文件。'
    isError.value = true
    return
  }
  if (!isFileTypeValid.value) {
    message.value = '文件格式不支持，请上传 .csv 或 .txt。'
    isError.value = true
    return
  }

  loading.value = true
  message.value = '正在上传，请稍候...'
  isError.value = false
  result.value = null

  try {
    const res = file.value.size >= LARGE_FILE_THRESHOLD_BYTES
      ? await uploadLargeCsvInChunks(file.value)
      : await uploadSingleFile(file.value)

    result.value = {
      code: Number(res?.code ?? -1),
      message: res?.message || '',
    }

    if (res.code !== 0) {
      throw new Error(res.message || '上传失败')
    }

    message.value = res.message || '上传成功，数据已入库。'
    isError.value = false
    closeAddDialog()
    clearForm()
    await loadTable()
  } catch (e) {
    message.value = e?.message || '上传失败'
    isError.value = true
  } finally {
    loading.value = false
  }
}

function buildQarIdByFilename(name) {
  const base = String(name || 'upload')
    .replace(/\.[^.]+$/, '')
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
  const safeBase = base || 'upload'
  return `${safeBase}_${Date.now()}`
}

async function uploadSingleFile(selectedFile) {
  const form = new FormData()
  if (label.value !== null && label.value !== undefined && label.value !== '') {
    form.append('label', String(label.value))
  }
  form.append('file', selectedFile)
  const res = await apiDataUploadRaw(form)
  return {
    ...res,
    message: '上传成功，数据已入库，后台正在异步计算统计与轨迹。',
  }
}

function splitCsvWithHeader(content, rowsPerChunk) {
  const lines = String(content).split(/\r?\n/)
  const nonEmptyLines = lines.filter((line) => line !== '')
  if (nonEmptyLines.length < 2) {
    throw new Error('CSV 内容为空或仅包含表头。')
  }

  const header = nonEmptyLines[0]
  const rows = nonEmptyLines.slice(1)
  const chunks = []

  for (let i = 0; i < rows.length; i += rowsPerChunk) {
    const chunkRows = rows.slice(i, i + rowsPerChunk)
    chunks.push([header, ...chunkRows].join('\n'))
  }

  return chunks
}

async function runChunkQueue(chunkUploadTasks, concurrency) {
  const results = []
  let cursor = 0

  async function worker() {
    while (cursor < chunkUploadTasks.length) {
      const current = cursor
      cursor += 1
      results[current] = await chunkUploadTasks[current]()
    }
  }

  const workerCount = Math.max(1, Math.min(concurrency, chunkUploadTasks.length))
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  return results
}

async function uploadLargeCsvInChunks(selectedFile) {
  const qarId = buildQarIdByFilename(selectedFile.name)
  const text = await selectedFile.text()
  const chunks = splitCsvWithHeader(text, CSV_ROWS_PER_CHUNK)
  const totalChunks = chunks.length

  if (!totalChunks) {
    throw new Error('未解析到可上传的数据行。')
  }

  message.value = `检测到大文件，开始分片并行上传（共 ${totalChunks} 片）...`

  const chunkUploadTasks = chunks.map((chunkContent, index) => async () => {
    const chunkBlob = new Blob([chunkContent], { type: 'text/csv;charset=utf-8' })
    const chunkFile = new File([chunkBlob], `${selectedFile.name.replace(/\.[^.]+$/, '')}_part_${index + 1}.csv`, {
      type: 'text/csv',
    })

    const form = new FormData()
    form.append('qar_id', qarId)
    if (label.value !== null && label.value !== undefined && label.value !== '') {
      form.append('label', String(label.value))
    }
    form.append('file', chunkFile)

    const uploadRes = await apiDataUploadRaw(form, {
      skipPostProcess: true,
      chunkIndex: index + 1,
      chunkCount: totalChunks,
    })

    if (uploadRes?.code !== 0) {
      throw new Error(uploadRes?.message || `分片 ${index + 1} 上传失败`)
    }

    message.value = `分片上传中：${index + 1}/${totalChunks}`
    return uploadRes
  })

  await runChunkQueue(chunkUploadTasks, CHUNK_CONCURRENCY)

  message.value = '分片已上传完成，正在触发后台异步计算...'
  const finalizeRes = await apiDataUploadRawFinalize(qarId)
  if (finalizeRes?.code !== 0) {
    throw new Error(finalizeRes?.message || '触发后台处理失败')
  }

  return {
    code: 0,
    message: `大文件上传完成（QAR ID: ${qarId}），后台正在异步计算掩码/统计/轨迹。`,
  }
}

async function loadTable() {
  tableLoading.value = true
  tableError.value = false
  tableMessage.value = ''
  try {
    const res = await apiDataQarManagementList({ page: tablePage.value, page_size: tablePageSize.value })
    if (res.code !== 0) {
      throw new Error(res.message || '加载失败')
    }
    tableRows.value = res?.data?.items || []
    tableTotal.value = Number(res?.data?.total || 0)
    tableMessage.value = `已加载 ${tableRows.value.length} 条记录。`
  } catch (e) {
    tableRows.value = []
    tableTotal.value = 0
    tableError.value = true
    tableMessage.value = e?.message || '加载失败'
  } finally {
    tableLoading.value = false
  }
}

function handleTablePageChange(nextPage) {
  tablePage.value = nextPage
  loadTable()
}

function handleTablePageSizeChange(nextSize) {
  tablePageSize.value = nextSize
  tablePage.value = 1
  loadTable()
}

function viewDetail(qarId) {
  if (!qarId) return
  qarContextStore.setCurrentQarId(qarId)
  router.push({ name: 'data-preview', query: { qar_id: qarId } })
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`
}

async function deleteByRow(row) {
  const qarId = row?.qar_id
  if (!qarId) return

  deleteTargetQarId.value = qarId
  deleteDialogVisible.value = true
}

function closeDeleteDialog(force = false) {
  if (deleting.value && !force) return
  deleteDialogVisible.value = false
  deleteTargetQarId.value = ''
}

async function confirmDelete() {
  const qarId = deleteTargetQarId.value
  if (!qarId) return

  deleting.value = true
  tableError.value = false
  tableMessage.value = '正在删除，请稍候...'
  try {
    const res = await apiDataDeleteQar(qarId)
    if (res.code !== 0) {
      throw new Error(res.message || '删除失败')
    }
    tableMessage.value = `删除成功：${qarId}（主记录 ${res?.data?.deleted_rows ?? 0} 条）。`
    deleting.value = false
    closeDeleteDialog(true)
    await loadTable()
  } catch (e) {
    tableError.value = true
    const errorMsg = String(e?.message || '')
    if (errorMsg.toLowerCase().includes('timeout')) {
      tableMessage.value = '删除请求超时（超过 180 秒）。数据量较大时删除会较慢，请稍后刷新列表确认结果。'
    } else {
      tableMessage.value = errorMsg || '删除失败'
    }
  } finally {
    deleting.value = false
  }
}

loadTable()
</script>

<style scoped>
.manager-card {
  padding: 14px;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.manager-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.manager-table-wrap {
  flex: 1;
  min-height: 0;
}

.manager-table {
  width: 100%;
}

.manager-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.row-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
}

.post-status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.5;
}

.post-status-success {
  color: #0f8f61;
  background: rgba(15, 143, 97, 0.12);
}

.post-status-failed {
  color: #c43838;
  background: rgba(196, 56, 56, 0.12);
}

.post-status-running {
  color: #2457c5;
  background: rgba(36, 87, 197, 0.12);
}

.post-status-pending {
  color: #8a6400;
  background: rgba(138, 100, 0, 0.14);
}

.row-icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.row-icon-btn .material-symbols-outlined {
  font-size: 18px;
}

.row-icon-btn-preview {
  background: color-mix(in srgb, var(--brand) 18%, transparent);
  color: var(--brand);
}

.row-icon-btn-preview:hover {
  background: color-mix(in srgb, var(--brand) 28%, transparent);
  border-color: color-mix(in srgb, var(--brand) 45%, var(--border));
}

.row-icon-btn-delete {
  background: color-mix(in srgb, var(--danger) 18%, transparent);
  color: var(--danger);
}

.row-icon-btn-delete:hover {
  background: color-mix(in srgb, var(--danger) 26%, transparent);
  border-color: color-mix(in srgb, var(--danger) 45%, var(--border));
}

.row-icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-modal-mask {
  position: fixed;
  inset: 0;
  background: var(--overlay-loading-bg);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 1000;
}

.upload-modal {
  width: min(920px, 100%);
  max-height: min(88vh, 900px);
  overflow: auto;
  padding: 18px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.delete-confirm-modal {
  width: min(560px, 100%);
  padding: 18px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.delete-confirm-head {
  margin-bottom: 10px;
}

.delete-confirm-text {
  margin: 0;
  font-size: 16px;
  line-height: 1.7;
  color: var(--text);
}

.delete-confirm-actions {
  margin-top: 18px;
}

.upload-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 14px;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  background: var(--surface-soft);
  color: #81ecff;
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.icon-btn-close {
  width: 38px;
  height: 38px;
  border-radius: 999px;
}

.icon-btn-close:hover {
  background: var(--surface-hover);
}

.upload-subtitle {
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}

.status-chip {
  margin-top: 8px;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid transparent;
}

.status-chip.idle {
  color: var(--chip-text);
  background: var(--chip-bg);
  border-color: var(--border);
}

.status-chip.working {
  color: color-mix(in srgb, var(--text) 75%, #e9b949 25%);
  background: color-mix(in srgb, #e9b949 22%, transparent);
  border-color: color-mix(in srgb, #e9b949 38%, var(--border));
}

.status-chip.ok {
  color: color-mix(in srgb, var(--text) 70%, var(--brand-2) 30%);
  background: color-mix(in srgb, var(--brand-2) 20%, transparent);
  border-color: color-mix(in srgb, var(--brand-2) 36%, var(--border));
}

.status-chip.error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 20%, transparent);
  border-color: color-mix(in srgb, var(--danger) 38%, var(--border));
}

.upload-form-grid {
  grid-template-columns: minmax(0, 1fr);
  align-items: stretch;
}

.upload-group {
  display: grid;
  gap: 8px;
}

.upload-label {
  font-size: 13px;
  font-weight: 700;
}

.upload-hint {
  font-size: 12px;
  color: var(--muted);
}

.label-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.label-switch .btn {
  min-width: 78px;
  padding: 8px 10px;
}

.upload-dropzone {
  border: 1px dashed color-mix(in srgb, var(--brand) 45%, var(--border));
  border-radius: 14px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 88%, transparent) 0%, color-mix(in srgb, var(--surface-hover) 88%, transparent) 100%);
  min-height: 210px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 6px;
  padding: 14px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s ease;
}

.upload-dropzone:hover {
  border-color: #8cb0e6;
}

.upload-dropzone.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(15, 123, 255, 0.12);
}

.upload-dropzone.invalid {
  border-color: var(--danger);
  box-shadow: 0 0 0 3px rgba(214, 69, 69, 0.12);
}

.dropzone-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #e5efff;
  color: #0d5cca;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 700;
}

.dropzone-title {
  font-size: 13px;
  font-weight: 700;
}

.dropzone-subtitle {
  font-size: 12px;
  color: var(--muted);
}

.file-meta {
  margin-top: 5px;
  border-top: 1px dashed #d5e2f6;
  padding-top: 8px;
  width: 100%;
  max-width: 420px;
}

.file-name {
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-info {
  margin-top: 3px;
  font-size: 12px;
  color: var(--muted);
}

.upload-actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-tip {
  margin-right: auto;
  font-size: 12px;
  color: var(--muted);
}

.upload-tip.error {
  color: var(--danger);
}

@media (max-width: 900px) {
  .manager-footer {
    justify-content: flex-end;
  }
}
</style>
