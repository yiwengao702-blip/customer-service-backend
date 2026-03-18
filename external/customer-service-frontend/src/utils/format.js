// 金额与订单状态的格式化助手。
// 聊天消息卡片与业务对象侧栏都会用到，故抽为共享模块，避免重复定义、便于后续组件拆分。

// 订单状态 → 状态徽章配色类名（与 styles 中 .status-warning/info/... 对应）
export const ORDER_STATUS_CLASS = {
  '待发货': 'status-warning',
  '待揽收': 'status-warning',
  '运输中': 'status-info',
  '派送中': 'status-info',
  '已完成': 'status-success',
  '已签收': 'status-success',
  '已取消': 'status-muted',
  '退款中': 'status-danger',
  '已退款': 'status-muted',
}

// 金额格式化：统一输出「￥x.xx」；非数字兜底为 ￥0.00
export function formatAmount(amount) {
  const numericAmount = Number(amount)
  if (Number.isNaN(numericAmount)) {
    return '￥0.00'
  }
  return `￥${numericAmount.toFixed(2)}`
}

// 订单状态 → 徽章配色类名；未知状态回落到 status-muted
export function getStatusClass(status) {
  return ORDER_STATUS_CLASS[status] || 'status-muted'
}
