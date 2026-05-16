import { defineStore } from 'pinia'

const DATA_QAR_CURRENT_ID_KEY = 'data_qar_current_id'

function normalizeQarId(value) {
  return String(value || '').trim()
}

function readPersistedQarId() {
  try {
    return normalizeQarId(localStorage.getItem(DATA_QAR_CURRENT_ID_KEY))
  } catch (_) {
    return ''
  }
}

export const useDataQarContextStore = defineStore('dataQarContext', {
  state: () => ({
    currentQarId: readPersistedQarId(),
  }),
  actions: {
    setCurrentQarId(value) {
      const next = normalizeQarId(value)
      this.currentQarId = next
      try {
        if (next) {
          localStorage.setItem(DATA_QAR_CURRENT_ID_KEY, next)
        } else {
          localStorage.removeItem(DATA_QAR_CURRENT_ID_KEY)
        }
      } catch (_) {
        // Ignore persistence errors in private mode or restricted environments.
      }
    },
    clearCurrentQarId() {
      this.setCurrentQarId('')
    },
  },
})
