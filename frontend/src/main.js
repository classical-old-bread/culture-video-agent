// Vue 的 createApp 负责把根组件挂载到 index.html 的 #app 节点。
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
