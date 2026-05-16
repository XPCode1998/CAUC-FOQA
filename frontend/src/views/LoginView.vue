<template>
  <div class="auth-page">
    <div class="auth-shell">
      <div class="auth-visual-panel">
        <img class="auth-visual" src="/auth-visual.svg" alt="系统认证视觉图" />
      </div>

      <div class="auth-panel">
        <div class="auth-panel-head">
          <div class="auth-system-name">CAUC FOQA</div>
          <h2 class="auth-panel-title">{{ panelTitle }}</h2>
          <p class="auth-panel-subtitle">{{ panelSubtitle }}</p>
        </div>

        <div class="auth-form grid">
          <input v-model.trim="username" class="input" placeholder="用户名" @keyup.enter="handleSubmit" />

          <input
            v-model="password"
            class="input"
            :placeholder="mode === 'reset' ? '新密码' : '密码'"
            type="password"
            @keyup.enter="handleSubmit"
          />

          <input
            v-if="mode !== 'login'"
            v-model="confirmPassword"
            class="input"
            :placeholder="mode === 'reset' ? '确认新密码' : '确认密码'"
            type="password"
            @keyup.enter="handleSubmit"
          />

          <div class="auth-links-row" :class="`mode-${mode}`">
            <template v-if="mode === 'login'">
              <RouterLink class="auth-link" :to="{ name: 'register' }">还没有账号？去注册</RouterLink>
              <RouterLink class="auth-link" :to="{ name: 'reset-password' }">忘记密码？</RouterLink>
            </template>
            <template v-else-if="mode === 'register'">
              <RouterLink class="auth-link" :to="{ name: 'login' }">已有账号？去登录</RouterLink>
            </template>
            <template v-else>
              <RouterLink class="auth-link" :to="{ name: 'register' }">还没有账号？去注册</RouterLink>
              <RouterLink class="auth-link" :to="{ name: 'login' }">登录</RouterLink>
            </template>
          </div>

          <button class="btn btn-primary" @click="handleSubmit" :disabled="loading">
            {{ loading ? loadingText : submitText }}
          </button>
        </div>

        <p v-if="feedback" class="auth-feedback" :class="{ error: isError, success: !isError }">{{ feedback }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const feedback = ref('')
const isError = ref(false)

const mode = computed(() => {
  if (route.name === 'register') return 'register'
  if (route.name === 'reset-password') return 'reset'
  return 'login'
})

const panelTitle = computed(() => (mode.value === 'register' ? '注册' : mode.value === 'reset' ? '重置密码' : '登录'))

const panelSubtitle = computed(() => {
  if (mode.value === 'register') return '创建账户后可直接进入平台'
  if (mode.value === 'reset') return '输入用户名并设置新密码'
  return '输入用户名与密码进入系统'
})

const submitText = computed(() => {
  if (mode.value === 'register') return '注册并进入系统'
  if (mode.value === 'reset') return '确认重设'
  return '登录'
})

const loadingText = computed(() => {
  if (mode.value === 'register') return '注册中...'
  if (mode.value === 'reset') return '重设中...'
  return '登录中...'
})

function extractApiErrorMessage(e, fallback) {
  return e?.response?.data?.message || e?.message || fallback
}

function clearSensitiveFields() {
  password.value = ''
  confirmPassword.value = ''
}

function goMode(nextMode) {
  const name = nextMode === 'register' ? 'register' : nextMode === 'reset' ? 'reset-password' : 'login'
  if (route.name === name) return
  feedback.value = ''
  isError.value = false
  clearSensitiveFields()
  router.push({ name })
}

watch(mode, () => {
  feedback.value = ''
  isError.value = false
  clearSensitiveFields()
})

async function handleSubmit() {
  feedback.value = ''
  isError.value = false

  if (!username.value) {
    feedback.value = '请输入用户名'
    isError.value = true
    return
  }

  if (mode.value === 'reset') {
    if (!password.value || !confirmPassword.value) {
      feedback.value = '请完整填写新密码和确认密码'
      isError.value = true
      return
    }
    if (password.value !== confirmPassword.value) {
      feedback.value = '两次输入的新密码不一致'
      isError.value = true
      return
    }
  } else {
    if (!password.value) {
      feedback.value = '请输入密码'
      isError.value = true
      return
    }
    if (mode.value === 'register' && password.value !== confirmPassword.value) {
      feedback.value = '两次输入的密码不一致'
      isError.value = true
      return
    }
  }

  loading.value = true
  try {
    if (mode.value === 'register') {
      await auth.register(username.value, password.value)
      router.push({ name: 'data-management' })
      return
    }

    if (mode.value === 'reset') {
      await auth.resetPassword(username.value, password.value)
      feedback.value = '密码重设成功，请使用新密码登录'
      isError.value = false
      clearSensitiveFields()
      router.push({ name: 'login' })
      return
    }

    await auth.login(username.value, password.value)
    router.push({ name: 'data-management' })
  } catch (e) {
    feedback.value = extractApiErrorMessage(
      e,
      mode.value === 'register' ? '注册失败' : mode.value === 'reset' ? '重设失败' : '登录失败'
    )
    isError.value = true
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  width: 100%;
  min-height: 100vh;
  background: var(--bg);
  --auth-primary: #00b4d8;
  --auth-secondary: #487f89;
  --auth-tertiary: #fec931;
  --auth-neutral: #f8fafc;
  --auth-text: #1f2b31;
}

.auth-shell {
  width: 100%;
  min-height: 100vh;
  display: grid;
  grid-template-columns: 2fr 3fr;
  gap: 0;
  padding: 0;
  overflow: hidden;
}

.auth-visual-panel {
  min-height: 100vh;
  background: color-mix(in srgb, var(--surface-soft) 80%, transparent);
}

.auth-visual {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.auth-panel {
  background: var(--panel);
  padding: 34px 30px;
  min-height: 100vh;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 14px;
}

.auth-panel-head,
.auth-form,
.auth-feedback {
  width: 60%;
}

.auth-panel-head {
  display: grid;
  gap: 8px;
}

.auth-system-name {
  font-size: 16px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--brand-2);
  font-weight: 700;
}

.auth-panel-title {
  margin: 0;
  font-size: 30px;
  line-height: 1.25;
  font-family: var(--font-display);
}

.auth-panel-subtitle {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}

.auth-form {
  gap: 12px;
}

.auth-form .input {
  min-height: 50px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--auth-secondary) 26%, #d2dbe2);
  background: var(--auth-neutral);
  color: var(--auth-text);
}

.auth-form .input::placeholder {
  color: color-mix(in srgb, var(--auth-secondary) 72%, #8f9aa3);
}

.auth-form .input:focus,
.auth-form .input:focus-visible {
  border-color: var(--auth-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--auth-primary) 24%, transparent);
}

.auth-form .input:-webkit-autofill,
.auth-form .input:-webkit-autofill:hover,
.auth-form .input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--auth-text);
  box-shadow: 0 0 0 1000px var(--auth-neutral) inset;
  border: 1px solid color-mix(in srgb, var(--auth-secondary) 26%, #d2dbe2);
}

.auth-form .btn-primary {
  min-height: 52px;
  border-radius: 12px;
  border: 0;
  background: linear-gradient(135deg, var(--auth-primary) 0%, color-mix(in srgb, var(--auth-primary) 78%, #6dd8ee 22%) 100%);
  color: #ffffff;
  font-weight: 700;
}

.auth-form .btn-primary:hover {
  filter: brightness(0.97);
}

.auth-form .btn-primary:focus-visible {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--auth-primary) 28%, transparent);
}

.auth-links-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  min-height: 20px;
}

.auth-links-row.mode-reset {
  justify-content: space-between;
}

.auth-links-row.mode-login {
  justify-content: space-between;
}

.auth-link {
  font-size: 13px;
  color: var(--auth-primary);
  text-decoration: none;
}

.auth-link:hover {
  color: var(--auth-secondary);
  text-decoration: underline;
}

.auth-feedback {
  margin: 0;
  font-size: 13px;
}

.auth-feedback.error {
  color: var(--danger);
}

.auth-feedback.success {
  color: color-mix(in srgb, var(--brand-2) 70%, var(--text));
}

@media (max-width: 920px) {
  .auth-shell {
    grid-template-columns: 1fr;
    min-height: 100vh;
  }

  .auth-visual-panel {
    min-height: 34vh;
  }

  .auth-panel {
    padding: 16px;
    min-height: 66vh;
    justify-items: stretch;
  }

  .auth-panel-head,
  .auth-form,
  .auth-feedback {
    width: 100%;
  }
}

@media (max-width: 560px) {
  .auth-panel-title {
    font-size: 26px;
  }

  .auth-links-row {
    flex-wrap: wrap;
  }
}
</style>
