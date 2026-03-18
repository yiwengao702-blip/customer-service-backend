<script setup>
// 业务对象侧栏（订单 / 商品）：纯展示型组件。
// 数据由父组件（App.vue）拉取后通过 props 下行；用户点击「发送」时通过 emit 上行，
// 具体的消息构造与发送逻辑仍由父组件统一处理，保证单一数据源。
import { ref } from 'vue'
import { formatAmount, getStatusClass } from '../utils/format.js'

const props = defineProps({
  orders: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  isLoadingSidebar: { type: Boolean, default: false },
  sidebarError: { type: String, default: '' },
  isSending: { type: Boolean, default: false },
})

const emit = defineEmits(['send-order', 'send-product'])

// 当前激活的标签页（订单 / 商品），属于本组件内部 UI 状态
const activeTab = ref('orders')
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2>业务对象</h2>
    </div>

    <div class="tabs">
      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'orders' }"
        @click="activeTab = 'orders'"
      >
        订单
      </button>
      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'products' }"
        @click="activeTab = 'products'"
      >
        商品
      </button>
    </div>

    <p v-if="sidebarError" class="sidebar-error">{{ sidebarError }}</p>

    <div v-if="activeTab === 'orders'" class="sidebar-list">
      <div v-if="!orders.length && !isLoadingSidebar" class="sidebar-empty">
        暂无订单数据
      </div>

      <article v-for="order in orders" :key="order.order_id" class="sidebar-card">
        <div class="card-image-wrapper">
          <img
            v-if="order.cover_url"
            :src="order.cover_url"
            :alt="order.title"
            class="card-image"
            loading="lazy"
            @error="$event.target.style.display = 'none'"
          />
          <div v-else class="card-image-placeholder">📦</div>
        </div>
        <div class="card-top">
          <div class="card-title">{{ order.title }}</div>
          <div class="card-amount">{{ formatAmount(order.amount) }}</div>
        </div>
        <div class="card-meta">订单号：{{ order.order_id }}</div>
        <div class="card-meta">
          <span class="status-badge" :class="getStatusClass(order.status)">{{ order.status }}</span>
        </div>
        <button
          type="button"
          class="secondary-button full-width"
          :disabled="isSending"
          @click="$emit('send-order', order)"
        >
          发送订单
        </button>
      </article>
    </div>

    <div v-else class="sidebar-list">
      <div v-if="!products.length && !isLoadingSidebar" class="sidebar-empty">
        暂无商品数据
      </div>

      <article v-for="product in products" :key="product.product_id" class="sidebar-card">
        <div class="card-image-wrapper">
          <img
            v-if="product.cover_url"
            :src="product.cover_url"
            :alt="product.title"
            class="card-image"
            loading="lazy"
            @error="$event.target.style.display = 'none'"
          />
          <div v-else class="card-image-placeholder">🛍️</div>
        </div>
        <div class="card-top">
          <div class="card-title">{{ product.title }}</div>
          <div class="card-amount">{{ formatAmount(product.price) }}</div>
        </div>
        <div class="card-meta">商品号：{{ product.product_id }}</div>
        <div class="card-meta">商品信息：最近浏览 / 购买商品</div>
        <button
          type="button"
          class="secondary-button full-width"
          :disabled="isSending"
          @click="$emit('send-product', product)"
        >
          发送商品
        </button>
      </article>
    </div>
  </aside>
</template>

<style scoped>
/* ── 侧栏容器（根节点；App.vue 的媒体查询仍通过 scoped 穿透作用于此根） ── */
.sidebar {
  min-height: calc(100vh - 48px);
  height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  backdrop-filter: blur(32px) saturate(1.2);
  -webkit-backdrop-filter: blur(32px) saturate(1.2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-glow-amber), var(--shadow-lg), var(--shadow-inner-glow);
  transition: border-color var(--duration-slow) var(--ease-in-out), box-shadow var(--duration-slow) var(--ease-in-out);
}
.sidebar:hover {
  border-color: rgba(90, 155, 106, 0.22);
}

.sidebar-header {
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--color-border-light);
}
/* 头部标题：与聊天区头部同款商务风渐变字号（scoped 不穿透子组件，故在此自包含） */
.sidebar-header h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #ffffff 0%, var(--color-accent) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.sidebar-empty {
  margin: auto;
  max-width: 420px;
  color: var(--color-text-muted);
  text-align: center;
  line-height: 1.7;
}

/* ── 状态徽章（与聊天区共用，组件内自包含一份以保证独立渲染） ── */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.status-warning {
  background: var(--color-warm-soft);
  color: var(--color-warm-strong);
  border: 1px solid rgba(217, 164, 65, 0.32);
}
.status-info {
  background: var(--color-info-soft);
  color: var(--color-info);
  border: 1px solid rgba(56, 189, 248, 0.25);
}
.status-success {
  background: var(--color-success-soft);
  color: var(--color-success);
  border: 1px solid rgba(52, 211, 153, 0.25);
}
.status-muted {
  background: rgba(113, 111, 104, 0.12);
  color: var(--color-text-muted);
  border: 1px solid rgba(113, 111, 104, 0.18);
}
.status-danger {
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border: 1px solid rgba(251, 113, 133, 0.25);
}

/* ── 商品 / 订单封面图 ── */
.card-image-wrapper {
  width: 100%;
  height: 140px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-surface-field);
  border: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--duration-base) var(--ease-out-expo);
}
.sidebar-card:hover .card-image {
  transform: scale(1.05);
}
.card-image-placeholder {
  font-size: 40px;
  opacity: 0.5;
}

/* ── 次级按钮（与聊天区共用，组件内自包含一份） ── */
.secondary-button {
  min-height: 42px;
  padding: 9px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.2;
  transition:
    transform var(--duration-fast) var(--ease-out-expo),
    box-shadow var(--duration-fast) var(--ease-out-expo),
    background var(--duration-fast) var(--ease-in-out),
    border-color var(--duration-fast) var(--ease-in-out);
}
.secondary-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.secondary-button:active:not(:disabled) {
  transform: translateY(0);
}
.secondary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}
.secondary-button.full-width {
  width: 100%;
  min-height: 42px;
}

.sidebar-error {
  margin: 0;
  padding: 0 24px 14px;
  color: var(--color-danger);
  font-size: 13px;
  font-weight: 500;
}

/* ── 标签页 ── */
.tabs {
  display: flex;
  gap: 8px;
  padding: 16px 24px 12px;
  border-bottom: 1px solid var(--color-border-light);
}
.tab-button {
  min-width: 80px;
}
.tab-button.active {
  background: linear-gradient(135deg, var(--color-accent-strong), var(--color-accent));
  border-color: transparent;
  color: #f0fdfa;
  box-shadow: 0 4px 14px var(--color-accent-glow);
}

/* ── 列表与卡片 ── */
.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.sidebar-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color var(--duration-fast) var(--ease-in-out),
    background var(--duration-fast) var(--ease-in-out);
}
.sidebar-card:hover {
  background: var(--color-surface-hover);
  border-color: var(--color-accent);
  box-shadow: var(--shadow-sm);
}
.card-top {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: flex-start;
}
.card-title {
  font-size: 15px;
  line-height: 1.5;
  color: var(--color-text-primary);
  font-weight: 600;
}
.card-amount {
  flex-shrink: 0;
  color: var(--color-warm-strong);
  font-weight: 700;
}
.card-meta {
  font-size: 14px;
  color: var(--color-text-secondary);
}
</style>
