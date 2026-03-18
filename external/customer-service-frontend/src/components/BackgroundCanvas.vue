<script setup>
// 背景粒子系统：纯展示层，不依赖任何聊天 / 数字人状态，生命周期自包含。
// 从 App.vue 抽出为独立组件，降低单体文件体积，并保持「切后台暂停动画」等优化。
import { onMounted, onUnmounted, ref } from 'vue'

const bgCanvas = ref(null)
let animFrameId = null
let bgParticles = []
const BG_PARTICLE_COUNT = 80
const BG_CONNECT_DIST = 150
const BG_MOUSE_RADIUS = 180
const bgMouse = { x: null, y: null }

function createBgParticles(w, h) {
  // 商务主题：蓝色为主 + 少量金色点缀，沉稳不抢内容
  const palette = [
    [30, 64, 140], [47, 111, 228], [74, 140, 255],
    [26, 36, 57], [201, 162, 39], [217, 164, 65],
  ]
  bgParticles = Array.from({ length: BG_PARTICLE_COUNT }, () => {
    const color = palette[Math.floor(Math.random() * palette.length)]
    return {
      x: Math.random() * w, y: Math.random() * h,
      size: Math.random() * 2.5 + 1,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      color, opacity: Math.random() * 0.45 + 0.12,
      phase: Math.random() * Math.PI * 2,
      pulse: Math.random() * 0.015 + 0.005,
    }
  })
}

function animateBg(ctx, w, h, time) {
  ctx.clearRect(0, 0, w, h)

  for (const p of bgParticles) {
    p.x += p.vx + Math.sin(time * 0.001 + p.phase) * 0.25
    p.y += p.vy + Math.cos(time * 0.001 + p.phase + 1) * 0.25

    if (bgMouse.x !== null) {
      const dx = p.x - bgMouse.x, dy = p.y - bgMouse.y
      const dist = Math.hypot(dx, dy)
      if (dist < BG_MOUSE_RADIUS) {
        const force = (BG_MOUSE_RADIUS - dist) / BG_MOUSE_RADIUS
        p.x += (dx / dist) * force * 0.7
        p.y += (dy / dist) * force * 0.7
      }
    }

    if (p.x < -20) p.x = w + 20; if (p.x > w + 20) p.x = -20
    if (p.y < -20) p.y = h + 20; if (p.y > h + 20) p.y = -20
  }

  // 连线
  ctx.lineWidth = 0.5
  for (let i = 0; i < bgParticles.length; i++) {
    for (let j = i + 1; j < bgParticles.length; j++) {
      const dx = bgParticles[i].x - bgParticles[j].x
      const dy = bgParticles[i].y - bgParticles[j].y
      const dist = Math.hypot(dx, dy)
      if (dist < BG_CONNECT_DIST) {
        const alpha = (1 - dist / BG_CONNECT_DIST) * 0.1
        // 蓝调连线，与商务主题对齐
        ctx.strokeStyle = `rgba(74,140,255,${alpha})`
        ctx.beginPath()
        ctx.moveTo(bgParticles[i].x, bgParticles[i].y)
        ctx.lineTo(bgParticles[j].x, bgParticles[j].y)
        ctx.stroke()
      }
    }
  }

  // 粒子光晕
  for (const p of bgParticles) {
    const pulse = 1 + Math.sin(time * p.pulse + p.phase) * 0.25
    const r = p.size * pulse
    const [cr, cg, cb] = p.color

    ctx.beginPath()
    ctx.arc(p.x, p.y, r * 2.5, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${cr},${cg},${cb},${p.opacity * 0.08})`
    ctx.fill()

    ctx.beginPath()
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${cr},${cg},${cb},${p.opacity * 0.7})`
    ctx.fill()
  }
}

function initBg() {
  const canvas = bgCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')

  // 尊重「减少动态效果」系统偏好：仅绘制一帧静态画面，不启动循环动画，避免引发不适
  const prefersReducedMotion =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const resize = () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
    createBgParticles(canvas.width, canvas.height)
  }
  resize()
  window.addEventListener('resize', resize)

  const onMouseMove = (e) => { bgMouse.x = e.clientX; bgMouse.y = e.clientY }
  const onMouseLeave = () => { bgMouse.x = null; bgMouse.y = null }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseleave', onMouseLeave)

  const loop = (time) => {
    animateBg(ctx, canvas.width, canvas.height, time)
    animFrameId = requestAnimationFrame(loop)
  }
  // 减少动态效果偏好：不启动循环动画，只绘制一帧静态画面
  if (prefersReducedMotion) {
    animateBg(ctx, canvas.width, canvas.height, 0)
    return
  }

  animFrameId = requestAnimationFrame(loop)

  // 标签页切到后台时暂停动画，回到前台再恢复，避免后台空转浪费 CPU/GPU
  const onVisibility = () => {
    if (document.hidden) {
      if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
    } else if (!animFrameId) {
      animFrameId = requestAnimationFrame(loop)
    }
  }
  document.addEventListener('visibilitychange', onVisibility)

  canvas._cleanup = () => {
    cancelAnimationFrame(animFrameId)
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('resize', resize)
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseleave', onMouseLeave)
  }
}

onMounted(() => initBg())
onUnmounted(() => {
  if (bgCanvas.value?._cleanup) bgCanvas.value._cleanup()
})
</script>

<template>
  <canvas ref="bgCanvas" class="bg-canvas"></canvas>
</template>

<style scoped>
.bg-canvas {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  /* 商务主题：背景只作极淡的质感层，不抢内容 */
  opacity: 0.35;
}
</style>
