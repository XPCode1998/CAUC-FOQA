<template>
  <MainLayout>
    <template #topbar-actions>
      <div class="topbar-actions">
        <DataQarIdPickerDialog v-model="qarId" @search="load" />
      </div>
    </template>

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
                  <button class="icon-action icon-action-success" :disabled="isSavingRow" @click="confirmEdit(row)" title="确认修改">
                    <el-icon><Check /></el-icon>
                  </button>
                  <button class="icon-action icon-action-danger" :disabled="isSavingRow" @click="cancelEdit" title="取消修改">
                    <el-icon><Close /></el-icon>
                  </button>
                </template>
                <template v-else>
                  <button class="icon-action" :disabled="editingRowId !== null" @click="startEdit(row)" title="编辑">
                    <el-icon><EditPen /></el-icon>
                  </button>
                </template>
              </div>
            </template>
          </el-table-column>

          <el-table-column
            v-for="field in fields"
            :key="field"
            :prop="field"
            :label="field"
            :min-width="140"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <el-input
                v-if="isRowEditing(row) && isFieldEditable(field)"
                v-model="editingDraft[field]"
                size="small"
                clearable
              />
              <span v-else>{{ formatCellValue(isRowEditing(row) ? editingDraft[field] : row[field]) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="table-footer">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Close, EditPen } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import DataQarIdPickerDialog from '../components/DataQarIdPickerDialog.vue'
import { apiDataPreview, apiDataPreviewUpdate } from '../api/dataApi'
import { formatTableCellValue } from '../utils/tableFormat'
import { getQarPageCache, setQarPageCache } from '../utils/qarPageCache'

const route = useRoute()
const qarId = ref('')
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const fields = ref([])
const rows = ref([])
const loading = ref(false)
const readonlyFields = ref(['id', 'created_at', 'updated_at'])
const editableFields = ref([])
const editingRowId = ref(null)
const editingDraft = ref({})
const originalDraft = ref({})
const isSavingRow = ref(false)

function isRowEditing(row) {
  return row?.id === editingRowId.value
}

function isFieldEditable(field) {
  if (Array.isArray(editableFields.value) && editableFields.value.length) {
    return editableFields.value.includes(field)
  }
  return !readonlyFields.value.includes(field)
}

function formatCellValue(value) {
  return formatTableCellValue(value, 4, '-')
}

function startEdit(row) {
  if (!row || row.id === undefined || row.id === null) return
  editingRowId.value = row.id
  editingDraft.value = { ...row }
  originalDraft.value = { ...row }
}

function cancelEdit() {
  editingRowId.value = null
  editingDraft.value = {}
  originalDraft.value = {}
}

function buildUpdatePayload() {
  const payload = {}
  for (const field of fields.value) {
    if (!isFieldEditable(field)) continue
    const nextValue = editingDraft.value[field]
    const prevValue = originalDraft.value[field]
    if (nextValue !== prevValue) {
      payload[field] = nextValue
    }
  }
  return payload
}

async function confirmEdit(row) {
  if (!isRowEditing(row) || isSavingRow.value) return

  const updates = buildUpdatePayload()
  if (!Object.keys(updates).length) {
    cancelEdit()
    return
  }

  isSavingRow.value = true
  try {
    const res = await apiDataPreviewUpdate({
      id: row.id,
      updates,
    })

    if (res.code !== 0) {
      throw new Error(res.message || '保存失败')
    }

    const nextRow = res?.data?.row
    if (nextRow && nextRow.id !== undefined) {
      const rowIndex = rows.value.findIndex((item) => item.id === nextRow.id)
      if (rowIndex >= 0) {
        rows.value[rowIndex] = nextRow
      }
    }

    ElMessage.success('修改已保存')
    cancelEdit()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    isSavingRow.value = false
  }
}

function syncQarIdFromRoute() {
  const queryQarId = String(route.query?.qar_id || '').trim()
  if (queryQarId && queryQarId !== qarId.value) {
    qarId.value = queryQarId
    page.value = 1
  }
}

async function load() {
  const normalizedQarId = String(qarId.value || '').trim()
  const cacheVariant = `${page.value}:${pageSize.value}`
  const cached = getQarPageCache('data-preview', normalizedQarId || '_default', cacheVariant)
  if (cached) {
    total.value = cached.total || 0
    fields.value = cached.fields || []
    rows.value = cached.rows || []
    readonlyFields.value = Array.isArray(cached.readonly_fields)
      ? cached.readonly_fields
      : ['id', 'created_at', 'updated_at']
    editableFields.value = Array.isArray(cached.editable_fields)
      ? cached.editable_fields
      : []
  }

  loading.value = true
  cancelEdit()
  try {
    const res = await apiDataPreview({ qar_id: qarId.value, page: page.value, page_size: pageSize.value })
    if (res.code === 0) {
      total.value = res.data.total
      fields.value = res.data.fields
      rows.value = res.data.rows
      readonlyFields.value = Array.isArray(res.data.readonly_fields)
        ? res.data.readonly_fields
        : ['id', 'created_at', 'updated_at']
      editableFields.value = Array.isArray(res.data.editable_fields)
        ? res.data.editable_fields
        : []

      setQarPageCache('data-preview', normalizedQarId || '_default', cacheVariant, {
        total: total.value,
        fields: fields.value,
        rows: rows.value,
        readonly_fields: readonlyFields.value,
        editable_fields: editableFields.value,
      })
    } else {
      rows.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

function handlePageChange(nextPage) {
  page.value = nextPage
  load()
}

function handlePageSizeChange(nextSize) {
  pageSize.value = nextSize
  page.value = 1
  load()
}

onMounted(() => {
  syncQarIdFromRoute()
  load()
})

watch(
  () => route.query?.qar_id,
  () => {
    syncQarIdFromRoute()
    load()
  },
)

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

.table-wrap {
  flex: 1;
  min-height: 0;
}

.preview-table {
  width: 100%;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
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
</style>
