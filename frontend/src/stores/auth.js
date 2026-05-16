import { defineStore } from 'pinia'
import { apiLogin, apiMe, apiRegister, apiResetPassword } from '../api/authApi'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    initialized: false,
  }),
  getters: {
    isAuthed: (state) => !!state.user,
  },
  actions: {
    async login(username, password) {
      const res = await apiLogin({ username, password })
      if (res.code !== 0) {
        throw new Error(res.message || '登录失败')
      }
      localStorage.setItem('access_token', res.data.access)
      localStorage.setItem('refresh_token', res.data.refresh)
      this.user = res.data.user
    },
    async register(username, password) {
      const res = await apiRegister({ username, password })
      if (res.code !== 0) {
        throw new Error(res.message || '注册失败')
      }
      localStorage.setItem('access_token', res.data.access)
      localStorage.setItem('refresh_token', res.data.refresh)
      this.user = res.data.user
    },
    async resetPassword(username, newPassword) {
      const res = await apiResetPassword({
        username,
        new_password: newPassword,
      })
      if (res.code !== 0) {
        throw new Error(res.message || '密码重设失败')
      }
      return res
    },
    async bootstrap() {
      if (this.initialized) return
      this.initialized = true
      const token = localStorage.getItem('access_token')
      if (!token) return
      try {
        const res = await apiMe()
        if (res.code === 0) {
          this.user = res.data
        }
      } catch (_) {
        this.logout()
      }
    },
    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
    },
  },
})
