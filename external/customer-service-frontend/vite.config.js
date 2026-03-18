import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
      '/commerce': {
        target: 'http://127.0.0.1:18081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/commerce/, ''),
      },
      '/health': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
      // WebSocket 实时对话 / 数字人对话通道
      '/ws': {
        target: 'ws://127.0.0.1:18082',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    // 现代浏览器目标，启用 esbuild 压缩（默认开启，这里显式声明意图）
    target: 'es2020',
    // 为 Vue 单文件组件的样式独立分包，便于缓存
    cssCodeSplit: true,
    // 业务代码更新频繁，Vue 框架本身极少变动；
    // 把 vue 单独拆包后，业务迭代不会让框架包失效，命中缓存、减少重复下载
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue'],
        },
      },
    },
    // 适度放宽警告阈值，避免大型单页（含数字人 SDK 异步分包）触发无意义告警
    chunkSizeWarningLimit: 1500,
  },
})
