import { resolve } from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Порты берём из корневого .env — он общий для фронта и бэка (см. .env.example)
const ROOT_DIR = resolve(import.meta.dirname, '..')

export default defineConfig(({ mode }) => {
  // Пустой префикс: нужные переменные не VITE_*, в клиентский бандл они не попадают
  const env = loadEnv(mode, ROOT_DIR, '')
  const webPort = Number(env.WEB_PORT) || 5173
  const apiPort = Number(env.UVICORN_PORT) || 8000

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: webPort,
      // Фронт ходит по относительному /api, чтобы не настраивать CORS в проде
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
