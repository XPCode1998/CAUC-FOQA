import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as Cesium from 'cesium'
import App from './App.vue'
import router from './router'
import './styles.css'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import 'element-plus/dist/index.css'

const cesiumIonToken = import.meta.env.VITE_CESIUM_ION_TOKEN
if (cesiumIonToken) {
	Cesium.Ion.defaultAccessToken = cesiumIonToken
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
