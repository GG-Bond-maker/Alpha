import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Global Error Handler]:', err, info)
}

window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Promise Rejection]:', event.reason)
})

app.mount('#app')

