/**
 * 认证相关 API
 */

async function parseErrorDetail(response, fallbackMessage) {
  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    const error = await response.json()
    return error?.detail || fallbackMessage
  }

  const text = (await response.text()).trim()
  return text || fallbackMessage
}

/**
 * 获取 OIDC 配置
 * @returns {Promise<{enabled: boolean, provider_name?: string}>}
 */
async function getOIDCConfig() {
  const response = await fetch('/api/auth/oidc/config')
  if (!response.ok) {
    throw new Error('获取 OIDC 配置失败')
  }
  return response.json()
}

/**
 * 获取 OIDC 登录 URL
 * @param {string} redirectPath - 登录后的重定向路径
 * @returns {Promise<{login_url: string}>}
 */
async function getOIDCLoginUrl(redirectPath = '/') {
  const params = new URLSearchParams({ redirect_path: redirectPath })
  const response = await fetch(`/api/auth/oidc/login-url?${params}`)
  if (!response.ok) {
    const detail = await parseErrorDetail(response, '获取 OIDC 登录地址失败')
    throw new Error(detail)
  }
  return response.json()
}

/**
 * 使用一次性 code 交换 OIDC 登录结果
 * @param {string} code - 一次性登录 code
 * @returns {Promise<{
 *   access_token: string,
 *   token_type: string,
 *   user_id: number,
 *   username: string,
 *   user_id_login: string,
 *   phone_number: string | null,
 *   avatar: string | null,
 *   role: string,
 *   department_id: number | null,
 *   department_name: string | null
 * }>}
 */
async function exchangeOIDCCode(code) {
  const response = await fetch('/api/auth/oidc/exchange-code', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ code })
  })

  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'OIDC 登录失败')
    throw new Error(detail)
  }

  return response.json()
}

export const authApi = {
  getOIDCConfig,
  getOIDCLoginUrl,
  exchangeOIDCCode,
  getSSOConfig,
  ssoLogin,
  changePassword
}

/**
 * 获取 SSO 配置
 * @returns {Promise<{enabled: boolean}>}
 */
async function getSSOConfig() {
  const response = await fetch('/api/auth/sso/config')
  if (!response.ok) {
    throw new Error('获取 SSO 配置失败')
  }
  return response.json()
}

/**
 * SSO 登录
 * @param {string} tenantId - 租户 ID
 * @param {string} token - 认证 token
 * @returns {Promise<{
 *   access_token: string,
 *   token_type: string,
 *   user_id: number,
 *   username: string,
 *   user_id_login: string,
 *   phone_number: string | null,
 *   avatar: string | null,
 *   role: string,
 *   department_id: number | null,
 *   department_name: string | null,
 *   require_password_change: number
 * }>}
 */
async function ssoLogin(tenantId, token) {
  const response = await fetch('/api/auth/sso/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tenant_id: tenantId, token })
  })

  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'SSO 登录失败')
    throw new Error(detail)
  }

  return response.json()
}

/**
 * 修改密码
 * @param {string} newPassword - 新密码
 * @returns {Promise<{success: boolean, message: string}>}
 */
async function changePassword(newPassword) {
  const response = await fetch('/api/auth/change-password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ new_password: newPassword })
  })

  if (!response.ok) {
    const detail = await parseErrorDetail(response, '修改密码失败')
    throw new Error(detail)
  }

  return response.json()
}
