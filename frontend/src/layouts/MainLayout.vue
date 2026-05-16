<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <h2 class="brand-title">CAUC FOQA</h2>
        <div class="brand-subtitle">QAR数据采集分析管理平台</div>
      </div>

      <nav class="sidebar-nav">
        <section v-for="group in menuGroups" :key="group.title" class="menu-group">
          <h3 class="menu-title">{{ group.title }}</h3>
          <ul class="menu-list">
            <li v-for="item in group.items" :key="item.label">
              <RouterLink
                v-if="item.to"
                :to="item.to"
                class="menu-link"
                :class="{ active: route.path === item.to }"
              >
                <span class="menu-link-main">
                  <span class="material-symbols-outlined menu-icon" aria-hidden="true">{{ item.icon }}</span>
                  <span>{{ item.label }}</span>
                </span>
              </RouterLink>
              <span v-else class="menu-link disabled">
                <span class="menu-link-main">
                  <span class="material-symbols-outlined menu-icon" aria-hidden="true">{{ item.icon }}</span>
                  <span>{{ item.label }}</span>
                </span>
                <span class="menu-badge">规划中</span>
              </span>
            </li>
          </ul>
        </section>
      </nav>

      <div class="sidebar-user" ref="userCardRef">
        <button class="sidebar-user-trigger" type="button" @click.stop="toggleUserMenu">
          <div class="sidebar-user-avatar">{{ userInitials }}</div>
          <div class="sidebar-user-meta">
            <div class="sidebar-user-name">{{ userDisplayName }}</div>
            <div class="sidebar-user-plan">Plus</div>
          </div>
          <div class="sidebar-user-arrow">{{ isUserMenuOpen ? '▴' : '▾' }}</div>
        </button>

        <div v-if="isUserMenuOpen" class="sidebar-user-menu">
          <button class="sidebar-user-menu-item" type="button" @click="openSettings">设置</button>
          <button class="sidebar-user-menu-item danger" type="button" @click="logout">退出登录</button>
        </div>
      </div>
    </aside>

    <main class="content-area">
      <div class="card topbar">
        <div class="topbar-inner">
          <div class="topbar-title-wrap">
            <div class="section-title">{{ currentMenuLabel }}</div>
          </div>
          <div class="topbar-actions-wrap">
            <slot name="topbar-actions" />
          </div>
        </div>
      </div>

      <div class="page-content">
        <slot />
      </div>
    </main>

    <teleport to="body">
      <div v-if="settingsVisible" class="settings-mask" @click="closeSettings">
        <div class="settings-dialog card" @click.stop>
          <div class="settings-header">
            <h3 class="settings-title">设置</h3>
            <button class="icon-btn icon-btn-close" type="button" @click="closeSettings" aria-label="关闭" title="关闭">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18.3 5.71a1 1 0 0 0-1.42 0L12 10.59 7.12 5.7A1 1 0 0 0 5.7 7.13L10.58 12l-4.9 4.88a1 1 0 0 0 1.43 1.42L12 13.41l4.88 4.89a1 1 0 0 0 1.42-1.43L13.41 12l4.89-4.88a1 1 0 0 0 0-1.41z" />
              </svg>
            </button>
          </div>

          <div class="settings-grid">
            <label class="settings-item">
              <span>外观</span>
              <select class="input" v-model="appearance">
                <option value="dark">暗黑</option>
                <option value="light">亮白</option>
              </select>
            </label>

            <label class="settings-item">
              <span>语言</span>
              <select class="input" v-model="language">
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
            </label>

            <div class="settings-item static">
              <span>系统版本</span>
              <div class="settings-value">CAUC FOQA v1.0.0</div>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const settingsVisible = ref(false)
const isUserMenuOpen = ref(false)
const userCardRef = ref(null)
const appearance = ref(normalizeAppearance(localStorage.getItem('app_appearance')))
const language = ref(localStorage.getItem('app_language') || 'zh-CN')
const DARK_THEME_CLASS = 'theme-one-dark'

function normalizeAppearance(value) {
  return value === 'light' ? 'light' : 'dark'
}

const menuGroups = [
  {
    title: 'QAR 数据管理',
    items: [
      { label: '数据管理', to: '/data/management', icon: 'database' },
      { label: '数据预览', to: '/data/preview', icon: 'visibility' },
      { label: '参数管理', to: '/data/thresholds', icon: 'settings_input_component' },
    ],
  },
  {
    title: 'QAR 数据可视化',
    items: [
      { label: '飞行参数可视化', to: '/flight/visualization', icon: 'insights' },
      { label: '飞行过程回放', to: '/flight/replay', icon: 'flight_takeoff' },
    ],
  },
  {
    title: '飞行风险监测',
    items: [
      { label: 'QAR超限分析', to: '/flight/risk/overlimit', icon: 'warning' },
      { label: '飞行风险预警', to: '/flight/risk/warning', icon: 'notification_important' },
    ],
  },
  {
    title: 'QAR质量管理',
    items: [
      { label: '模型训练管理', to: '/data/imputation/training', icon: 'model_training' },
      { label: 'QAR缺失值填充', to: '/data/imputation', icon: 'format_color_fill' },
    ],
  },
  {
    title: '系统性能与运维',
    items: [
      { label: '系统性能与运维', to: '/system/metrics', icon: 'monitoring' },
    ],
  },
]

const currentMenuLabel = computed(() => {
  for (const group of menuGroups) {
    for (const item of group.items) {
      if (item.to === route.path) return item.label
    }
  }
  return '平台首页'
})

const userDisplayName = computed(() => {
  const user = auth.user || {}
  return user.nickname || user.username || '用户'
})

const userInitials = computed(() => {
  const name = userDisplayName.value
  if (!name) return 'U'
  return String(name).trim().slice(0, 1).toUpperCase()
})

function toggleUserMenu() {
  isUserMenuOpen.value = !isUserMenuOpen.value
}

function openSettings() {
  isUserMenuOpen.value = false
  settingsVisible.value = true
}

function closeSettings() {
  settingsVisible.value = false
}

function logout() {
  isUserMenuOpen.value = false
  auth.logout()
  router.push({ name: 'login' })
}

function applyAppearanceTheme() {
  const root = document.documentElement
  const useDark = appearance.value === 'dark'
  root.classList.toggle(DARK_THEME_CLASS, useDark)
}

function handleGlobalClick(event) {
  if (!isUserMenuOpen.value) return
  const root = userCardRef.value
  if (!root) return
  if (!root.contains(event.target)) {
    isUserMenuOpen.value = false
  }
}

watch(appearance, (v) => {
  const normalized = normalizeAppearance(v)
  if (appearance.value !== normalized) {
    appearance.value = normalized
    return
  }
  localStorage.setItem('app_appearance', normalized)
  applyAppearanceTheme()
})

watch(language, (v) => {
  localStorage.setItem('app_language', v)
})

onMounted(() => {
  applyAppearanceTheme()
  document.addEventListener('click', handleGlobalClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleGlobalClick)
})
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.brand-title {
  margin: 0;
  font-size: 20px;
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: -0.02em;
}

.brand-subtitle {
  color: var(--brand);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-weight: 600;
  margin-top: 4px;
}

.topbar-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.topbar-title-wrap {
  min-width: 0;
}

.topbar-actions-wrap {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.sidebar-nav {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 18px;
  align-content: start;
}

.menu-link-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.menu-icon {
  font-size: 18px;
  color: color-mix(in srgb, var(--muted) 84%, transparent);
  transition: color 0.2s ease-in-out;
}

.menu-link:hover .menu-icon {
  color: color-mix(in srgb, var(--text) 86%, transparent);
}

.menu-link.active .menu-icon {
  color: var(--brand);
}

.sidebar-user {
  margin-top: auto;
  position: relative;
  padding: 14px 8px 0;
  border-top: 1px solid color-mix(in srgb, var(--border) 55%, transparent);
}

.sidebar-user-trigger {
  width: 100%;
  border: 1px solid color-mix(in srgb, var(--border) 65%, transparent);
  background: color-mix(in srgb, var(--surface-hover) 34%, transparent);
  color: var(--text);
  border-radius: 14px;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.sidebar-user-trigger:hover {
  background: color-mix(in srgb, var(--surface-hover) 54%, transparent);
}

.sidebar-user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--surface-hover) 70%, #2a3554 30%);
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
}

.sidebar-user-meta {
  min-width: 0;
  text-align: left;
  flex: 1;
}

.sidebar-user-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-user-plan {
  font-size: 10px;
  color: var(--brand);
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.sidebar-user-arrow {
  color: var(--muted);
  flex: 0 0 auto;
}

.sidebar-user-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 8px);
  background: var(--panel-elevated);
  border: 0;
  border-radius: 12px;
  box-shadow: none;
  padding: 6px;
  display: grid;
  gap: 4px;
  z-index: 20;
}

.sidebar-user-menu-item {
  border: 0;
  background: var(--surface-soft);
  color: var(--text);
  border-radius: 8px;
  text-align: left;
  padding: 8px 10px;
  cursor: pointer;
}

.sidebar-user-menu-item:hover {
  background: var(--surface-hover);
}

.sidebar-user-menu-item.danger {
  background: color-mix(in srgb, var(--danger) 18%, transparent);
  color: var(--danger);
}

.settings-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--overlay-loading-bg) 92%, transparent);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 1000;
}

.settings-dialog {
  width: min(400px, 100%);
  padding: 16px;
  display: grid;
  gap: 12px;
  background: var(--panel-elevated);
  border: 0;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.settings-title {
  margin: 0;
}

.settings-grid {
  display: grid;
  gap: 10px;
}

.settings-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  font-size: 13px;
}

.settings-item > span {
  flex: 0 0 auto;
  font-weight: 600;
}

.settings-item .input,
.settings-item .settings-value {
  width: min(260px, 52%);
}

.settings-item.static {
  border-radius: 10px;
  padding: 0;
}

.settings-value {
  border-radius: 10px;
  background: var(--surface-soft);
  padding: 10px 12px;
  color: var(--muted);
}
</style>
