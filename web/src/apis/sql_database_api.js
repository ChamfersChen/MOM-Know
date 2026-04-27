import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'
import { JSEncrypt } from 'jsencrypt'

const SQL_PASSWORD_ALGORITHM = 'RSA-OAEP-256'

function pemToArrayBuffer(pem) {
  const base64 = pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s+/g, '')
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

async function encryptPassword(password, publicKeyPem) {
  if (!window.crypto?.subtle) {
    const encryptor = new JSEncrypt()
    encryptor.setPublicKey(publicKeyPem)
    const encrypted = encryptor.encrypt(password)
    if (!encrypted) {
      throw new Error('浏览器 RSA 加密失败，请检查公钥配置')
    }
    return encrypted
  }

  const keyBuffer = pemToArrayBuffer(publicKeyPem)
  const publicKey = await window.crypto.subtle.importKey(
    'spki',
    keyBuffer,
    {
      name: 'RSA-OAEP',
      hash: 'SHA-256'
    },
    false,
    ['encrypt']
  )
  const encoded = new TextEncoder().encode(password)
  const encrypted = await window.crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, encoded)
  const encryptedBytes = new Uint8Array(encrypted)
  let binary = ''
  encryptedBytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  return btoa(binary)
}

async function buildSecureDatabasePayload(databaseData) {
  const connectInfo = databaseData?.connect_info || {}
  if (!connectInfo.password) {
    return databaseData
  }

  const keyPayload = await apiAdminGet('/api/sql_database/password/public_key')
  if (keyPayload?.algorithm !== SQL_PASSWORD_ALGORITHM || !keyPayload?.public_key) {
    throw new Error('服务端密码加密配置异常，请联系管理员')
  }

  const encryptedPassword = await encryptPassword(connectInfo.password, keyPayload.public_key)
  return {
    ...databaseData,
    connect_info: {
      ...connectInfo,
      password: undefined,
      password_encrypted: encryptedPassword
    }
  }
}

/**
 * 知识库管理API模块
 * 包含数据库管理、文档管理、查询接口等功能
 */

// =============================================================================
// === 数据库管理分组 ===
// =============================================================================

export const databaseApi = {
  /**
   * 获取所有数据库列表
   * @returns {Promise} - 数据库列表
   */
  getDatabases: async () => {
    return apiAdminGet('/api/sql_database/databases')
  },

  /**
   * 创建数据库
   * @param {Object} databaseData - 数据库数据
   * @returns {Promise} - 创建结果
   */
  checkConnection: async (databaseData) => {
    const securePayload = await buildSecureDatabasePayload(databaseData)
    return apiAdminPost('/api/sql_database/check_connection', securePayload)
  },

  /**
   * 创建数据库
   * @param {Object} databaseData - 数据库数据
   * @returns {Promise} - 创建结果
   */
  createDatabase: async (databaseData) => {
    const securePayload = await buildSecureDatabasePayload(databaseData)
    return apiAdminPost('/api/sql_database/database', securePayload)
  },

  deleteConnection: async (dbId) => {
    return apiAdminDelete(`/api/sql_database/database/${dbId}`)
  },

  /**
   * 获取知识库详细信息
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 知识库信息
   */
  getDatabaseInfo: async (dbId) => {
    return apiAdminGet(`/api/sql_database/database/${dbId}`)
  },

  /**
   * 删除知识库
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 删除结果
   */
  deleteDatabase: async (dbId) => {
    return apiAdminDelete(`/api/sql_database/database/${dbId}`)
  },
  /**
   * 更新知识库信息
   * @param {string} dbId - 知识库ID
   * @param {Object} updateData - 更新数据
   * @returns {Promise} - 更新结果
   */
  updateDatabase: async (dbId, updateData) => {
    return apiAdminPut(`/api/sql_database/database/${dbId}`, updateData)
  },

  /**
   * 更新知识库信息
   * @param {string} dbId - 知识库ID
   * @param {Object} updateData - 更新数据
   * @returns {Promise} - 更新结果
   */
  updateTables: async (dbId, tableInfo) => {
    return apiAdminPut(`/api/sql_database/database/${dbId}/tables`, tableInfo)
  },
  /**
   * 根据知识库配置信息，创建知识图谱
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  createGraph: async (params = {}) => {
    return apiAdminPost(`/api/sql_database/databases/neo4j`, params)
  },

  /**
   * 获得配置术语列表
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  getAllTerms: async () => {
    return apiAdminGet(`/api/sql_database/term`)
  },
  getTermsByHostPort: async (host, port) => {
    return apiAdminGet(`/api/sql_database/term/${host}/${port}`)
  },
  /**
   * 关闭、启用术语
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  enableTerm: async (termId, enable) => {
    return apiAdminPut(`/api/sql_database/term/${termId}/enable/${enable}`)
  },
  /**
   * 删除术语
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  deleteTerm: async (termId) => {
    return apiAdminDelete(`/api/sql_database/term/${termId}`)
  },
  /**
   * 更新术语
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  updateTerm: async (updateData) => {
    return apiAdminPut(`/api/sql_database/term`, updateData)
  },
  /**
   * 新增术语
   * @param {Object} params - 数据库分组信息
   * @returns {Promise} - 更新结果
   */
  addTerm: async (termData) => {
    return apiAdminPost(`/api/sql_database/term`, termData)
  },
  /**
   * 获取所有sql例子
   * @returns {Promise} - 获取结果
   */
  getAllExamples: async () => {
    return apiAdminGet(`/api/sql_database/sqls`)
  },

  getSqlExamplesByHostPort: async (host, port) => {
    return apiAdminGet(`/api/sql_database/sqls/${host}/${port}`)
  },
  enableExample: async (exampleId, enable) => {
    return apiAdminPut(`/api/sql_database/sql/${exampleId}/enable/${enable}`)
  },
  deleteExample: async (exampleId) => {
    return apiAdminDelete(`/api/sql_database/sql/${exampleId}`)
  },
  updateExample: async (updateData) => {
    return apiAdminPut(`/api/sql_database/sql`, updateData)
  },
  addExample: async (exampleData) => {
    return apiAdminPost(`/api/sql_database/sql`, exampleData)
  },
}
