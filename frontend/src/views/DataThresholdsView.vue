<template>
  <MainLayout>
    <div class="card data-preview-card">
     
      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="rows"
          stripe
          border
          height="100%"
          class="preview-table"
        >
          <el-table-column label="操作" fixed="left" width="96" align="center">
            <template #default="{ row }">
              <div class="op-cell">
                <template v-if="isRowEditing(row)">
                  <button class="icon-action icon-action-success" :disabled="saving" @click="confirmEdit(row)" title="确认修改">
                    <el-icon><Check /></el-icon>
                  </button>
                  <button class="icon-action icon-action-danger" :disabled="saving" @click="cancelEdit" title="取消修改">
                    <el-icon><Close /></el-icon>
                  </button>
                </template>
                <template v-else>
                  <button class="icon-action" :disabled="editingKey !== null" @click="startEdit(row)" title="编辑">
                    <el-icon><EditPen /></el-icon>
                  </button>
                </template>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="parameter_name" label="参数名" min-width="150" show-overflow-tooltip />
          <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />

          <el-table-column prop="unit" label="单位" min-width="90" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.unit || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="警告下限" min-width="140">
            <template #default="{ row }">
              <el-input v-if="isRowEditing(row)" v-model="editingDraft.warning_lower" size="small" />
              <span v-else>{{ formatThresholdValue(row.warning_lower) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="警告上限" min-width="140">
            <template #default="{ row }">
              <el-input v-if="isRowEditing(row)" v-model="editingDraft.warning_upper" size="small" />
              <span v-else>{{ formatThresholdValue(row.warning_upper) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="严重下限" min-width="140">
            <template #default="{ row }">
              <el-input v-if="isRowEditing(row)" v-model="editingDraft.critical_lower" size="small" />
              <span v-else>{{ formatThresholdValue(row.critical_lower) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="严重上限" min-width="140">
            <template #default="{ row }">
              <el-input v-if="isRowEditing(row)" v-model="editingDraft.critical_upper" size="small" />
              <span v-else>{{ formatThresholdValue(row.critical_upper) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="监控" min-width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-if="isRowEditing(row)" v-model="editingDraft.is_monitored" />
              <el-icon v-else-if="row.is_monitored" class="monitor-check-icon"><Check /></el-icon>
              <span v-else class="monitor-empty">-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Close, EditPen } from '@element-plus/icons-vue'
import MainLayout from '../layouts/MainLayout.vue'
import {
  apiDataSaveThresholds,
  apiDataThresholds,
} from '../api/dataApi'
import { formatTableCellValue } from '../utils/tableFormat'

const monitoredOnly = ref(false)
const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const editingKey = ref(null)
const editingDraft = ref({})
const originalDraft = ref({})

async function load() {
  loading.value = true
  try {
    const thresholdRes = await apiDataThresholds(monitoredOnly.value)

    if (thresholdRes.code !== 0) {
      throw new Error(thresholdRes.message || '阈值数据加载失败')
    }

    const thresholdItems = thresholdRes.data.items || []

    rows.value = thresholdItems.map((item) => ({
      ...item,
      unit: item.unit || '',
    }))
    cancelEdit()
  } catch (e) {
    rows.value = []
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function isRowEditing(row) {
  return row?.parameter_name === editingKey.value
}

function startEdit(row) {
  if (!row?.parameter_name) return
  editingKey.value = row.parameter_name
  editingDraft.value = { ...row }
  originalDraft.value = { ...row }
}

function cancelEdit() {
  editingKey.value = null
  editingDraft.value = {}
  originalDraft.value = {}
}

function buildUpdatePayload() {
  const payload = {}
  const fields = ['warning_lower', 'warning_upper', 'critical_lower', 'critical_upper', 'is_monitored']

  for (const field of fields) {
    const nextValue = editingDraft.value[field]
    const prevValue = originalDraft.value[field]

    if (field === 'is_monitored') {
      if (!!nextValue !== !!prevValue) {
        payload[field] = !!nextValue
      }
      continue
    }

    if (String(nextValue ?? '') !== String(prevValue ?? '')) {
      payload[field] = nextValue
    }
  }

  return payload
}

async function confirmEdit(row) {
  if (!isRowEditing(row)) return

  const updates = buildUpdatePayload()
  if (!Object.keys(updates).length) {
    cancelEdit()
    return
  }

  saving.value = true
  try {
    const thresholdPayload = [{
      parameter_name: row.parameter_name,
      ...updates,
    }]
    const thresholdRes = await apiDataSaveThresholds(thresholdPayload)

    if (thresholdRes.code !== 0) {
      throw new Error(thresholdRes.message || '阈值保存失败')
    }

    ElMessage.success('修改已保存')
    cancelEdit()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function formatThresholdValue(value) {
  return formatTableCellValue(value, 4, '-')
}

onMounted(load)
</script>

<style scoped>
.data-preview-card {
  padding: 14px;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.policy-tip {
  color: var(--muted);
  font-size: 12px;
}

.table-wrap {
  flex: 1;
  min-height: 0;
}

.preview-table {
  width: 100%;
}

.op-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.icon-action {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface-soft);
  color: var(--text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
}

.icon-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.icon-action-success {
  color: #1e9c5e;
  border-color: color-mix(in srgb, #1e9c5e 45%, var(--border));
}

.icon-action-danger {
  color: #d64545;
  border-color: color-mix(in srgb, #d64545 45%, var(--border));
}

.monitor-check-icon {
  color: #1e9c5e;
  font-size: 16px;
}

.monitor-empty {
  color: var(--muted);
}
</style>
