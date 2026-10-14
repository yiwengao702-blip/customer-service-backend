<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import BackgroundCanvas from './components/BackgroundCanvas.vue'
import Sidebar from './components/Sidebar.vue'
import { formatAmount, getStatusClass } from './utils/format.js'
import { fetchJson } from './utils/api.js'
import { getToken, setAuth, clearAuth, getStoredUser } from './utils/auth.js'
import xiaoerAvatar from './assets/xiaoer.webp'
import userProfileAvatar from './assets/user-avatar.webp'

const senderId = ref('u1001')
const draftMessage = ref('')
const isSending = ref(false)
const errorMessage = ref('')
const messages = ref([])
const messagesContainer = ref(null)

const orders = ref([])
const products = ref([])
const isLoadingSidebar = ref(false)
const sidebarError = ref('')
const activeTab = ref('orders')

// 数字人面板开关：默认开启（带数字人版）；URL 带 ?dh=off 或 ?nohuman=1 则关闭（无数字人版）
const showDigitalHuman = ref(true)
{
  const urlParams = new URLSearchParams(window.location.search)
  if (urlParams.get('dh') === 'off' || urlParams.get('nohuman') === '1') {
    showDigitalHuman.value = false
  }
}

// TTS state
const ttsState = ref({})
let currentAudio = null

// ───────────────────────────────────────────────────────────────
// 登录态 / 视图切换：login(登录页) / register(注册页) / chat(聊天主页)
// 未登录时只暴露登录/注册；登录成功后进入聊天，且所有请求自动带令牌。
// ───────────────────────────────────────────────────────────────
const view = ref('login')
const authUser = ref(getStoredUser())        // 刷新页面先用本地缓存，再异步校验
const authError = ref('')
const authLoading = ref(false)
const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ username: '', password: '', nickname: '' })

// 登录页左侧品牌区的能力亮点（智能客服主题，纯展示数据）
const authFeatures = [
  { icon: '💡', title: '商品知识问答', desc: '品种 / 产地 / 冲泡 / 功效，AI 秒懂你的需求' },
  { icon: '🧑‍💼', title: '数字人客服', desc: '端渲染 / 云渲染双引擎，开口即服务' },
  { icon: '📦', title: '订单与售后', desc: '查订单、跟物流、退换货全程自动应答' },
]

// 进入聊天页时加载侧边栏与历史（原先在 onMounted 里，这里抽出便于登录后复用）
async function loadChatData() {
  await Promise.all([fetchSidebarData(), fetchChatHistory()])
}

// 刷新页面恢复会话：有令牌就调 /api/auth/me 校验，有效则直接进入聊天，无效则清空回登录
async function restoreSession() {
  const token = getToken()
  if (!token) {
    view.value = 'login'
    return
  }
  try {
    const { response, data } = await fetchJson('/api/auth/me')
    if (!response.ok) throw new Error('令牌已失效')
    authUser.value = data
    view.value = 'chat'
    await loadChatData()
  } catch (e) {
    clearAuth()
    authUser.value = null
    view.value = 'login'
  }
}

// 登录：请求 /api/auth/login，成功则存令牌并进入聊天
async function doLogin() {
  authError.value = ''
  authLoading.value = true
  try {
    const { response, data } = await fetchJson('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(loginForm.value),
    })
    if (!response.ok) throw new Error(data?.detail || '登录失败')
    setAuth(data.token, data.user)
    authUser.value = data.user
    view.value = 'chat'
    loginForm.value = { username: '', password: '' }
    await loadChatData()
  } catch (e) {
    authError.value = e.message || '登录失败'
  } finally {
    authLoading.value = false
  }
}

// 注册：请求 /api/auth/register，成功则直接以新账号登录进入聊天
async function doRegister() {
  authError.value = ''
  authLoading.value = true
  try {
    const { response, data } = await fetchJson('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(registerForm.value),
    })
    if (!response.ok) throw new Error(data?.detail || '注册失败')
    setAuth(data.token, data.user)
    authUser.value = data.user
    view.value = 'chat'
    registerForm.value = { username: '', password: '', nickname: '' }
    await loadChatData()
  } catch (e) {
    authError.value = e.message || '注册失败'
  } finally {
    authLoading.value = false
  }
}

// 退出登录：清空本地令牌，回到登录页
function doLogout() {
  clearAuth()
  authUser.value = null
  view.value = 'login'
  messages.value = []
}

// Copy state
const copyState = ref({})


// 客服数字人配置
const customerService = {
  name: '小满',
  title: '金牌客服',
  avatar: xiaoerAvatar,
  status: '在线'
}

// 用户配置
const userProfile = {
  name: '你',
  avatar: userProfileAvatar
}

// 将消息分组为 Turn 结构
const turns = computed(() => {
  const result = []
  let currentTurn = null
  let turnIndex = 0

  for (const message of messages.value) {
    if (message.type === 'divider') {
      if (currentTurn) {
        result.push(currentTurn)
        currentTurn = null
      }
      result.push({
        type: 'divider',
        text: message.text
      })
      continue
    }

    if (message.role === 'user') {
      // 如果有待处理的当前 turn，先保存
      if (currentTurn) {
        result.push(currentTurn)
      }
      // 创建新的 turn
      turnIndex++
      currentTurn = {
        type: 'turn',
        id: `turn-${turnIndex}`,
        index: turnIndex,
        userMessage: message,
        botMessages: []
      }
    } else if (message.role === 'bot') {
      if (!currentTurn) {
        // 如果没有当前 turn，创建一个（可能是因为历史消息）
        turnIndex++
        currentTurn = {
          type: 'turn',
          id: `turn-${turnIndex}`,
          index: turnIndex,
          userMessage: null,
          botMessages: []
        }
      }
      currentTurn.botMessages.push(message)
    }
  }

  if (currentTurn) {
    result.push(currentTurn)
  }

  return result
})

const chatEndpoint = computed(() => '/api/chat')
const chatHistoryEndpoint = computed(
  () => `/api/chat/history?sender_id=${encodeURIComponent(senderId.value.trim())}`
)
const commerceOrdersEndpoint = computed(
  () => `/commerce/users/${encodeURIComponent(senderId.value.trim())}/orders`
)
const commerceProductsEndpoint = computed(
  () => `/commerce/users/${encodeURIComponent(senderId.value.trim())}/products`
)

function createBaseMessage(role, timestamp = Date.now()) {
  return {
    id: crypto.randomUUID(),
    role,
    buttons: [],
    // 用于聊天区按时间展示；若后端历史消息带时间则沿用，否则取落库时刻
    timestamp,
  }
}

function appendUserText(text) {
  messages.value.push({
    ...createBaseMessage('user'),
    type: 'text',
    text,
  })
}

function appendUserObject(objectType, payload) {
  messages.value.push({
    ...createBaseMessage('user'),
    type: 'object',
    objectType,
    payload,
  })
}

function appendBotMessages(botMessages) {
  for (const message of botMessages) {
    appendMessage('bot', message)
    // 同步驱动数字人朗读本句回复（仅 live 回复触发，历史消息不会朗读）
    if (message.text) speakDigitalHuman(message.text)
  }
}

function appendMessage(role, message) {
  if (role === 'divider') {
    messages.value.push({
      ...createBaseMessage('divider', message.timestamp),
      type: 'divider',
      text: message.text ?? '以上为历史消息',
    })
    return
  }

  if (message.object) {
    messages.value.push({
      ...createBaseMessage(role, message.timestamp),
      type: 'object',
      objectType: message.object.type,
      payload: message.object,
    })
  } else {
    messages.value.push({
      ...createBaseMessage(role, message.timestamp),
      type: 'text',
      text: message.text ?? '',
      suggestions: message.suggestions ?? null,
    })
  }
}

function setHistoryMessages(historyMessages) {
  messages.value = []
  for (const message of historyMessages) {
    const role = ['user', 'bot', 'divider'].includes(message.role) ? message.role : 'bot'
    appendMessage(role, message)
  }
}

async function scrollToBottom() {
  await nextTick()
  const container = messagesContainer.value
  if (!container) {
    return
  }
  container.scrollTop = container.scrollHeight
}

watch(
  () => messages.value.length,
  async () => {
    await scrollToBottom()
  }
)

// 把消息时间戳格式化为 HH:MM（当天）；用于聊天区每条消息的轻量时间标签
function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

function resetConversation() {
  messages.value = []
  errorMessage.value = ''
}

function formatOrderSummary(order) {
  return order.status ? `订单状态：${order.status}` : '订单'
}

function formatProductSummary(product) {
  if (product.description) {
    return product.description
  }
  if (product.attributes?.price) {
    return `商品价格：${formatAmount(product.attributes.price)}`
  }
  return '商品信息'
}

function getObjectTitle(message) {
  const payload = message.payload ?? {}
  if (payload.title) {
    return payload.title
  }
  return message.objectType === 'order' ? '订单对象' : '商品对象'
}

function getObjectIdentifier(message) {
  const payload = message.payload ?? {}
  const id = payload.order_id ?? payload.product_id ?? payload.id
  const label = message.objectType === 'order' ? '订单号' : '商品号'
  return id ? `${label}：${id}` : label
}

function getObjectSummary(message) {
  const payload = message.payload ?? {}
  if (message.objectType === 'order') {
    const status = payload.status ?? payload.attributes?.status
    return status ? `订单状态：${status}` : '订单'
  }
  return formatProductSummary(payload)
}

function getObjectAmount(message) {
  const payload = message.payload ?? {}
  const amount = message.objectType === 'order'
    ? payload.amount ?? payload.attributes?.amount
    : payload.price ?? payload.attributes?.price
  return formatAmount(amount)
}

async function fetchSidebarData() {
  const currentSenderId = senderId.value.trim()
  orders.value = []
  products.value = []
  sidebarError.value = ''

  if (!currentSenderId) {
    return
  }

  isLoadingSidebar.value = true
  try {
    // 统一走 fetchJson：后端未启动/空响应体时给出可读的中文错误，而非浏览器原始异常
    const [ordersResult, productsResult] = await Promise.all([
      fetchJson(commerceOrdersEndpoint.value, undefined, '订单列表'),
      fetchJson(commerceProductsEndpoint.value, undefined, '商品列表'),
    ])
    const { response: ordersResponse, data: ordersPayload } = ordersResult
    const { response: productsResponse, data: productsPayload } = productsResult

    if (!ordersResponse.ok) {
      throw new Error(ordersPayload?.detail || '加载订单列表失败。')
    }
    if (!productsResponse.ok) {
      throw new Error(productsPayload?.detail || '加载商品列表失败。')
    }

    orders.value = Array.isArray(ordersPayload?.data?.orders) ? ordersPayload.data.orders : []
    products.value = Array.isArray(productsPayload?.data?.products) ? productsPayload.data.products : []
  } catch (error) {
    sidebarError.value = error instanceof Error ? error.message : '加载右侧列表失败。'
  } finally {
    isLoadingSidebar.value = false
  }
}

async function fetchChatHistory() {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    messages.value = []
    return
  }

  try {
    // 统一走 fetchJson：后端未启动/空响应体时给出可读的中文错误
    const { response, data } = await fetchJson(chatHistoryEndpoint.value, undefined, '历史消息')
    if (!response.ok) {
      throw new Error(data?.detail || '加载历史消息失败。')
    }
    if (currentSenderId === senderId.value.trim()) {
      setHistoryMessages(Array.isArray(data?.messages) ? data.messages : [])
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载历史消息失败。'
  }
}

async function sendPayload(payload) {
  if (isSending.value) {
    return
  }

  errorMessage.value = ''
  isSending.value = true

  try {
    // 统一走 fetchJson：后端未启动/空响应体时给出可读的中文错误
    const { response, data } = await fetchJson(
      chatEndpoint.value,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sender_id: senderId.value.trim(),
          ...payload,
        }),
      },
      '对话'
    )

    if (!response.ok) {
      throw new Error(data?.detail || '请求失败。')
    }

    appendBotMessages(data.messages ?? [])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求失败。'
  } finally {
    isSending.value = false
  }
}

async function sendSuggestion(text) {
  appendUserText(text)
  await sendPayload({ text })
}

async function sendQuickText(text) {
  draftMessage.value = text
  await sendTextMessage()
}
async function sendTextMessage() {
  const text = draftMessage.value.trim()
  const currentSenderId = senderId.value.trim()

  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }
  if (!text) {
    return
  }

  draftMessage.value = ''
  appendUserText(text)
  await sendPayload({ text })
}

async function sendOrder(order) {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }

  appendUserObject('order', { ...order })
  await sendPayload({
    object: {
      type: 'order',
      id: order.order_id,
      title: order.title,
      attributes: {
        status: order.status,
        amount: order.amount,
        created_at: order.created_at,
        cover_url: order.cover_url,
      },
    },
  })
}

async function sendProduct(product) {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }

  appendUserObject('product', { ...product })
  await sendPayload({
    object: {
      type: 'product',
      id: product.product_id,
      title: product.title,
      attributes: {
        price: product.price,
        cover_url: product.cover_url,
        description: product.description,
      },
    },
  })
}

watch(
  () => senderId.value.trim(),
  async (value, previousValue) => {
    if (value === previousValue) {
      return
    }

    resetConversation()
    if (!value) {
      orders.value = []
      products.value = []
      return
    }
    await Promise.all([fetchSidebarData(), fetchChatHistory()])
  }
)

onMounted(async () => {
  // 刷新页面先尝试用已有令牌恢复会话；未登录则停留登录页
  await restoreSession()
})

async function playTts(botMsg) {
  const msgId = botMsg.id
  if (!botMsg.text || ttsState.value[msgId] === 'loading') return

  if (currentAudio) { currentAudio.pause(); currentAudio = null }
  for (const key of Object.keys(ttsState.value)) {
    if (ttsState.value[key] === 'playing') ttsState.value[key] = 'idle'
  }

  ttsState.value[msgId] = 'loading'
  try {
    const response = await fetch('/api/chat/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: botMsg.text }),
    })
    if (!response.ok) throw new Error('TTS 请求失败')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    currentAudio = new Audio(url)
    ttsState.value[msgId] = 'playing'
    currentAudio.onended = () => { ttsState.value[msgId] = 'idle'; URL.revokeObjectURL(url); currentAudio = null }
    currentAudio.onerror = () => { ttsState.value[msgId] = 'idle'; URL.revokeObjectURL(url); currentAudio = null }
    await currentAudio.play()
  } catch (error) {
    ttsState.value[msgId] = 'idle'
    console.error('TTS error:', error)
  }
}

async function copyBotText(botMsg) {
  const msgId = botMsg.id
  try {
    await navigator.clipboard.writeText(botMsg.text)
    copyState.value[msgId] = true
    setTimeout(() => { copyState.value[msgId] = false }, 1800)
  } catch (error) {
    console.error('Copy failed:', error)
  }
}

// ───────────────────────────────────────────────────────────────
// 数字人(魔珐星云 / 阿里灵眸) 集成
// 默认厂商由前端常量 DIGITAL_HUMAN_PROVIDER 决定(与后端 .env 的
// DIGITAL_HUMAN_PROVIDER 保持一致)。连接时先从后端拿凭证/会话，
// 再初始化对应 SDK；bot 文本回复到达时调用 speakDigitalHuman 朗读。
// ───────────────────────────────────────────────────────────────
// 前端默认厂商: moxia(魔珐星云, 纯前端 CDN SDK) / lingmou(阿里灵眸)
// 优先从后端 /api/digital-human/config 读取，保证与 .env 的
// DIGITAL_HUMAN_PROVIDER 始终一致；读取失败再回落到默认值。
const DIGITAL_HUMAN_PROVIDER_DEFAULT = 'moxia'
const digitalHumanProvider = ref(DIGITAL_HUMAN_PROVIDER_DEFAULT)

const dhSdk = ref(null)          // SDK 实例
const dhConnected = ref(false)   // 已连接并就绪(可说话)
const dhConnecting = ref(false)  // 正在连接
const dhProgress = ref(0)        // 魔珐资源下载进度 0-100
const dhStatusText = ref('未连接')
const dhError = ref('')

function setDhStatus(text) { dhStatusText.value = text }

// 动态加载外部 SDK 脚本(CDN)，返回 Promise
function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return }
    const s = document.createElement('script')
    s.src = src
    s.onload = () => resolve()
    s.onerror = () => reject(new Error(`加载 SDK 失败: ${src}`))
    document.head.appendChild(s)
  })
}

// 统一入口: 连接数字人(异步, 先取凭证/会话)
async function initDigitalHuman() {
  if (dhConnected.value || dhConnecting.value) return
  // 先销毁上一次可能残留的 SDK 实例，避免重复占用
  destroyDigitalHuman()
  // 读取后端配置的厂商（与 .env DIGITAL_HUMAN_PROVIDER 一致）
  try {
    const cfg = await fetch('/api/digital-human/config').then((r) => r.json())
    if (cfg && cfg.provider) digitalHumanProvider.value = cfg.provider
  } catch (e) {
    // 拉取失败则沿用默认值，不阻断连接
  }
  // 先自检浏览器环境（安全上下文 + WebGL2），不满足则直接给出修复指引。
  // 注意：灵眸是「云渲染」，画面由阿里云 RTC 推流，本地不需要 WebGL2，
  // 因此只对魔珐(端渲染)做 WebGL 校验。
  const env = digitalHumanProvider.value === 'lingmou'
    ? checkLingmouEnv()
    : checkDigitalHumanEnv()
  if (!env.ok) {
    dhError.value = env.title + '：' + env.fix
    // 追加本机实测结论，避免用户反复尝试无效方案
    dhError.value += '（本机实测：NVIDIA 驱动 2022-10 未更新 + 显示输出挂在 AMD 核显；' +
      '根治请更新 NVIDIA 驱动并在本机运行，临时方案见根目录 start-avatar-gpu.bat；' +
      '或改用阿里灵眸云渲染，无需显卡）'
    setDhStatus('环境不满足')
    return
  }
  dhConnecting.value = true
  dhError.value = ''
  dhProgress.value = 0
  setDhStatus('正在连接...')
  try {
    if (digitalHumanProvider.value === 'moxia') {
      await initMoxia()
    } else if (digitalHumanProvider.value === 'lingmou') {
      await initLingmou()
    } else {
      throw new Error('未知的数字人厂商: ' + digitalHumanProvider.value)
    }
  } catch (e) {
    dhError.value = e.message || '初始化失败'
    setDhStatus('连接失败')
    console.error('[数字人] 初始化失败:', e)
  } finally {
    dhConnecting.value = false
  }
}

// 常见错误码中文提示（对照魔珐星云 SDK 源码 xmovAvatar@latest.js）
// 重要：当前版本里 10005 = INIT_ERROR(初始化失败)，多为浏览器环境不满足导致，
// 而非旧文档所说的"房间限流"；具体原因以 SDK 的 message 字段为准。
const DH_ERROR_TEXT = {
  10001: '容器不存在：页面未找到数字人容器，请刷新页面',
  10002: 'Socket 连接错误：请检查网络后重试',
  10003: '会话错误：请检查 App ID / App Secret 是否正确',
  10005: '初始化失败(INIT_ERROR)：通常是浏览器环境不满足（见下方说明）',
  30001: '背景图片加载错误，请刷新重试',
  30004: '资源下载错误，请检查网络后重试',
  50004: '网络断开，SDK 会自动重连',
}

// 调用 SDK 前，先复刻 SDK 的两项 fatal 校验（取自 xmovAvatar 源码），
// 任一不过就直接给出明确修复指引，避免白白连一次拿个模糊的 10005。
function checkDigitalHumanEnv() {
  if (!window.isSecureContext) {
    return {
      ok: false,
      title: '当前不是安全上下文',
      fix: '请改用 https:// 或 http://localhost:5173 / http://127.0.0.1:5173 访问；不要用局域网 IP（如 http://192.168.x.x:5173），否则浏览器判定为不安全上下文，SDK 会报 10005。',
    }
  }
  let gl2 = null
  try {
    gl2 = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true })
  } catch (e) {}
  if (!gl2) {
    return {
      ok: false,
      title: '浏览器不支持 WebGL2',
      fix: '请开启 Chrome 硬件加速：chrome://settings → 系统 → 打开“使用硬件加速”，重启浏览器；若仍被软件渲染拦截，先更新显卡驱动（驱动过旧会被 Chrome 拉黑），或改用阿里灵眸云渲染。',
    }
  }
  // SDK 另有 3 项 fatal 校验：音频 / WebCodecs / Worker
  // （源码 checkAudioSystemSync / checkWebCodecsSync / checkWorkerSync）
  const hasAudioCtx = typeof window.AudioContext !== 'undefined' || typeof window.webkitAudioContext !== 'undefined'
  const hasWorklet = typeof window.AudioWorkletNode !== 'undefined'
  const hasMediaSource = typeof window.MediaSource !== 'undefined'
  if (!((hasAudioCtx && hasWorklet) || hasMediaSource)) {
    return {
      ok: false,
      title: '浏览器音频能力不可用',
      fix: '魔珐 SDK 需要 AudioContext+AudioWorklet 或 MediaSource，请使用较新的 Chrome/Edge（建议 94 以上）并确认未禁用音频。',
    }
  }
  if (typeof window.VideoDecoder === 'undefined') {
    return {
      ok: false,
      title: '浏览器不支持 WebCodecs (VideoDecoder)',
      fix: '魔珐 SDK 需要 WebCodecs，请升级到 Chrome/Edge 94 及以上版本；或改用阿里灵眸云渲染。',
    }
  }
  return { ok: true }
}

// 灵眸(云渲染)环境自检：只需安全上下文(RTC 要求)，
// 不需要 WebGL2 —— 画面由阿里云推流，本地无 GPU 也能用。
function checkLingmouEnv() {
  if (!window.isSecureContext) {
    return {
      ok: false,
      title: '当前不是安全上下文',
      fix: '灵眸 RTC 仅允许在 HTTPS 或 http://localhost / http://127.0.0.1 下运行，请不要用局域网 IP 访问本系统。',
    }
  }
  return { ok: true }
}

// ── 10005 房间限流自动重试 ──
// 服务端旧连接要等几十秒心跳超时才释放，与其让用户手动反复点击，
// 不如每 30s 自动重试一次（最多 5 次，约覆盖 2 分钟释放窗口）
const DH_RETRY_MAX = 5
const DH_RETRY_INTERVAL = 30000
let dhRetryTimer = null
let dhRetryLeft = 0

function clearDhRetryTimer() {
  if (dhRetryTimer) { clearTimeout(dhRetryTimer); dhRetryTimer = null }
}

function scheduleDhRetry() {
  clearDhRetryTimer()
  if (dhRetryLeft <= 0) dhRetryLeft = DH_RETRY_MAX
  dhRetryLeft -= 1
  if (dhRetryLeft > 0) {
    setDhStatus(`连接异常，${DH_RETRY_INTERVAL / 1000}s 后自动重试(剩 ${dhRetryLeft} 次)...`)
    dhRetryTimer = setTimeout(() => { dhRetryTimer = null; initDigitalHuman() }, DH_RETRY_INTERVAL)
  } else {
    setDhStatus('仍无法连接')
    if (!dhError.value) dhError.value = '多次自动重试仍失败，请检查网络与 App ID / App Secret 配置'
  }
}

// 魔珐星云(XmovAvatar) 初始化
async function initMoxia() {
  // 统一走 fetchJson：后端未启动时空响应体也能得到可读错误（外层 catch 会展示到 dhError）
  const { data: cred } = await fetchJson('/api/digital-human/credentials', undefined, '数字人凭证')
  if (!cred.configured) {
    throw new Error('后端未配置魔珐星云凭证，请在 .env 设置 DIGITAL_HUMAN_APP_ID / DIGITAL_HUMAN_APP_SECRET')
  }
  await loadScript('https://media.xingyun3d.com/xingyun3d/general/litesdk/xmovAvatar@latest.js')
  dhSdk.value = new window.XmovAvatar({
    containerId: '#digital-human-sdk',
    appId: cred.app_id,
    appSecret: cred.app_secret,
    gatewayServer: cred.gateway_server,
    hardwareAcceleration: 'prefer-hardware',
    enableLogger: false,
    // 走 MSE 音频路径：SDK 内部有两条音频通路
    //   raw_audio=true  → AudioWorklet（Firefox + 软渲染/远程会话下易静默失败）
    //   raw_audio=false → MediaSource + <audio>（兼容性最好，Firefox 实测更稳）
    // 现象：口型在动但没声音，通常就是 Worklet 通路失败导致。
    raw_audio: false,
    onMessage(message) {
      // 50001/50002 是离线/在线模式通知，不算错误
      if (message && message.code && message.code !== 50001 && message.code !== 50002) {
        // 优先展示 SDK 自带的真实原因(message 字段)，比错误码更有用
        dhError.value = message.message
          ? (DH_ERROR_TEXT[message.code] ? DH_ERROR_TEXT[message.code] + '：' : '') + message.message
          : (DH_ERROR_TEXT[message.code] || ('SDK 错误 code=' + message.code))
        // 魔珐服务端会在应用配置不完整（形象/角色未保存）时返回
        //形如 "Error: 3, APP, 3次失败" 的消息，这里翻译成可操作指引
        const raw = String(message.message || '')
        if (/APP|次失败|角色|形象/i.test(raw)) {
          dhError.value =
            '应用配置不完整（魔珐服务端返回：' + raw + '）。' +
            '请到魔珐星云控制台 → 该应用 →「形象」页重新选择一个数字人形象并点「保存」，' +
            '再点右上角「接入SDK」重新获取 App ID / App Secret 后重新连接。'
        }
        // 仅对瞬时网络类错误(10002/50004)自动重试；10005=初始化失败属环境不满足，重试无意义
        if (message.code === 10002 || message.code === 50004) scheduleDhRetry()
      }
    },
    onVoiceStateChange(status) {
      if (status === 'start') setDhStatus('数字人正在说话...')
      else if (status === 'end') setDhStatus('就绪')
    },
  })
  // 关键: 必须调用 init 下载资源, 进度到 100% 后才能 speak
  // 若init 以 Promise 形式失败（如应用形象未配置导致服务端拒绝），在此兜住并给出指引
  const initRet = dhSdk.value.init({
    initModel: 'normal',
    onDownloadProgress(progress) {
      dhProgress.value = progress
      if (progress >= 100) {
        dhConnected.value = true
        setDhStatus('就绪')
        // 就绪后补播排队文本（软渲染加载慢时不会漏掉语音）
        drainSpeakQueue()
      }
    },
  })
  if (initRet && typeof initRet.catch === 'function') {
    initRet.catch((e) => {
      const msg = (e && (e.message || e.toString())) || '未知错误'
      dhError.value = /APP|次失败|角色|形象/i.test(msg)
        ? '应用配置不完整（魔珐服务端返回：' + msg + '）。请到魔珐星云控制台 → 该应用 →「形象」页重新选择数字人形象并点「保存」，再重新获取 App ID / App Secret 后连接。'
        : '初始化失败：' + msg
      setDhStatus('连接失败')
      console.error('[数字人] init 失败:', e)
    })
  }
}

// 阿里灵眸(lm-avatar-chat-sdk) 初始化
async function initLingmou() {
  // 统一走 fetchJson：后端未启动/空响应体时给出可读错误
  const { response, data: session } = await fetchJson('/api/avatar/session', undefined, '灵眸会话')
  if (!response.ok) {
    throw new Error(session?.detail || '获取灵眸会话失败')
  }
  let LM
  try {
    // 用变量承载包名，避免 Vite 在编译期静态解析这个可选依赖；
    // 运行时若未安装，会进入 catch 给出友好提示（默认魔珐路径不会走到这里）
    const sdkPkg = 'lm-avatar-chat-sdk'
    LM = await import(/* @vite-ignore */ sdkPkg)
  } catch (e) {
    throw new Error('未安装 lm-avatar-chat-sdk，请先 npm install lm-avatar-chat-sdk')
  }
  // 官方接入姿势（云渲染全链路）：
  //   createAvatar(TYAvatarType.cloudAvatar, {...rtcParams, rootContainer, sessionId})
  //   → avatar.start({ mode: TYVoiceChatMode.tap2talk })
  // rtc_params 由后端 CreateChatSession 返回（appId/channel/token/timestamp/
  // clientUserId/clientUserName/serverUserId/avatarUserId/gslb/nonce）。
  const { createAvatar, TYAvatarType, TYVoiceChatMode } = LM
  if (!createAvatar || !TYAvatarType) {
    throw new Error('lm-avatar-chat-sdk 版本异常：未导出 createAvatar / TYAvatarType')
  }

  const initParams = Object.assign({}, session.rtcParams || {}, {
    rootContainer: '#digital-human-video',
    sessionId: session.sessionId,
  })

  dhSdk.value = createAvatar(TYAvatarType.cloudAvatar, initParams)

  // 首帧渲染完成 → 数字人真正出现
  if (dhSdk.value.onFirstFrameReceived) {
    dhSdk.value.onFirstFrameReceived(() => {
      dhConnected.value = true
      setDhStatus('就绪')
    })
  }
  // 可开始语音交互
  if (dhSdk.value.onReadyToSpeech) {
    dhSdk.value.onReadyToSpeech(() => setDhStatus('数字人正在聆听...'))
  }
  // 内部错误回调（云渲染不需要本地 WebGL，但 RTC/会话仍可能出错）
  if (dhSdk.value.onErrorReceived) {
    dhSdk.value.onErrorReceived((err) => {
      dhError.value = '灵眸错误 code=' + (err && err.code) + ' ' + (err && err.message)
      setDhStatus('连接异常')
    })
  }

  dhSdk.value.start({ mode: TYVoiceChatMode ? TYVoiceChatMode.tap2talk : undefined })
  // 未收到首帧回调时兜底标记，避免一直停在"正在连接"
  setTimeout(() => {
    if (!dhConnected.value && !dhError.value) {
      dhConnected.value = true
      setDhStatus('已启动（等待画面）')
    }
  }, 8000)
}

// 音频自检：用 WebAudio 播一声提示音，区分
//「系统/浏览器音频有问题」与「SDK 音频通路有问题」。
// 同时尝试把 SDK 音量拉到最大，排除被设成 0。
function audioSelfTest() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) {
      dhError.value = '音频自检：浏览器不支持 AudioContext'
      return
    }
    const ctx = new AC()
    // 尝试拉起被挂起的 AudioContext（自动播放策略）
    if (ctx.state === 'suspended') ctx.resume()

    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.0001, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.6, ctx.currentTime + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5)
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.55)

    // 顺便把 SDK 音量拉满
    if (dhSdk.value) {
      if (typeof dhSdk.value.setVolume === 'function') dhSdk.value.setVolume(1)
      if (typeof dhSdk.value.setSpeed === 'function') dhSdk.value.setSpeed(1)
    }

    setTimeout(() => {
      const stateTxt = ctx.state === 'running'
        ? '提示音已触发（若完全听不到，问题在系统音频层）'
        : 'AudioContext 状态为 ' + ctx.state + '（可能被自动播放策略挂起，请再点一次本按钮）'
      dhError.value =
        '音频自检：' + stateTxt +
        '｜已检测到本机输出设备为「扬声器 (ToDesk Virtual Audio)」——' +
        '若你正在用 ToDesk 远程控制本机，该虚拟声卡需要 ToDesk 开启音频转发才能听到；' +
        '否则请把 Windows 输出设备切到真实声卡（如 耳机/漫步者 Zero Buds）。' +
        'SDK 音量已拉满。'
      if (import.meta.env.DEV) console.log('[数字人] audio self-test, AudioContext state =', ctx.state)
    }, 700)
  } catch (e) {
    dhError.value = '音频自检失败：' + (e.message || e)
  }
}

// 待播报队列：若数字人尚未就绪，先排队，等 onDownloadProgress 到 100%
// 再依次播报。否则软渲染加载慢时 speak() 会被静默丢弃（用户表现为"没声音"）。
let speakQueue = []
let speakDraining = false

// 让数字人把一段文本"说"出来(bot 回复到达时调用)
function speakDigitalHuman(text) {
  if (!showDigitalHuman.value) return
  if (!text) return
  if (!dhConnected.value || !dhSdk.value) {
    // 未就绪 → 入队，避免"点了连接但还没加载完就不出声"
    speakQueue.push(text)
    if (import.meta.env.DEV) console.warn('[数字人] 尚未就绪，已排队等待:', text.slice(0, 20))
    return
  }
  doSpeak(text)
}

// 实际执行播报（逐条，避免多句叠在一起）
function doSpeak(text) {
  try {
    if (digitalHumanProvider.value === 'moxia') {
      // 魔珐: 非流式一次性说话(is_start=true, is_end=true)
      dhSdk.value.speak(text, true, true)
    } else if (digitalHumanProvider.value === 'lingmou') {
      // 灵眸云渲染文本驱动：requestToRespond(type, text)
      // type = 'transcript' 表示直接把文本交给数字人朗读，
      // 由灵眸云端完成 TTS + 口型 + 推流（无需本地 WebGL）。
      if (dhSdk.value.requestToRespond) {
        dhSdk.value.requestToRespond('transcript', text)
      }
    }
  } catch (e) {
    console.error('[数字人] 说话失败:', e)
  }
}

// 就绪后把队列里的文本依次播完
function drainSpeakQueue() {
  if (speakDraining) return
  speakDraining = true
  const items = speakQueue.slice()
  speakQueue = []
  items.forEach((t, i) => setTimeout(() => doSpeak(t), i * 200))
  if (import.meta.env.DEV && items.length) console.log(`[数字人] 就绪，补播 ${items.length} 条待播文本`)
  setTimeout(() => { speakDraining = false }, items.length * 200 + 500)
}

// 断开并释放数字人(避免并发占用)
function destroyDigitalHuman() {
  clearDhRetryTimer()
  dhRetryLeft = 0
  try { if (dhSdk.value && dhSdk.value.destroy) dhSdk.value.destroy() } catch (e) {}
  dhSdk.value = null
  dhConnected.value = false
  dhProgress.value = 0
  setDhStatus('未连接')
}

// 页面刷新/关闭前主动销毁 SDK：立刻向服务端释放房间连接。
// 不做这一步，服务端要等几十秒心跳超时才释放旧房间，
// 期间重连就会报 10005「超出房间并发限制」(官方文档明确的坑)
window.addEventListener('beforeunload', destroyDigitalHuman)
window.addEventListener('pagehide', destroyDigitalHuman)
</script>

<template>
  <!-- 登录 / 注册 全屏视图：左品牌展示 + 右表单卡片 -->
  <div v-if="view !== 'chat'" class="auth-screen">
    <BackgroundCanvas />
    
    <div class="auth-layout">
      <!-- 左：品牌展示区（智能客服主题） -->
      <section class="auth-brand-panel">
        <div class="auth-logo-row">
          <span class="auth-logo-mark">语</span>
          <div class="auth-logo-text">
            <h1>语桥 <span class="brand-en">YuBridge</span></h1>
            <p class="brand-slogan">大模型 · 智能客服中台</p>
          </div>
        </div>
        <div class="auth-gold-line"></div>
        <ul class="auth-features">
          <li v-for="f in authFeatures" :key="f.title">
            <span class="feat-icon">{{ f.icon }}</span>
            <div class="feat-text">
              <b>{{ f.title }}</b>
              <small>{{ f.desc }}</small>
            </div>
          </li>
        </ul>
        <p class="auth-footnote">登录后即可咨询商品选购、使用与售后问题</p>
      </section>

      <!-- 右：表单卡片 -->
      <section class="auth-card">
        <div class="auth-tabs">
          <button type="button" :class="{ active: view === 'login' }" @click="view = 'login'; authError = ''">登录</button>
          <button type="button" :class="{ active: view === 'register' }" @click="view = 'register'; authError = ''">注册</button>
        </div>

        <form v-if="view === 'login'" class="auth-form" @submit.prevent="doLogin">
          <label>用户名
            <div class="input-wrap">
              <span class="input-icon">👤</span>
              <input v-model="loginForm.username" type="text" autocomplete="username" placeholder="3-32 位字母/数字/下划线" required />
            </div>
          </label>
          <label>密码
            <div class="input-wrap">
              <span class="input-icon">🔒</span>
              <input v-model="loginForm.password" type="password" autocomplete="current-password" placeholder="至少 6 位" required />
            </div>
          </label>
          <p v-if="authError" class="auth-error">{{ authError }}</p>
          <button type="submit" class="auth-submit" :disabled="authLoading">{{ authLoading ? '登录中…' : '登 录' }}</button>
        </form>

        <form v-else class="auth-form" @submit.prevent="doRegister">
          <label>用户名
            <div class="input-wrap">
              <span class="input-icon">👤</span>
              <input v-model="registerForm.username" type="text" autocomplete="username" placeholder="3-32 位字母/数字/下划线" required />
            </div>
          </label>
          <label>昵称（选填）
            <div class="input-wrap">
              <span class="input-icon">🏷️</span>
              <input v-model="registerForm.nickname" type="text" placeholder="留空则等同用户名" />
            </div>
          </label>
          <label>密码
            <div class="input-wrap">
              <span class="input-icon">🔒</span>
              <input v-model="registerForm.password" type="password" autocomplete="new-password" placeholder="至少 6 位" required />
            </div>
          </label>
          <p v-if="authError" class="auth-error">{{ authError }}</p>
          <button type="submit" class="auth-submit" :disabled="authLoading">{{ authLoading ? '注册中…' : '注 册' }}</button>
        </form>

        <p class="auth-switch">
          <template v-if="view === 'login'">还没有账号？<a @click="view = 'register'; authError = ''">去注册</a></template>
          <template v-else>已有账号？<a @click="view = 'login'; authError = ''">去登录</a></template>
        </p>
      </section>
    </div>
  </div>

  <div v-if="view === 'chat'" class="app-shell">
    <BackgroundCanvas />
    
    <div class="workspace" :class="{ 'no-digital-human': !showDigitalHuman }">
      <aside v-if="showDigitalHuman" class="digital-human-panel">
        <div class="dh-header">
          <h2>数字人客服</h2>
          <span class="dh-provider">{{ digitalHumanProvider === 'moxia' ? '魔珐星云' : '阿里灵眸' }}</span>
        </div>
        <div class="dh-viewport" :class="'is-' + digitalHumanProvider">
          <!-- 魔珐星云（端渲染）：WebGL 画布容器，仅魔珐模式显示 -->
          <div id="digital-human-sdk"></div>
          <!-- 灵眸（云渲染）：RTC 视频流容器，仅灵眸模式显示 -->
          <video id="digital-human-video" class="dh-video" autoplay playsinline></video>
          <div v-if="!dhConnected && !dhConnecting" class="dh-placeholder">
            <div class="dh-placeholder-icon">🧑‍💼</div>
            <p>点击「连接数字人」让客服"活"起来</p>
          </div>
          <div v-if="dhError" class="dh-error">{{ dhError }}</div>
        </div>
        <div class="dh-progress" v-if="dhConnecting || dhProgress > 0">
          <div class="dh-progress-bar" :style="{ width: dhProgress + '%' }"></div>
        </div>
        <div class="dh-footer">
          <div class="dh-status">{{ dhStatusText }}</div>
          <div class="dh-footer-btns">
            <!-- 手动试音：用于区分"没连上"与"连上了但没声音" -->
            <button
              type="button"
              class="dh-test-btn"
              :disabled="!dhConnected"
              title="让数字人说一句测试语音"
              @click="speakDigitalHuman('您好，我是电商小二，很高兴为您服务。')"
            >
              试音
            </button>
            <!-- 音频自检：判断是系统音频问题还是 SDK 音频通路问题 -->
            <button
              type="button"
              class="dh-test-btn"
              title="播放一声提示音，检查浏览器/系统音频是否正常"
              @click="audioSelfTest()"
            >
              音量自检
            </button>
            <button
              type="button"
              class="dh-connect-btn"
              :class="{ danger: dhConnected }"
              :disabled="dhConnecting"
              @click="dhConnected ? destroyDigitalHuman() : initDigitalHuman()"
            >
              {{ dhConnected ? '断开连接' : (dhConnecting ? '连接中...' : '连接数字人') }}
            </button>
          </div>
        </div>
      </aside>

      <div class="chat-card">
        <header class="chat-header">
          <div class="header-content">
            <div class="header-info">
              <div class="brand-row">
                <h1>语桥</h1>
                <span class="brand-en">YuBridge</span>
                <span class="brand-slogan">大模型 · 智能客服中台</span>
              </div>
              <div class="service-info">
                <div class="service-avatar-wrapper">
                  <img :src="customerService.avatar" class="service-avatar" />
                  <span class="status-indicator"></span>
                </div>
                <div class="service-details">
                  <span class="service-name">{{ customerService.name }}</span>
                  <span class="service-status">{{ customerService.status }}</span>
                </div>
              </div>
            </div>
            <button type="button" class="clear-button" title="清空对话" @click="resetConversation">
              <span>🔄</span>
              <span>新对话</span>
            </button>
            <button type="button" class="logout-button" title="退出登录" @click="doLogout">
              <span>🚪</span>
              <span>退出</span>
            </button>
            <button
              type="button"
              class="dh-toggle-button"
              :class="{ off: !showDigitalHuman }"
              :title="showDigitalHuman ? '当前：带数字人版，点击切换到无数字人版' : '当前：无数字人版，点击切换回带数字人版'"
              @click="showDigitalHuman = !showDigitalHuman"
            >
              🧑‍💼 数字人：{{ showDigitalHuman ? '开' : '关' }}
            </button>
          </div>
        </header>

        <details class="dev-panel">
          <summary class="dev-panel-summary">
            <span class="dev-panel-title">开发者调试</span>
            <span class="dev-panel-hint">会话标识 / 对象列表</span>
          </summary>
          <div class="dev-panel-body">
            <label class="field">
              <span>sender_id</span>
              <div class="field-row">
                <input v-model="senderId" type="text" placeholder="u1001" />
                <button
                  type="button"
                  class="secondary-button"
                  :disabled="isLoadingSidebar"
                  @click="fetchSidebarData"
                >
                  {{ isLoadingSidebar ? '加载中...' : '刷新对象列表' }}
                </button>
              </div>
            </label>
          </div>
        </details>

        <section ref="messagesContainer" class="messages">
          <div v-if="turns.length === 0" class="welcome">
            <div class="welcome-card">
              <div class="welcome-glow"></div>
              <div class="welcome-avatar-wrapper">
                <img :src="customerService.avatar" class="welcome-avatar" alt="小满" />
                <span class="welcome-status-pulse"></span>
              </div>
              <h2 class="welcome-greeting">Hi，我是 {{ customerService.name }}</h2>
              <p class="welcome-subtitle">语桥数字人客服 · 随时为你服务</p>
              <div class="welcome-chips">
                <button
                  v-for="chip in ['我要退款', '查订单状态', '商品推荐', '退换货政策']"
                  :key="chip"
                  type="button"
                  class="welcome-chip"
                  :disabled="isSending"
                  @click="sendQuickText(chip)"
                >{{ chip }}</button>
              </div>
              <p class="welcome-features">
                <span>💬 文字对话</span>
                <span>🔊 语音播报</span>
                <span>📦 订单查询</span>
                <span>🛍️ 商品咨询</span>
              </p>
            </div>
          </div>

          <!-- Turn 结构展示 -->
          <template v-for="(item, index) in turns" :key="item.id || index">
            <!-- 分隔线 -->
            <div v-if="item.type === 'divider'" class="history-divider">
              <span>{{ item.text }}</span>
            </div>

            <!-- Turn 卡片 -->
            <div v-else class="turn-card" :class="{ 'has-user-message': item.userMessage }">
              <!-- Turn 标识 -->
              <div class="turn-header">
                <span class="turn-badge">Turn {{ item.index }}</span>
                <span class="turn-label">对话轮次</span>
              </div>

              <!-- 用户消息区域 -->
              <div v-if="item.userMessage" class="turn-section user-section">
                <div class="section-header">
                  <div class="avatar-wrapper user-avatar">
                    <img :src="userProfile.avatar" class="avatar" />
                  </div>
                <div class="agent-info">
                  <span class="agent-name">{{ userProfile.name }}</span>
                  <span class="agent-label">用户</span>
                  <span class="msg-time">{{ formatTime(item.userMessage.timestamp) }}</span>
                </div>
                </div>
                <div class="turn-bubble user-bubble">
                  <template v-if="item.userMessage.type === 'object'">
                    <div class="object-card" :class="`object-card-${item.userMessage.objectType}`">
                      <div class="object-card-badge">
                        {{ item.userMessage.objectType === 'order' ? '订单对象' : '商品对象' }}
                      </div>
                      <img
                        v-if="item.userMessage.type === 'object' && item.userMessage.payload.cover_url"
                        :src="item.userMessage.payload.cover_url"
                        :alt="getObjectTitle(item.userMessage)"
                        class="object-card-image"
                        @error="$event.target.style.display='none'"
                      />
                      <div class="object-card-title">{{ getObjectTitle(item.userMessage) }}</div>
                      <div class="object-card-meta">{{ getObjectIdentifier(item.userMessage) }}</div>
                      <div class="object-card-meta">
                        <span v-if="item.userMessage.objectType === 'order' && item.userMessage.payload.status" class="status-badge" :class="getStatusClass(item.userMessage.payload.status)">{{ item.userMessage.payload.status }}</span>
                        <span v-else>{{ getObjectSummary(item.userMessage) }}</span>
                      </div>
                      <div class="object-card-price">{{ getObjectAmount(item.userMessage) }}</div>
                    </div>
                  </template>
                  <template v-else>
                    <p>{{ item.userMessage.text }}</p>
                  </template>
                </div>
              </div>

              <!-- 客服回复区域 -->
              <div v-if="item.botMessages.length > 0" class="turn-section bot-section">
                <div class="section-header">
                  <div class="avatar-wrapper service-avatar">
                    <img :src="customerService.avatar" class="avatar" />
                    <span class="status-dot"></span>
                  </div>
                <div class="agent-info">
                  <span class="agent-name">{{ customerService.name }}</span>
                  <span class="agent-label">{{ customerService.title }}</span>
                  <span class="msg-time">{{ formatTime(item.botMessages[0]?.timestamp) }}</span>
                </div>
                </div>
                <div class="bot-messages">
                  <div
                    v-for="(botMsg, msgIndex) in item.botMessages"
                    :key="msgIndex"
                    class="turn-bubble bot-bubble"
                  >
                    <template v-if="botMsg.type === 'object'">
                      <div class="object-card" :class="`object-card-${botMsg.objectType}`">
                        <div class="object-card-badge">
                          {{ botMsg.objectType === 'order' ? '订单对象' : '商品对象' }}
                        </div>
                        <img
                          v-if="botMsg.type === 'object' && botMsg.payload.cover_url"
                          :src="botMsg.payload.cover_url"
                          :alt="getObjectTitle(botMsg)"
                          class="object-card-image"
                          @error="$event.target.style.display='none'"
                        />
                        <div class="object-card-title">{{ getObjectTitle(botMsg) }}</div>
                        <div class="object-card-meta">{{ getObjectIdentifier(botMsg) }}</div>
                        <div class="object-card-meta">
                          <span v-if="botMsg.objectType === 'order' && botMsg.payload.status" class="status-badge" :class="getStatusClass(botMsg.payload.status)">{{ botMsg.payload.status }}</span>
                          <span v-else>{{ getObjectSummary(botMsg) }}</span>
                        </div>
                        <div class="object-card-price">{{ getObjectAmount(botMsg) }}</div>
                      </div>
                    </template>
                    <template v-else>
                      <div class="bot-text-row">
                        <p>{{ botMsg.text }}</p>
                        <div class="bot-actions">
                          <button type="button" class="tts-button"
                            :class="{ 'tts-loading': ttsState[botMsg.id] === 'loading', 'tts-playing': ttsState[botMsg.id] === 'playing' }"
                            :disabled="ttsState[botMsg.id] === 'loading'"
                            :title="ttsState[botMsg.id] === 'playing' ? '正在播放...' : '语音播报'"
                            @click.stop="playTts(botMsg)">
                            <span v-if="ttsState[botMsg.id] === 'loading'" class="tts-spinner"></span>
                            <span v-else-if="ttsState[botMsg.id] === 'playing'" class="tts-bars">
                              <span></span><span></span><span></span>
                            </span>
                            <span v-else>🔈</span>
                          </button>
                          <button type="button" class="copy-button"
                            :class="{ 'copy-done': copyState[botMsg.id] }"
                            :title="copyState[botMsg.id] ? '已复制' : '复制文字'"
                            @click.stop="copyBotText(botMsg)">
                            <span v-if="copyState[botMsg.id]">✓</span>
                            <span v-else>📋</span>
                          </button>
                        </div>
                      </div>
                    </template>
                    <div v-if="botMsg.suggestions && botMsg.suggestions.length > 0" class="suggestion-chips">
                      <button
                        v-for="sug in botMsg.suggestions"
                        :key="sug"
                        type="button"
                        class="suggestion-chip"
                        :disabled="isSending"
                        @click.stop="sendSuggestion(sug)"
                      >{{ sug }}</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </section>

        <div v-if="isSending" class="typing-indicator">
          <div class="typing-avatar">
            <img :src="customerService.avatar" class="avatar-small" alt="小满" />
          </div>
          <div class="typing-bubble">
            <span class="typing-dots">
              <span></span><span></span><span></span>
            </span>
            <span class="typing-label">小满正在输入...</span>
          </div>
        </div>

        <p v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </p>

        <form class="composer" @submit.prevent="sendTextMessage">
          <input
            v-model="draftMessage"
            type="text"
            placeholder="请输入咨询内容..."
            :disabled="isSending"
          />
          <button type="submit" :disabled="isSending || !draftMessage.trim()">
            {{ isSending ? '发送中...' : '发送' }}
          </button>
        </form>
      </div>

      <Sidebar
        :orders="orders"
        :products="products"
        :is-loading-sidebar="isLoadingSidebar"
        :sidebar-error="sidebarError"
        :is-sending="isSending"
        @send-order="sendOrder"
        @send-product="sendProduct"
      />
    </div>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300..700&family=Zen+Maru+Gothic:wght@400;500;700&display=swap');

:global(*) {
  box-sizing: border-box;
}

:global(:root) {
  /* ── Palette · 商务主题：蓝色主调 ── */
  --color-bg-deep: #0a1120;
  --color-bg-mid: #0e1728;
  --color-bg-surface: #131d31;
  /* 磨砂玻璃：降低通透度，商务风要「实」不要「飘」 */
  --color-surface: rgba(17, 25, 42, 0.86);
  --color-surface-hover: rgba(26, 36, 57, 0.92);
  --color-surface-dim: rgba(17, 25, 42, 0.62);
  --color-surface-raised: rgba(29, 40, 62, 0.78);
  --color-surface-field: rgba(8, 16, 12, 0.62);
  /* Light text on dark surfaces */
  --color-text-primary: #e6e3dc;
  --color-text-secondary: #9b9790;
  --color-text-muted: #726f68;
  --color-text-inverse: #18171c;
  /* ── 商务主题主色：蓝色 + 琥珀金 ── */
  --color-bg-deep: #0a1120;
  --color-bg-mid: #0e1728;
  --color-bg-surface: #131d31;
  --color-surface: rgba(17, 25, 42, 0.86);
  --color-surface-hover: rgba(26, 36, 57, 0.92);
  --color-surface-dim: rgba(17, 25, 42, 0.62);
  --color-surface-raised: rgba(29, 40, 62, 0.78);
  --color-surface-field: rgba(8, 16, 12, 0.66);
  /* 文本：冷灰阶，层次靠亮度差而非发光 */
  --color-text-primary: #e9eef7;
  --color-text-secondary: #a4b0c4;
  --color-text-muted: #6d7a90;
  --color-text-inverse: #0a1120;
  /* 主色：蓝色 */
  --color-accent: #4a8cff;
  --color-accent-strong: #2f6fe4;
  --color-accent-soft: rgba(74, 140, 255, 0.12);
  --color-accent-glow: rgba(74, 140, 255, 0.18);
  --color-accent-soft-bg: rgba(74, 140, 255, 0.06);
  /* 点缀：琥珀金，仅用于强调与高亮，不做大面积铺色 */
  --color-warm: #c9a227;
  --color-warm-strong: #a8851a;
  --color-warm-soft: rgba(201, 162, 39, 0.12);
  --color-warm-glow: rgba(201, 162, 39, 0.14);
  --color-warm-soft-bg: rgba(201, 162, 39, 0.05);
  /* 语义色：降低饱和，更沉稳 */
  --color-success: #2fa96b;
  --color-success-soft: rgba(47, 169, 107, 0.12);
  --color-info: #4a8cff;
  --color-info-soft: rgba(74, 140, 255, 0.12);
  --color-danger: #d9534f;
  --color-danger-soft: rgba(217, 83, 79, 0.12);
  /* 描边：商务风要利落，加强对比让卡片边界清晰 */
  --color-border: rgba(255, 255, 255, 0.13);
  --color-border-light: rgba(255, 255, 255, 0.08);
  --color-border-strong: rgba(255, 255, 255, 0.22);
  /* ── 圆角：商务风收紧，避免糖果感 ── */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;
  /* ── 阴影：去掉辉光，改分层投影 ── */
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.24);
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.28);
  --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.32);
  --shadow-lg: 0 20px 48px rgba(0, 0, 0, 0.38);
  --shadow-glow-teal: 0 1px 0 rgba(255, 255, 255, 0.03);
  --shadow-glow-amber: 0 1px 0 rgba(255, 255, 255, 0.03);
  --shadow-inner-glow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
  /* ── Transitions ── */
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-out-back: cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --duration-fast: 150ms;
  --duration-base: 250ms;
  --duration-slow: 400ms;
}

:global(body) {
  margin: 0;
  /* 商务风：系统无衬线字体，去掉圆体带来的卡通感 */
  font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont,
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", sans-serif;
  background: var(--color-bg-deep);
  color: var(--color-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

:global(button),
:global(input) {
  font: inherit;
}

:global(#app) {
  min-height: 100vh;
}

.app-shell {
  min-height: 100vh;
  padding: 24px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(165deg, #070a14 0%, #0a1020 25%, #080d1c 50%, #0a1020 75%, #070a14 100%);
  background-size: 400% 400%;
  animation: bgShift 24s ease-in-out infinite;
}
/* Subtle grain texture overlay */
.app-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.028;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.bg-canvas {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  /* 商务风：背景只作极淡的质感层，不抢内容 */
  opacity: 0.35;
}

.app-shell::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
}
/* 蓝调光晕 — 左上 */
.app-shell::after {
  width: 820px; height: 820px;
  background: radial-gradient(circle, rgba(74, 140, 255, 0.14) 0%, rgba(74, 140, 255, 0.05) 35%, transparent 70%);
  top: -320px; left: -280px;
  animation: orb1 20s ease-in-out infinite;
}
/* 金调光晕 — 右下 */
.workspace::before {
  content: "";
  position: fixed;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
  width: 640px; height: 640px;
  background: radial-gradient(circle, rgba(201, 162, 39, 0.12) 0%, rgba(201, 162, 39, 0.04) 40%, transparent 70%);
  bottom: -280px; right: -220px;
  animation: orb2 24s ease-in-out infinite;
}

@keyframes bgShift {
  0%, 100% { background-position: 0% 0%; }
  25% { background-position: 100% 0%; }
  50% { background-position: 100% 100%; }
  75% { background-position: 0% 100%; }
}
@keyframes orb1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(140px, 90px) scale(1.22); }
  66% { transform: translate(-50px, 150px) scale(0.82); }
}
@keyframes orb2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-110px, -70px) scale(1.18); }
  66% { transform: translate(70px, -130px) scale(0.88); }
}

.workspace {
  width: min(1760px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr) 370px;
  gap: 22px;
  position: relative;
  z-index: 1;
}

/* 无数字人版：桌面端由三栏收敛为两栏（聊天 + 侧栏），仅宽屏生效 */
@media (min-width: 1181px) {
  .workspace.no-digital-human {
    grid-template-columns: minmax(0, 1fr) 370px;
  }
}

.chat-card,
.sidebar {
  min-height: calc(100vh - 48px);
  height: calc(100vh - 48px);
  background: var(--color-surface);
  backdrop-filter: blur(32px) saturate(1.2);
  -webkit-backdrop-filter: blur(32px) saturate(1.2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color var(--duration-slow) var(--ease-in-out), box-shadow var(--duration-slow) var(--ease-in-out);
}
.chat-card {
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-glow-teal), var(--shadow-lg), var(--shadow-inner-glow);
}
.chat-card:hover {
  border-color: rgba(74, 140, 255, 0.18);
}
.sidebar {
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-glow-amber), var(--shadow-lg), var(--shadow-inner-glow);
}
.sidebar:hover {
  border-color: rgba(74, 140, 255, 0.22);
}

.chat-header,
.sidebar-header {
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--color-border-light);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

/* 品牌行：语桥 YuBridge + 副标语 */
.brand-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.brand-row h1 {
  margin: 0;
  font-size: 24px;
  line-height: 1.2;
}
.brand-en {
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--color-accent);
  opacity: 0.85;
}
.brand-slogan {
  font-size: 12px;
  color: var(--color-text-tertiary);
  padding-left: 10px;
  border-left: 1px solid var(--color-border-light);
}

.chat-header h1,
.sidebar-header h2 {
  margin: 0;
  font-size: 24px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #ffffff 0%, var(--color-accent) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.sidebar-header h2 {
  font-size: 22px;
  background: linear-gradient(135deg, #ffffff 0%, var(--color-warm) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.chat-header p,
.sidebar-header p {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
}

/* 客服信息 */
.service-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.service-avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.service-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  padding: 3px;
  background: conic-gradient(var(--color-success), var(--color-accent), var(--color-warm), var(--color-success));
  animation: avatarSpin 4s linear infinite;
  box-shadow: 0 0 20px var(--color-accent-glow), 0 4px 12px var(--color-success-soft);
}
@keyframes avatarSpin {
  to { transform: rotate(360deg); }
}

.status-indicator {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 14px;
  height: 14px;
  background: var(--color-success);
  border: 3px solid #ffffff;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.service-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.service-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.service-status {
  font-size: 12px;
  color: var(--color-success);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.service-status::before {
  content: '';
  width: 6px;
  height: 6px;
  background: var(--color-success);
  border-radius: 50%;
}

.clear-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-base) var(--ease-out-expo);
  white-space: nowrap;
}
.clear-button:hover {
  background: rgba(251, 113, 133, 0.10);
  border-color: var(--color-danger);
  color: var(--color-danger);
  transform: translateY(-1px);
  box-shadow: 0 4px 18px var(--color-danger-soft);
}

/* 数字人版本切换按钮（带数字人版 / 无数字人版） */
.dh-toggle-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--duration-base) var(--ease-out-expo);
}
.dh-toggle-button:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
  transform: translateY(-1px);
}
.dh-toggle-button.off {
  opacity: 0.7;
}

/* 开发者调试面板：默认折叠，避免把 sender_id 等技术字段直接暴露给最终用户 */
.dev-panel {
  border-bottom: 1px solid var(--color-border-light);
}
.dev-panel-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition: background var(--duration-fast) var(--ease-in-out);
}
.dev-panel-summary::-webkit-details-marker { display: none; }
.dev-panel-summary:hover { background: var(--color-surface-raised); }
.dev-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.dev-panel-title::before {
  content: "▸ ";
  color: var(--color-accent);
  font-size: 11px;
}
.dev-panel[open] .dev-panel-title::before { content: "▾ "; }
.dev-panel-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}
.dev-panel-body {
  padding: 0 24px 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field span {
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.field-row {
  display: flex;
  gap: 12px;
}

.field input,
.composer input {
  width: 100%;
  min-width: 0;
  min-height: 46px;
  padding: 11px 14px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-field);
  color: var(--color-text-primary);
  font-size: 15px;
  line-height: 1.4;
  transition: border-color var(--duration-fast) var(--ease-in-out), box-shadow var(--duration-fast) var(--ease-in-out);
}
.field input::placeholder,
.composer input::placeholder {
  color: var(--color-text-muted);
}
.field input:focus,
.composer input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Turn 卡片样式 */
.turn-card {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: all var(--duration-base) var(--ease-out-expo);
  position: relative;
  overflow: hidden;
  animation: msgEnter 0.4s var(--ease-out-back) both;
}
@keyframes msgEnter {
  from { opacity: 0; transform: translateY(24px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.turn-card::before {
  content: "";
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.04) 50%, transparent 60%);
  transition: left 0.5s ease;
  pointer-events: none;
  z-index: 2;
}
.turn-card:hover::before {
  left: 100%;
}
.turn-card:hover {
  background: var(--color-surface-hover);
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-md), 0 0 0 1px rgba(255,255,255,0.02);
  transform: translateY(-2px);
}

.turn-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--color-border);
}

.turn-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: linear-gradient(135deg, var(--color-accent), var(--color-warm));
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  box-shadow: 0 2px 12px var(--color-accent-glow);
}

.turn-label {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 500;
}

.turn-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  font-weight: 600;
}

/* 头像样式 */
.avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #e5e7eb;
  background: #f3f4f6;
  transition: all var(--duration-base) var(--ease-out-expo);
}

.user-avatar .avatar {
  border: 3px solid transparent;
  background: linear-gradient(#ffffff, #ffffff) padding-box,
              linear-gradient(135deg, var(--color-info), var(--color-accent)) border-box;
  box-shadow: 0 2px 14px var(--color-info-soft);
}

.service-avatar .avatar {
  border-color: var(--color-success);
  box-shadow: 0 2px 10px var(--color-success-soft);
}

.status-dot {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 12px;
  height: 12px;
  background: var(--color-success);
  border: 2px solid #ffffff;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.65;
    transform: scale(1.12);
  }
}

.agent-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-label {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 500;
}

/* 聊天消息的轻量时间标签：跟随角色名下方，弱化为次要信息 */
.msg-time {
  font-size: 11px;
  color: var(--color-text-muted);
  opacity: 0.8;
  font-variant-numeric: tabular-nums;
}

.user-section .agent-name {
  color: var(--color-info);
}

.bot-section .agent-name {
  color: var(--color-success);
}

.role-icon {
  font-size: 16px;
}

.role-label {
  color: var(--color-text-secondary);
}

.user-section .role-label {
  color: var(--color-info);
}

.bot-section .role-label {
  color: var(--color-success);
}

.turn-bubble {
  padding: 14px 18px;
  border-radius: var(--radius-md);
  max-width: 100%;
}

.user-bubble {
  background: linear-gradient(135deg, var(--color-accent), var(--color-accent-strong));
  border: 1px solid transparent;
  color: #ffffff;
  box-shadow: 0 4px 18px var(--color-accent-glow);
  margin-left: auto;
  max-width: 85%;
}

.bot-bubble {
  background: var(--color-surface-field);
  border: 1px solid var(--color-border);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-xs);
}

.bot-messages {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.turn-bubble p {
  margin: 0;
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble p {
  color: #ffffff;
}

/* 历史消息分隔线 */
.history-divider {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  color: var(--color-text-muted);
  font-size: 13px;
  padding: 8px 0;
}

.history-divider::before,
.history-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--color-border-strong);
}

.history-divider span {
  padding: 6px 14px;
  border-radius: var(--radius-full);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  font-size: 12px;
}

.welcome {
  flex-shrink: 0;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.welcome-card {
  position: relative;
  max-width: 480px;
  width: 100%;
  padding: 44px 40px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  text-align: center;
  box-shadow: var(--shadow-glow-teal), var(--shadow-lg);
  overflow: hidden;
  animation: welcomeFloat 0.6s var(--ease-out-back);
}
@keyframes welcomeFloat {
  from { opacity: 0; transform: translateY(36px) scale(0.94); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.welcome-glow {
  position: absolute;
  top: -100px; left: 50%; transform: translateX(-50%);
  width: 350px; height: 350px;
  background: radial-gradient(circle, rgba(74,140,255,0.08) 0%, rgba(74,140,255,0.02) 45%, transparent 70%);
  pointer-events: none;
}
.welcome-avatar-wrapper {
  position: relative;
  display: inline-block;
  margin-bottom: 20px;
}
.welcome-avatar {
  width: 88px; height: 88px;
  border-radius: 50%;
  padding: 4px;
  background: conic-gradient(var(--color-success), var(--color-accent), var(--color-warm), var(--color-success));
  animation: avatarSpin 4s linear infinite;
  box-shadow: 0 0 36px var(--color-accent-glow);
}
.welcome-status-pulse {
  position: absolute;
  bottom: 6px; right: 6px;
  width: 18px; height: 18px;
  background: var(--color-success);
  border: 3px solid var(--color-bg-mid);
  border-radius: 50%;
  animation: pulse 2s infinite;
  box-shadow: 0 0 16px rgba(52, 211, 153, 0.4);
}
.welcome-greeting {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 700;
  background: linear-gradient(135deg, #ffffff, var(--color-accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.welcome-subtitle {
  margin: 0 0 28px;
  color: var(--color-text-secondary);
  font-size: 15px;
}
.welcome-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-bottom: 28px;
}
.welcome-chip {
  padding: 10px 20px;
  border: 1px solid rgba(74, 140, 255, 0.22);
  border-radius: var(--radius-full);
  background: var(--color-accent-soft-bg);
  color: var(--color-accent);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-base) var(--ease-out-expo);
}
.welcome-chip:hover:not(:disabled) {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px var(--color-accent-glow);
}
.welcome-chip:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.welcome-features {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
}

.sidebar-empty {
  margin: auto;
  max-width: 420px;
  color: var(--color-text-muted);
  text-align: center;
  line-height: 1.7;
}

.typing-indicator {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 0 20px;
  animation: msgEnter 0.3s var(--ease-out-expo);
}
.avatar-small {
  width: 34px; height: 34px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid var(--color-success);
  box-shadow: 0 0 12px rgba(52, 211, 153, 0.25);
}
.typing-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: 20px 20px 20px 6px;
  box-shadow: var(--shadow-sm);
}
.typing-dots {
  display: flex;
  gap: 4px;
  align-items: center;
}
.typing-dots span {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: dotBounce 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(1) { animation-delay: 0s; }
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30% { transform: translateY(-8px); opacity: 1; }
}
.typing-label {
  font-size: 13px;
  color: var(--color-text-muted);
}

.object-card-price {
  font-size: 15px;
  font-weight: 600;
}

/* ── 状态徽章 ────────────────────────────────────────────── */
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
  border: 1px solid rgba(201, 162, 39, 0.32);
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

/* ── 商品图片（侧边栏） ────────────────────────────────────── */
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

/* ── 对象卡片图片（聊天区） ─────────────────────────────────── */
.object-card-image {
  width: 100%;
  height: 150px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
  border: 1px solid var(--color-border-light);
  background: var(--color-surface-field);
}

/* Turn 卡片中的对象卡片样式调整 */
.turn-bubble .object-card {
  min-width: 200px;
}

.user-bubble .object-card-badge {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.composer button,
.secondary-button,
.tab-button {
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

/* 主按钮（发送）：商务风实心深蓝，作为界面唯一的高饱和焦点 */
.composer button {
  background: var(--color-accent-strong);
  border-color: var(--color-accent-strong);
  color: #ffffff;
  font-weight: 500;
  letter-spacing: 0.04em;
  padding-inline: 22px;
}
.composer button:hover:not(:disabled) {
  background: var(--color-accent);
  border-color: var(--color-accent);
  transform: none;
  box-shadow: var(--shadow-sm);
}
.composer button:active:not(:disabled) {
  background: var(--color-accent-strong);
  transform: none;
}
.composer button:disabled {
  background: var(--color-surface-raised);
  border-color: var(--color-border);
  color: var(--color-text-muted);
  opacity: 1;
}

.composer button:hover:not(:disabled),
.secondary-button:hover:not(:disabled),
.tab-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.composer button:active:not(:disabled),
.secondary-button:active:not(:disabled),
.tab-button:active:not(:disabled) {
  transform: translateY(0);
}

.composer button:disabled,
.secondary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.error-message,
.sidebar-error {
  margin: 0;
  padding: 0 24px 14px;
  color: var(--color-danger);
  font-size: 13px;
  font-weight: 500;
}

.composer {
  flex-shrink: 0;
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface-dim);
}

.composer button {
  min-width: 96px;
  padding-inline: 20px;
  background: linear-gradient(135deg, var(--color-accent), var(--color-accent-strong));
  border-color: transparent;
  color: #f0fdfa;
  box-shadow: 0 14px 28px var(--color-accent-glow);
}
.composer button:hover:not(:disabled) {
  box-shadow: 0 18px 36px var(--color-accent-glow);
  transform: translateY(-2px);
}

.sidebar {
  display: flex;
  flex-direction: column;
}

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
  /* 商务风：扁平化——纯色面，不叠渐变与重投影 */
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
  /* 商务风：不跳动，只做描边与面色变化 */
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

.bot-text-row { display: flex; align-items: flex-start; gap: 8px; }
.bot-text-row p { flex: 1; margin: 0; }
.bot-actions {
  display: flex; gap: 6px; flex-shrink: 0; align-items: center;
}
.tts-button, .copy-button {
  flex-shrink: 0; width: 32px; height: 32px; padding: 0;
  border: 1px solid var(--color-border-light); border-radius: 8px;
  background: var(--color-surface); cursor: pointer;
  font-size: 14px; display: inline-flex; align-items: center; justify-content: center;
  transition: all var(--duration-base) var(--ease-out-expo); color: var(--color-text-muted);
}

/* ── 数字人面板 ── */
.digital-human-panel {
  min-height: calc(100vh - 48px);
  height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-glow-teal), var(--shadow-lg), var(--shadow-inner-glow);
}
.dh-header {
  padding: 24px 20px 14px;
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.dh-header h2 {
  margin: 0;
  font-size: 20px;
  background: linear-gradient(135deg, #ffffff, var(--color-accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.dh-provider {
  font-size: 12px;
  color: var(--color-text-secondary);
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
}
.dh-viewport {
  flex: 1;
  position: relative;
  min-height: 0;
  background: radial-gradient(circle at 50% 35%, rgba(74, 140, 255, 0.07), transparent 70%), #0a1120;
  display: flex;
  align-items: center;
  justify-content: center;
}
#digital-human-sdk {
  width: 100%;
  height: 100%;
}
/* 灵眸云渲染：RTC 视频流铺满视口 */
.dh-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  /* 未推流时保持深色，避免空 video 元素在部分浏览器渲染成白块 */
  background: #05070f;
}

/* 两个厂商容器互斥显示。
   注意：SDK 与视频流都需要容器始终参与布局（有真实宽高），
   所以用 visibility/opacity 控制显隐，而不是 display:none，
   否则魔珐 SDK 可能取不到容器尺寸、灵眸视频流也无法起播。 */
.dh-viewport.is-moxia #digital-human-video { visibility: hidden; opacity: 0; }
.dh-viewport.is-lingmou #digital-human-sdk { visibility: hidden; opacity: 0; }
.dh-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 20px;
}
.dh-placeholder-icon { font-size: 48px; }
.dh-error {
  position: absolute;
  bottom: 12px;
  left: 12px;
  right: 12px;
  font-size: 12px;
  color: var(--color-danger);
  background: var(--color-danger-soft);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
}
.dh-progress {
  height: 5px;
  background: var(--color-surface-field);
}
.dh-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--color-accent), var(--color-info));
  transition: width 0.3s;
}
.dh-footer {
  padding: 14px 20px;
  border-top: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.dh-status {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.dh-footer-btns {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dh-test-btn {
  padding: 7px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out-expo);
}
.dh-test-btn:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent-strong);
}
.dh-test-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.dh-connect-btn {
  padding: 9px 18px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  /* 商务风：实心深蓝，不再用渐变 */
  background: var(--color-accent-strong);
  color: #ffffff;
  font-weight: 500;
  cursor: pointer;
  font-size: 13px;
  letter-spacing: 0.02em;
  transition: background var(--duration-fast) var(--ease-out-expo),
    box-shadow var(--duration-fast) var(--ease-out-expo);
}
.dh-connect-btn:hover:not(:disabled) {
  background: var(--color-accent);
  box-shadow: var(--shadow-sm);
}
.dh-connect-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px var(--color-accent-glow);
}
.dh-connect-btn.danger { background: var(--color-danger); }
.dh-connect-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.tts-button:hover:not(:disabled), .copy-button:hover:not(:disabled) {
  background: var(--color-accent-soft); border-color: var(--color-accent); color: var(--color-accent-strong);
  transform: scale(1.1);
}
.tts-button:disabled, .copy-button:disabled { cursor: not-allowed; opacity: 0.65; }
.tts-button.tts-playing { background: var(--color-accent-soft); border-color: var(--color-accent); color: var(--color-accent-strong); }
.tts-bars {
  display: inline-flex; align-items: flex-end; gap: 3px; height: 16px;
}
.tts-bars span {
  width: 3px;
  background: var(--color-accent);
  border-radius: 2px;
  animation: barBounce 0.6s ease-in-out infinite;
}
.tts-bars span:nth-child(1) { height: 8px; animation-delay: 0s; }
.tts-bars span:nth-child(2) { height: 14px; animation-delay: 0.15s; }
.tts-bars span:nth-child(3) { height: 10px; animation-delay: 0.3s; }
@keyframes barBounce {
  0%, 100% { transform: scaleY(0.5); }
  50% { transform: scaleY(1); }
}
.tts-spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--color-accent-soft); border-top-color: var(--color-accent);
  border-radius: 50%; animation: tts-spin 0.6s linear infinite;
}
@keyframes tts-spin { to { transform: rotate(360deg); } }
.copy-button.copy-done {
  background: var(--color-success-soft);
  border-color: var(--color-success);
  color: var(--color-success);
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border-light);
}
.suggestion-chip {
  padding: 6px 14px;
  border: 1px solid rgba(74, 140, 255, 0.18);
  border-radius: var(--radius-full);
  background: var(--color-accent-soft-bg);
  color: var(--color-accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-base) var(--ease-out-expo);
}
.suggestion-chip:hover:not(:disabled) {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  transform: translateY(-1px);
}
.suggestion-chip:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.full-width {
  width: 100%;
}

.sidebar .secondary-button.full-width {
  min-height: 42px;
}

.sidebar-empty {
  margin: auto;
  max-width: 420px;
  color: var(--color-text-muted);
  text-align: center;
  line-height: 1.7;
}

/* Turn 卡片中的对象卡片样式调整 */
.turn-bubble .object-card {
  min-width: 200px;
}

.user-bubble .object-card-badge {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  /* 移动/平板下聊天是核心，排到最前；数字人面板与侧栏顺延其后 */
  .chat-card { order: 1; }
  .digital-human-panel { order: 2; }
  .sidebar { order: 3; }

  .chat-header {
    flex-direction: column;
  }

  /* 数字人面板在窄屏不再占满整屏高度，避免把聊天挤到视口外 */
  .digital-human-panel {
    min-height: auto;
    height: auto;
  }
  .dh-viewport {
    flex: none;
    height: 360px;
  }

  .sidebar {
    min-height: auto;
    height: auto;
  }
}

@media (max-width: 720px) {
  .app-shell {
    padding: 0;
  }

  .workspace {
    gap: 0;
  }

  .chat-card,
  .sidebar {
    min-height: auto;
    height: auto;
    border-radius: 0;
    border-left: none;
    border-right: none;
  }

  .chat-card {
    min-height: 100vh;
  }

  .message {
    max-width: 100%;
  }

  .composer,
  .field-row {
    flex-direction: column;
    align-items: stretch;
  }
}

/* ───────────────────────────────────────────────────────────────
   登录 / 注册 全屏视图：左品牌展示 + 右表单卡片（蓝色 + 琥珀金）
   ─────────────────────────────────────────────────────────────── */
.auth-screen {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  /* 深蓝色底 + 双光晕（蓝色 / 琥珀金），再叠 BackgroundCanvas 粒子质感 */
  background:
    radial-gradient(1000px 620px at 15% 18%, rgba(74, 140, 255, 0.20), transparent 60%),
    radial-gradient(820px 520px at 86% 82%, rgba(201, 162, 39, 0.14), transparent 55%),
    linear-gradient(135deg, #0f261b 0%, #1a3a2a 55%, #234a35 100%);
  padding: 32px;
}
.auth-layout {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 76px;
  width: 100%;
  max-width: 1000px;
  animation: authFadeUp .6s ease both;
}
/* 左侧品牌展示 */
.auth-brand-panel { flex: 1.15; color: #eaf1fb; min-width: 0; }
.auth-logo-row { display: flex; align-items: center; gap: 16px; }
.auth-logo-mark {
  flex: none;
  width: 58px; height: 58px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 16px;
  font-size: 26px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #2f6fe4, #4a8cff);
  box-shadow: 0 10px 26px rgba(60, 122, 79, 0.45);
}
.auth-logo-text h1 { margin: 0; font-size: 34px; letter-spacing: 3px; color: #f4f8ff; }
.auth-logo-text .brand-en {
  font-size: 14px; color: #c9a227; font-weight: 600; letter-spacing: 1px; margin-left: 6px;
}
.auth-logo-text .brand-slogan { margin: 4px 0 0; font-size: 13.5px; color: #9db4d4; letter-spacing: 1px; }
.auth-gold-line {
  width: 64px; height: 3px; border-radius: 2px;
  margin: 26px 0;
  background: linear-gradient(90deg, #d9b24c, rgba(217, 178, 76, 0));
}
.auth-features { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 20px; }
.auth-features li { display: flex; align-items: flex-start; gap: 14px; }
.feat-icon {
  flex: none; width: 42px; height: 42px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 12px; font-size: 20px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.feat-text b { display: block; font-size: 15px; color: #f4f8ff; }
.feat-text small { display: block; margin-top: 3px; font-size: 12.5px; color: #9db4d4; }
.auth-footnote { margin: 34px 0 0; font-size: 12.5px; color: #7f97ba; }
/* 右侧表单卡片 */
.auth-card {
  flex: none; width: 400px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 20px;
  padding: 36px 34px 30px;
  box-shadow: 0 30px 80px rgba(4, 16, 38, 0.5);
  text-align: center;
  animation: authFadeUp .6s .12s ease both;
}
.auth-tabs {
  display: flex;
  gap: 8px;
  background: #eef2f7;
  border-radius: 11px;
  padding: 4px;
  margin-bottom: 24px;
}
.auth-tabs button {
  flex: 1;
  border: none;
  background: transparent;
  padding: 10px 0;
  border-radius: 8px;
  font-size: 14px;
  color: #6b7a90;
  cursor: pointer;
  transition: all .2s;
}
.auth-tabs button.active {
  background: #fff;
  color: #2f6fe4;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 15px;
  text-align: left;
}
.auth-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #34465c;
  font-weight: 500;
}
.input-wrap { position: relative; }
.input-icon {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  opacity: .72;
  pointer-events: none;
}
.auth-form input {
  width: 100%;
  padding: 12px 14px 12px 40px;
  border: 1px solid #d7deea;
  border-radius: 10px;
  font-size: 14px;
  outline: none;
  transition: border-color .2s, box-shadow .2s;
}
.auth-form input::placeholder { color: #a8b4c6; }
.auth-form input:focus {
  border-color: #4a8cff;
  box-shadow: 0 0 0 3px rgba(74, 140, 255, 0.20);
}
.auth-error {
  margin: 0;
  color: #d6455a;
  font-size: 13px;
  background: #fdeef0;
  padding: 9px 12px;
  border-radius: 9px;
}
.auth-submit {
  margin-top: 4px;
  padding: 13px;
  border: none;
  border-radius: 11px;
  background: linear-gradient(135deg, #2f6fe4, #c9a227);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 4px;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(60, 122, 79, 0.35);
  transition: transform .2s, box-shadow .2s, opacity .2s;
}
.auth-submit:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 14px 30px rgba(201, 162, 39, 0.42);
}
.auth-submit:disabled {
  opacity: .6;
  cursor: not-allowed;
}
.auth-switch {
  margin: 20px 0 0;
  font-size: 13px;
  color: #6b7a90;
}
.auth-switch a {
  color: #4a8cff;
  cursor: pointer;
  font-weight: 600;
  text-decoration: underline;
}
@keyframes authFadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .auth-layout, .auth-card { animation: none; }
}
/* 窄屏：隐藏品牌区，卡片居中 */
@media (max-width: 880px) {
  .auth-layout { justify-content: center; }
  .auth-brand-panel { display: none; }
  .auth-card { width: 100%; max-width: 400px; }
}
/* 聊天页「退出」按钮（与「新对话」并列） */
.logout-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.08);
  color: #e8eef7;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: background .2s;
}
.logout-button:hover {
  background: rgba(255, 255, 255, 0.18);
}
</style>
