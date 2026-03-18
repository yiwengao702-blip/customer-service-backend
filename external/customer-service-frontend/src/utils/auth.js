// 登录态工具：token 与用户信息的本地持久化（localStorage）。
// 仅负责「存取」，不负责网络请求；网络调用由 App.vue 通过 fetchJson 完成。

const TOKEN_KEY = 'cs_token'
const USER_KEY = 'cs_user'

// 读取当前登录令牌（空字符串表示未登录）
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

// 登录成功后保存令牌与用户信息
export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user || null))
}

// 退出登录：清空本地登录态
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 读取本地缓存的用户信息（用于刷新页面后先展示，再异步校验令牌有效性）
export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

// 是否已登录（仅看本地是否存了令牌，令牌有效性由 /api/auth/me 最终裁决）
export function isLoggedIn() {
  return Boolean(getToken())
}
