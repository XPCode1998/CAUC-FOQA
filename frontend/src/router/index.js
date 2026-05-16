import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const LoginView = () => import('../views/LoginView.vue')
const FlightVisualizationView = () => import('../views/FlightVisualizationView.vue')
const FlightReplayView = () => import('../views/FlightReplayView.vue')
const DataPreviewView = () => import('../views/DataPreviewView.vue')
const DataManagementView = () => import('../views/DataManagementView.vue')
const FlightRiskOverlimitView = () => import('../views/FlightRiskOverlimitView.vue')
const FlightRiskWarningView = () => import('../views/FlightRiskWarningView.vue')
const DataThresholdsView = () => import('../views/DataThresholdsView.vue')
const DataImputationView = () => import('../views/DataImputationView.vue')
const DataImputationTrainingView = () => import('../views/DataImputationTrainingView.vue')
const SystemMetricsView = () => import('../views/SystemMetricsView.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/register', name: 'register', component: LoginView },
    { path: '/reset-password', name: 'reset-password', component: LoginView },
    { path: '/', redirect: '/data/management' },
    { path: '/data/management', name: 'data-management', component: DataManagementView, meta: { auth: true } },
    { path: '/data/preview', name: 'data-preview', component: DataPreviewView, meta: { auth: true } },
    { path: '/data/thresholds', name: 'data-thresholds', component: DataThresholdsView, meta: { auth: true } },
    { path: '/flight/visualization', name: 'flight-visualization', component: FlightVisualizationView, meta: { auth: true } },
    { path: '/flight/replay', name: 'flight-replay', component: FlightReplayView, meta: { auth: true } },
    { path: '/flight/risk/overlimit', name: 'flight-risk-overlimit', component: FlightRiskOverlimitView, meta: { auth: true } },
    { path: '/flight/risk/warning', name: 'flight-risk-warning', component: FlightRiskWarningView, meta: { auth: true } },
    { path: '/data/imputation', name: 'data-imputation', component: DataImputationView, meta: { auth: true } },
    { path: '/data/imputation/training', name: 'data-imputation-training', component: DataImputationTrainingView, meta: { auth: true } },
    { path: '/system/metrics', name: 'system-metrics', component: SystemMetricsView, meta: { auth: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  if (to.meta.auth && !auth.isAuthed) {
    return { name: 'login' }
  }
  if (['login', 'register', 'reset-password'].includes(String(to.name)) && auth.isAuthed) {
    return { name: 'data-management' }
  }
  return true
})

export default router
