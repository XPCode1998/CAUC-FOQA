import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cesium from 'vite-plugin-cesium'

export default defineConfig({
  plugins: [vue(), cesium()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('/cesium/')) return 'cesium'
          if (id.includes('/echarts-gl/')) return 'echarts-gl'
          if (id.includes('/echarts/')) return 'echarts'
          if (id.includes('/vue-router/')) return 'vue-router'
          if (id.includes('/pinia/')) return 'pinia'
          if (id.includes('/axios/')) return 'axios'
          if (id.includes('/vue/')) return 'vue'

          return 'vendor'
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
