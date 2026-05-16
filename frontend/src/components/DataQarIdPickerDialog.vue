<template>
  <div class="control-row">
    <input
      class="input input-w-md"
      :value="modelValue"
      placeholder="QAR ID"
      readonly
      @click="openDialog"
    />
    <button class="btn btn-primary" @click="onSearch">选择</button>

    <teleport to="body">
      <div v-if="visible" class="qar-dialog-mask" @click="closeDialog">
        <div class="qar-dialog" @click.stop>
          <div class="qar-dialog-header">
            <h4 class="dialog-title">选择 QAR ID</h4>
            <button class="icon-btn icon-btn-close" type="button" @click="closeDialog" aria-label="关闭" title="关闭">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18.3 5.71a1 1 0 0 0-1.42 0L12 10.59 7.12 5.7A1 1 0 0 0 5.7 7.13L10.58 12l-4.9 4.88a1 1 0 0 0 1.43 1.42L12 13.41l4.88 4.89a1 1 0 0 0 1.42-1.43L13.41 12l4.89-4.88a1 1 0 0 0 0-1.41z" />
              </svg>
            </button>
          </div>

          <div class="qar-dialog-search">
            <input
              class="input"
              v-model.trim="keyword"
              placeholder="输入关键字筛选"
              @keyup.enter="fetchIds"
            />
            <button
              class="icon-btn icon-btn-search"
              type="button"
              @click="fetchIds"
              :disabled="loading"
              aria-label="搜索"
              title="搜索"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M10.5 3a7.5 7.5 0 1 0 4.67 13.38l4.22 4.22a1 1 0 0 0 1.41-1.41l-4.22-4.22A7.5 7.5 0 0 0 10.5 3zm0 2a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11z" />
              </svg>
            </button>
          </div>

          <div class="qar-dialog-list card">
            <div v-if="loading" class="list-placeholder">加载中...</div>
            <div v-else-if="!items.length" class="list-placeholder">未找到可用 QAR ID</div>
            <label
              v-else
              v-for="id in items"
              :key="id"
              class="qar-dialog-item"
            >
              <input type="radio" name="qar-id-select" :value="id" v-model="selected" />
              <span>{{ id }}</span>
            </label>
          </div>

          <div class="qar-dialog-actions">
            <button class="btn btn-ghost" @click="closeDialog">取消</button>
            <button class="btn btn-primary" :disabled="!selected" @click="confirmSelect">确认</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { apiDataQarIds } from '../api/dataApi'
import { useDataQarContextStore } from '../stores/dataQarContext'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'search'])
const qarContextStore = useDataQarContextStore()

const visible = ref(false)
const loading = ref(false)
const keyword = ref('')
const items = ref([])
const selected = ref('')

watch(
  () => props.modelValue,
  (v) => {
    const normalized = String(v || '').trim()
    selected.value = normalized
    if (normalized) {
      qarContextStore.setCurrentQarId(normalized)
      return
    }

    if (qarContextStore.currentQarId && qarContextStore.currentQarId !== normalized) {
      emit('update:modelValue', qarContextStore.currentQarId)
      emit('search', qarContextStore.currentQarId)
    }
  },
  { immediate: true }
)

async function fetchIds() {
  loading.value = true
  try {
    const res = await apiDataQarIds({ q: keyword.value, limit: 500 })
    items.value = Array.isArray(res?.data?.items) ? res.data.items : []
    if (!selected.value && items.value.length) {
      selected.value = items.value[0]
    }
  } catch (_) {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function openDialog() {
  visible.value = true
  selected.value = props.modelValue || ''
  await fetchIds()
}

function closeDialog() {
  visible.value = false
}

function confirmSelect() {
  if (!selected.value) return
  qarContextStore.setCurrentQarId(selected.value)
  emit('update:modelValue', selected.value)
  visible.value = false
}

function onSearch() {
  const normalized = String(props.modelValue || '').trim()
  if (normalized) {
    qarContextStore.setCurrentQarId(normalized)
  }
  emit('search', props.modelValue)
}
</script>

<style scoped>
.qar-dialog-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--overlay-loading-bg) 90%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 1000;
}

.qar-dialog {
  width: min(680px, 100%);
  max-height: min(80vh, 780px);
  background: var(--glass-bg-strong);
  border: 0;
  border-radius: 16px;
  padding: 14px;
  display: grid;
  gap: 12px;
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.qar-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dialog-title {
  margin: 0;
}

.qar-dialog-search {
  --search-control-height: 42px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.qar-dialog-search .input {
  height: var(--search-control-height);
  box-sizing: border-box;
  border: 1px solid color-mix(in srgb, #81ecff 34%, var(--surface-soft));
}

.qar-dialog-list {
  overflow: auto;
  max-height: 46vh;
  padding: 8px;
  background: color-mix(in srgb, var(--glass-bg) 76%, transparent);
  border: 0;
  backdrop-filter: blur(20px) saturate(125%);
  -webkit-backdrop-filter: blur(20px) saturate(125%);
}

.qar-dialog-search .input:focus,
.qar-dialog-search .input:focus-visible {
  border-color: #81ecff;
  box-shadow: 0 0 0 2px color-mix(in srgb, #81ecff 20%, transparent);
}

.qar-dialog-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
}

.qar-dialog-item:hover {
  background: var(--surface-hover);
}

.list-placeholder {
  padding: 12px;
  color: var(--muted);
}

.qar-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: var(--surface-soft);
  color: var(--brand);
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.icon-btn svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.icon-btn-close {
  width: 34px;
  height: 34px;
  border-radius: 999px;
}

.icon-btn-close:hover {
  background: var(--surface-hover);
}

.icon-btn-search {
  width: 42px;
  height: var(--search-control-height);
  border-radius: 12px;
}

.icon-btn-search:hover {
  background: var(--surface-hover);
}
</style>
