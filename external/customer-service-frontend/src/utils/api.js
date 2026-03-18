// 统一的后端请求工具：把「网络不可达」和「响应体无法解析」两类底层错误
// 翻译成用户能看懂的中文提示，避免把浏览器原始异常（如
// "Failed to execute 'json' on 'Response': Unexpected end of JSON input"）
// 直接暴露到界面上。
//
// 背景：vite 代理的后端服务未启动时，代理会返回 500 + 空 body，
// 此时 response.json() 会抛 SyntaxError；后端彻底不可达时 fetch 本身会 reject。
// 两种情况在这里都被收敛为带上下文的友好 Error。

// 安全解析响应 JSON：空 body / 非 JSON 时抛出带 HTTP 状态码上下文的友好错误
export async function parseJsonSafe(response, label = '接口') {
  try {
    return await response.json()
  } catch (e) {
    throw new Error(
      `${label}返回了异常响应（HTTP ${response.status}），后端服务可能未启动或接口异常，请先启动后端后再试。`
    )
  }
}

// fetch + 安全解析二合一：网络层失败（后端不可达 / DNS / CORS）也统一转友好提示
import { getToken } from './auth.js'

export async function fetchJson(url, options = {}, label = '接口') {
  // 自动附带登录令牌：用户登录后，所有请求都带上 Bearer，
  // 后端受保护接口（如 /api/chat）据此鉴权。未登录时 getToken() 为空串，不附加。
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = 'Bearer ' + token

  let response
  try {
    response = await fetch(url, { ...options, headers })
  } catch (e) {
    throw new Error(`无法连接后端服务（${label}），请确认后端已启动并刷新重试。`)
  }
  const data = await parseJsonSafe(response, label)
  return { response, data }
}
