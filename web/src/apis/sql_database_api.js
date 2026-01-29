import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'

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
   * 选择数据库表
   * @param {string} db_id - 数据库ID
   * @param {Object} databaseData - 数据库数据
   * @returns {Promise} - 创建结果
   */
  createChooseDatabaseTables: async (db_id, databaseData) => {
    return apiAdminPost(`/api/sql_database/database/${db_id}/tables/choose`, databaseData)
  },

  /**
   * 创建数据库
   * @param {Object} databaseData - 数据库数据
   * @returns {Promise} - 创建结果
   */
  createDatabase: async (databaseData) => {
    return apiAdminPost('/api/sql_database/database', databaseData)
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
   * @returns {Promise} - 更新结果
   */
  createGraph: async () => {
    return apiAdminPost(`/api/sql_database/databases/neo4j`)
  },
}
