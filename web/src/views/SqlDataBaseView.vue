<template>
  <div class="database-container layout-container">
    <HeaderComponent title="数据数据源" :loading="dbState.listLoading">
      <template #actions>
        <a-button type="primary" @click="handleCreateNewDatasource"> 创建数据源 </a-button>
        <a-button @click="navigateToGraph"> 查看图谱 </a-button>
      </template>
    </HeaderComponent>

    <a-modal
      :open="state.openNewDatabaseModel"
      title="创建数据源"
      :confirm-loading="dbState.creating"
      @ok="handleCreateDatabase"
      @cancel="cancelCreateDatabase"
      class="new-database-modal"
      width="800px"
      destroyOnClose
    >
      <!-- 步骤条 -->
      <a-steps :current="state.currentStep" size="small" class="steps-container">
        <a-step title="选择数据源" />
        <a-step title="配置连接信息" />
      </a-steps>

      <!-- 第一步：选择数据源类型 -->
      <div v-show="state.currentStep === 0" class="step-content">
        <h3>选择数据库类型<span style="color: var(--error-color)">*</span></h3>
        <div class="db-type-cards">
          <div
            v-for="dbType in supportedDbTypes"
            :key="dbType.name"
            class="db-type-card"
            :class="{ active: newDatabase.db_type === dbType.type }"
            @click="newDatabase.db_type = dbType.type"
          >
            <img class="db-type-icon" :src="dbType.img" :alt="dbType.name" />
            <div class="db-type-info">
              <h4>{{ dbType.name }}</h4>
              <p>{{ dbType.description }}</p>
            </div>
            <div v-if="newDatabase.db_type === dbType.type" class="check-icon">
              <CheckCircleFilled />
            </div>
          </div>
        </div>
      </div>

      <!-- 第二步：配置连接信息 -->
      <div v-show="state.currentStep === 1" class="step-content">
        <div class="connection-config">
          <a-form layout="vertical" class="config-form">
            <a-form-item label="数据源名称" required>
              <a-input v-model:value="newDatabase.name" placeholder="请输入数据源名称" size="large" />
            </a-form-item>
            
            <div class="config-row">
              <a-form-item label="类型" required>
                <a-select v-model:value="newDatabase.db_type" size="large" style="width: 150px">
                  <a-select-option v-for="db in supportedDbTypes" :key="db.type" :value="db.type">
                    {{ db.name }}
                  </a-select-option>
                </a-select>
              </a-form-item>
              
              <a-form-item label="主机地址" required class="flex-1">
                <a-input v-model:value="connectInfo.host" placeholder="例如：127.0.0.1" size="large" />
              </a-form-item>
              
              <a-form-item label="端口" required>
                <a-input-number 
                  v-model:value="connectInfo.port" 
                  :min="1" 
                  :max="65535" 
                  size="large" 
                  style="width: 100px" 
                />
              </a-form-item>
            </div>
            
            <div class="config-row">
              <a-form-item label="用户名" required class="flex-1">
                <a-input v-model:value="connectInfo.user" placeholder="请输入用户名" size="large" />
              </a-form-item>
              
              <a-form-item label="密码" required class="flex-1">
                <a-input-password v-model:value="connectInfo.password" placeholder="请输入密码" size="large" />
              </a-form-item>
            </div>
            
            <a-form-item label="数据库名" required v-if="newDatabase.db_type !== 'oracle'">
              <a-input v-model:value="connectInfo.database" placeholder="请输入数据库名称" size="large" />
            </a-form-item>
            
            <a-form-item label="服务名" required v-if="newDatabase.db_type === 'oracle'">
              <a-input v-model:value="connectInfo.serviceName" placeholder="请输入服务名" size="large" />
            </a-form-item>
            
            <a-form-item label="描述">
              <a-textarea
                v-model:value="newDatabase.description"
                placeholder="请输入数据源描述（可选）"
                :auto-size="{ minRows: 2, maxRows: 3 }"
              />
            </a-form-item>
          </a-form>
        </div>
        
        <!-- 共享配置 -->
        <div class="share-config">
          <h3>共享设置</h3>
          <ShareConfigForm v-model="shareConfig" :auto-select-user-dept="true" />
        </div>
      </div>

      <template #footer>
        <a-button v-if="state.currentStep === 1" key="prev" @click="state.currentStep = 0">
          上一步
        </a-button>
        <a-button key="back" @click="cancelCreateDatabase" danger>取消</a-button>
        <a-button
          v-if="state.currentStep === 1"
          key="check"
          type="dashed"
          :loading="dbState.checking"
          @click="handleCheckConnection"
        >
          校验
        </a-button>
        <a-button
          v-if="state.currentStep === 0"
          key="next"
          type="primary"
          @click="state.currentStep = 1"
        >
          下一步
        </a-button>
        <a-button
          v-else
          key="submit"
          type="primary"
          :loading="dbState.creating"
          @click="handleCreateDatabase"
        >
          创建
        </a-button>
      </template>
    </a-modal>

    <!-- 加载状态 -->
    <div v-if="dbState.listLoading" class="loading-container">
      <a-spin size="large" />
      <p>正在加载知识库...</p>
    </div>

    <!-- 空状态显示 -->
    <div v-else-if="!databases || databases.length === 0" class="empty-state">
      <h3 class="empty-title">暂无数据源</h3>
      <p class="empty-description">创建您的第一个数据源</p>
      <a-button type="primary" size="large" @click="state.openNewDatabaseModel = true">
        <template #icon>
          <PlusOutlined />
        </template>
        创建数据源
      </a-button>
    </div>

    <!-- 数据库列表 - 分组显示 -->
    <div v-else class="databases-group">
      <div
        v-for="group in groupedDatabases"
        :key="group.key"
        class="database-group"
        :class="{ 
          'is-imported': selectedGraphGroupsStore.isGroupSelected(group),
          'is-modified': selectedGraphGroupsStore.isGroupSelected(group) && selectedGraphGroupsStore.hasModifiedTables(group)
        }"
      >
        <div class="group-header">
          <div class="group-info">
            <span class="group-type">{{ getDbTypeLabel(group.dbType) }}</span>
            <span class="group-divider">|</span>
            <span class="group-address">{{ group.host }}:{{ group.port }}</span>
            <a-tag class="group-count">{{ group.databases.length }} 个数据源</a-tag>
            <a-tag v-if="selectedGraphGroupsStore.isGroupSelected(group) && selectedGraphGroupsStore.hasModifiedTables(group)" color="orange">
              <ExclamationCircleFilled /> 请同步更新
            </a-tag>
            <a-tag v-else-if="selectedGraphGroupsStore.isGroupSelected(group)" color="green">
              <CheckCircleFilled /> 已导入图谱
            </a-tag>
          </div>
          <div class="group-actions">
            <a-button type="primary" size="small" @click="handleAddToGroup(group)">
              <PlusOutlined /> 添加
            </a-button>
            <a-button size="small" @click="navigateToSqlExample(group)">
              <CodeOutlined /> SQL示例库
            </a-button>
            <a-button size="small" @click="navigateToTermConfig(group)">
              <SettingOutlined /> 术语配置
            </a-button>
            <a-button 
              class="graph-btn" 
              size="small" 
              @click="uploadToNeo4j(group)"
            >
              {{ selectedGraphGroupsStore.isGroupSelected(group) ? '重新导入' : '选择数据源并导入图谱' }}
            </a-button>
          </div>
        </div>
        
        <div class="group-content">
          <div
            v-for="database in group.databases"
            :key="database.db_id"
            class="database dbcard"
            @click="navigateToDatabase(database.db_id)"
          >
            <div class="top">
              <div class="icon">
                <component :is="getKbTypeIcon(database.db_type || 'mysql')" />
              </div>
              <div class="info">
                <h3>{{ database.name }}</h3>
                <p>
                  <span>{{ database.tables ? Object.values(database.tables).filter(t => t.is_choose).length : 0 }}/{{ database.tables ? Object.keys(database.tables).length : 0 }} 文件</span>
                  <span class="created-time-inline" v-if="database.created_at">
                    {{ formatCreatedTime(database.created_at) }}
                  </span>
                </p>
              </div>
            </div>
            <p class="description">{{ database.description || '暂无描述' }}</p>
            <!-- <div class="tags">
              <a-tag color="blue" v-if="database.embed_info?.name">
                {{ database.embed_info.name }}
              </a-tag>
              <a-tag
                :color="getKbTypeColor(database.db_type || 'lightrag')"
                class="kb-type-tag"
                size="small"
              >
                {{ getKbTypeLabel(database.db_type || 'lightrag') }}
              </a-tag>
            </div> -->
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed, shallowRef } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/sql_database'
import { useSelectedGraphGroupsStore } from '@/stores/selectedGraphGroups'
import { LockOutlined, InfoCircleOutlined, PlusOutlined, CheckCircleFilled, ExclamationCircleFilled, DatabaseOutlined, FileTextOutlined, CloudServerOutlined, SettingOutlined, CodeOutlined } from '@ant-design/icons-vue'
import { databaseApi } from '@/apis/sql_database_api'
import { dsTypeWithImg } from '@/composables/ds-type'
import HeaderComponent from '@/components/HeaderComponent.vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue'
import ShareConfigForm from '@/components/ShareConfigForm.vue'
import dayjs, { parseToShanghai } from '@/utils/time'
import AiTextarea from '@/components/AiTextarea.vue'
import { getKbTypeLabel, getKbTypeIcon, getKbTypeColor } from '@/utils/kb_utils'
import { message, Modal } from 'ant-design-vue'

const route = useRoute()
const router = useRouter()
const configStore = useConfigStore()
const databaseStore = useDatabaseStore()
const selectedGraphGroupsStore = useSelectedGraphGroupsStore()
// 使用 store 的状态
const { databases, state: dbState } = storeToRefs(databaseStore)

const state = reactive({
  openNewDatabaseModel: false,
  currentStep: 0,
  importing: false
})

const groupedDatabases = computed(() => {
  const groups = {}
  
  databases.value.forEach(db => {
    const dbType = db.db_type || 'unknown'
    const connectInfo = db.connect_info || {}
    const host = connectInfo.host || 'unknown'
    const port = connectInfo.port || 'unknown'
    const key = `${dbType}:${host}:${port}`
    
    if (!groups[key]) {
      groups[key] = {
        key,
        dbType,
        host,
        port,
        databases: []
      }
    }
    groups[key].databases.push(db)
  })
  
  return Object.values(groups).sort((a, b) => {
    if (a.dbType !== b.dbType) return a.dbType.localeCompare(b.dbType)
    if (a.host !== b.host) return a.host.localeCompare(b.host)
    return a.port - b.port
  })
})

const getDbTypeLabel = (type) => {
  const typeMap = {
    'mysql': 'MySQL',
    // 'pg': 'PostgreSQL',
    // 'oracle': 'Oracle',
    // 'sqlServer': 'SQL Server',
    // 'ck': 'ClickHouse',
    // 'dm': '达梦',
    // 'doris': 'Apache Doris',
    // 'redshift': 'AWS Redshift',
    // 'es': 'Elasticsearch',
    // 'kingbase': 'Kingbase'
  }
  return typeMap[type] || type
}
const supportedDbTypes = shallowRef(dsTypeWithImg)

// 共享配置状态（用于提交数据）
const shareConfig = ref({
  is_shared: true,
  accessible_department_ids: []
})

const connectInfo = reactive({
  host: '127.0.0.1',
  port: 3306,
  user: 'root',
  password: '',
  database: 'mom',
  serviceName: ''
})

const getDefaultPort = (dbType) => {
  const db = supportedDbTypes.value.find(d => d.value === dbType)
  return db?.defaultPort || ""
}

const createEmptyDatabaseForm = () => ({
  name: '',
  description: '',
  db_type: 'mysql',
})

const newDatabase = reactive(createEmptyDatabaseForm())

const resetNewDatabase = () => {
  Object.assign(newDatabase, createEmptyDatabaseForm())
  state.currentStep = 0
  const defaultPort = getDefaultPort(newDatabase.db_type)
  connectInfo.host = '127.0.0.1'
  connectInfo.port = defaultPort
  connectInfo.user = 'root'
  connectInfo.password = ''
  connectInfo.database = 'mom'
  connectInfo.serviceName = ''
  shareConfig.value = {
    is_shared: true,
    accessible_department_ids: []
  }
}

const cancelCreateDatabase = () => {
  state.openNewDatabaseModel = false
  resetNewDatabase()
}

// 格式化创建时间
const formatCreatedTime = (createdAt) => {
  if (!createdAt) return ''
  const parsed = parseToShanghai(createdAt)
  if (!parsed) return ''

  const today = dayjs().startOf('day')
  const createdDay = parsed.startOf('day')
  const diffInDays = today.diff(createdDay, 'day')

  if (diffInDays === 0) {
    return '今天创建'
  }
  if (diffInDays === 1) {
    return '昨天创建'
  }
  if (diffInDays < 7) {
    return `${diffInDays} 天前创建`
  }
  if (diffInDays < 30) {
    const weeks = Math.floor(diffInDays / 7)
    return `${weeks} 周前创建`
  }
  if (diffInDays < 365) {
    const months = Math.floor(diffInDays / 30)
    return `${months} 个月前创建`
  }
  const years = Math.floor(diffInDays / 365)
  return `${years} 年前创建`
}

// // 导入Neo4j图数据库
// const uploadToNeo4j = async () => {
//   // 根据databases info上传图数据库
//   console.log('>>> upload to neo4j: ', databaseStore.databases)
//   const confirmed = window.confirm('即将把当前所有数据库中的表结构导入 Neo4j 并创建知识图谱，是否继续？')
//   if (!confirmed) return
//   try{
//     const ret = await databaseApi.createGraph()
//     if(ret.code === 0){ 
//       message.success('知识图谱创建成功')
//     }else{
//       message.error('知识图谱创建失败')
//     }
//   }catch(e){
//     console.log('>>> upload to neo4j error: ', e)
//     message.error('知识图谱创建失败')
//   }
// }

// 构建请求数据（只负责表单数据转换）
const buildCheckConnectionRequestData = () => {
  const requestData = {
    database_name: connectInfo.database,
    db_type: newDatabase.db_type,
  }
  // 添加共享配置
  requestData.share_config = {
    is_shared: shareConfig.value.is_shared,
    accessible_departments: shareConfig.value.is_shared
      ? []
      : shareConfig.value.accessible_department_ids || []
  }
  requestData.connect_info = {
    host: connectInfo.host,
    port: connectInfo.port,
    username: connectInfo.user,
    password: connectInfo.password,
    database: connectInfo.database,
  }
  return requestData
}
// 校验按钮处理
const handleCheckConnection = async () => {
  const requestData = buildCheckConnectionRequestData()
  try {
    await databaseStore.checkConnection(requestData)
  } catch (error) {
    // 错误已在 store 中处理
  }
}

// 构建请求数据（只负责表单数据转换）
const buildRequestData = () => {
  const requestData = {
    database_name: connectInfo.database,
    description: newDatabase.description?.trim() || '',
    db_type: newDatabase.db_type,
  }
  // 添加共享配置
  requestData.share_config = {
    is_shared: shareConfig.value.is_shared,
    accessible_departments: shareConfig.value.is_shared
      ? []
      : shareConfig.value.accessible_department_ids || []
  }
  requestData.connect_info = {
    host: connectInfo.host,
    port: connectInfo.port,
    username: connectInfo.user,
    password: connectInfo.password,
    database: connectInfo.database,
  }
  return requestData
}

// 创建按钮处理
const handleCreateDatabase = async () => {
  const requestData = buildRequestData()
  try {
    const result = await databaseStore.createDatabase(requestData)
    if (result && result.db_id) {
      selectedGraphGroupsStore.markTableModified(result.db_id, 'database_added')
    }
    resetNewDatabase()
    state.openNewDatabaseModel = false
  } catch (error) {
    // 错误已在 store 中处理
  }
}

const navigateToDatabase = (databaseId) => {
  router.push({ path: `/sqldatabase/${databaseId}` })
}

const navigateToGraph = () => {
  router.push({ path: '/graph' })
}

const navigateToSqlExample = (group) => {
  router.push({ 
    path: '/sqldatabase/sql-example', 
    query: { 
      dbType: group.dbType, 
      host: group.host, 
      port: group.port 
    } 
  })
}

const navigateToTermConfig = (group) => {
  router.push({ 
    path: '/sqldatabase/term-config', 
    query: { 
      dbType: group.dbType, 
      host: group.host, 
      port: group.port 
    } 
  })
}

const handleAddToGroup = (group) => {
  state.openNewDatabaseModel = true
  state.currentStep = 1
  newDatabase.db_type = group.dbType
  connectInfo.host = group.host
  connectInfo.port = group.port
  newDatabase.name = ''
  newDatabase.description = ''
  connectInfo.user = 'root'
  connectInfo.password = ''
  connectInfo.database = ''
  connectInfo.serviceName = ''
}

const handleCreateNewDatasource = () => {
  state.openNewDatabaseModel = true
  state.currentStep = 0
  newDatabase.db_type = 'mysql'
  connectInfo.host = '127.0.0.1'
  connectInfo.port = 3306
  newDatabase.name = ''
  newDatabase.description = ''
  connectInfo.user = 'root'
  connectInfo.password = ''
  connectInfo.database = ''
  connectInfo.serviceName = ''
}

const uploadToNeo4j = async (group) => {
  console.log('>>> upload to neo4j for group: ', group)
  console.log('>>> databases: ', databaseStore.databases)
  
  const action = selectedGraphGroupsStore.isGroupSelected(group) ? '重新导入' : '导入'
  const groupName = `${getDbTypeLabel(group.dbType)} - ${group.host}:${group.port}`
  const dbCount = group.databases.length
  
  const totalSelectedTables = group.databases.reduce((sum, db) => {
    const tables = db.tables || {}
    const selected = Object.values(tables).filter(t => t.is_choose).length
    return sum + selected
  }, 0)
  
  if (totalSelectedTables === 0) {
    message.warning('该分组下没有选择任何数据表，请先在数据源中选择需要导入的表后再进行导入')
    return
  }
  
  Modal.confirm({
    title: `${action}图谱`,
    content: `即将${action}「${groupName}」分组下已选择的 ${totalSelectedTables} 张数据表导入 Neo4j 并创建知识图谱。该分组下共有 ${dbCount} 个数据源。`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      state.importing = true
      try {
        const ret = await databaseApi.createGraph(group.databases)
        if (ret.code === 0) {
          selectedGraphGroupsStore.selectGroup(group)
          message.success(`「${groupName}」已${action}图谱`)
        } else {
          message.error('知识图谱创建失败')
        }
      } catch (e) {
        console.log('>>> upload to neo4j error: ', e)
        message.error('知识图谱创建失败')
      } finally {
        state.importing = false
      }
    }
  })
}

watch(
  () => route.path,
  (newPath) => {
    if (newPath === '/sqldatabase') {
      databaseStore.loadDatabases()
    }
  }
)

watch(
  () => newDatabase.db_type,
  (newType) => {
    connectInfo.port = getDefaultPort(newType)
    connectInfo.database = ''
    connectInfo.serviceName = ''
    connectInfo.user = 'root'
    connectInfo.password = ''
  }
)

onMounted(() => {
  // loadSupportedKbTypes()
  databaseStore.loadDatabases()
  console.log(">>> Databases: ", databaseStore.databases)
})
</script>

<style lang="less" scoped>
.new-database-modal {
  .steps-container {
    margin-bottom: 24px;
  }

  .step-content {
    min-height: 300px;
  }

  .connection-config {
    .config-form {
      .config-row {
        display: flex;
        gap: 16px;
        margin-bottom: 0;
        
        .full-width {
          width: 100%;
          
          :deep(.ant-form-item-control-wrapper) {
            width: 100%;
          }
        }
        
        .fixed-width {
          width: auto;
        }
        
        .flex-1 {
          flex: 1;
          min-width: 150px;
        }
        
        .dynamic-field {
          flex: 1;
          min-width: 150px;
          
          &.full-width {
            flex: 0 0 100%;
          }
        }
      }
      
      .ant-form-item {
        margin-bottom: 0;
      }
      
      :deep(.ant-form-item-label) {
        padding-bottom: 4px;
        
        > label {
          font-size: 13px;
          color: var(--gray-700);
        }
      }
    }
  }
  
  .share-config {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid var(--gray-200);
    
    h3 {
      margin: 0 0 12px 0;
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-800);
    }
  }

  .kb-type-guide {
    margin: 12px 0;
  }

  .db-type-cards {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 16px;

    .db-type-card {
      border: 2px solid var(--gray-150);
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.3s ease;
      background: var(--gray-0);
      position: relative;
      display: flex;
      align-items: center;
      gap: 16px;

      &:hover {
        border-color: var(--main-color);
        background: var(--main-10);
      }

      &.active {
        border-color: var(--main-color);
        background: var(--main-10);

        .db-type-icon {
          color: var(--main-color);
        }
      }

      .db-type-icon {
        width: 48px;
        height: 48px;
        font-size: 28px;
        color: var(--gray-600);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .db-type-info {
        flex: 1;

        h4 {
          margin: 0 0 4px 0;
          font-size: 16px;
          font-weight: 600;
          color: var(--gray-800);
        }

        p {
          margin: 0;
          font-size: 13px;
          color: var(--gray-600);
        }
      }

      .check-icon {
        color: var(--main-color);
        font-size: 20px;
      }
    }
  }

  .privacy-config {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
  }

  .kb-type-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin: 16px 0;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
      gap: 12px;
    }

    .kb-type-card {
      border: 2px solid var(--gray-150);
      border-radius: 12px;
      padding: 16px;
      cursor: pointer;
      transition: all 0.3s ease;
      background: var(--gray-0);
      position: relative;
      overflow: hidden;

      &:hover {
        border-color: var(--main-color);
      }

      &.active {
        border-color: var(--main-color);
        background: var(--main-10);
        .type-icon {
          color: var(--main-color);
        }
      }

      .card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;

        .type-icon {
          width: 24px;
          height: 24px;
          color: var(--main-color);
          flex-shrink: 0;
        }

        .type-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--gray-800);
        }
      }

      .card-description {
        font-size: 13px;
        color: var(--gray-600);
        line-height: 1.5;
        margin-bottom: 0;
        // min-height: 40px;
      }

      .deprecated-badge {
        background: var(--color-error-100);
        color: var(--color-error-600);
        font-size: 10px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: auto;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        cursor: help;
        transition: all 0.2s ease;

        &:hover {
          background: var(--color-error-200);
          color: var(--color-error-700);
        }
      }
    }
  }

  .chunk-config {
    margin-top: 16px;
    padding: 12px 16px;
    background-color: var(--gray-25);
    border-radius: 6px;
    border: 1px solid var(--gray-150);

    h3 {
      margin-top: 0;
      margin-bottom: 12px;
      color: var(--gray-800);
    }

    .chunk-params {
      display: flex;
      flex-direction: column;
      gap: 12px;

      .param-row {
        display: flex;
        align-items: center;
        gap: 12px;

        label {
          min-width: 80px;
          font-weight: 500;
          color: var(--gray-700);
        }

        .param-hint {
          font-size: 12px;
          color: var(--gray-500);
          margin-left: 8px;
        }
      }
    }
  }
}

.database-container {
  .databases {
    .database {
      .top {
        .info {
          h3 {
            display: block;
          }
        }
      }
    }
  }
}
.database-actions,
.document-actions {
  margin-bottom: 20px;
}
.databases {
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.databases-group {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;

  .database-group {
    background: var(--gray-0);
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    overflow: hidden;
    transition: all 0.3s ease;

    &.is-imported {
      border-color: var(--color-success-300);
      box-shadow: 0 0 0 2px var(--color-success-100);
      
      .group-header {
        background: var(--color-success-50);
        border-bottom-color: var(--color-success-200);
      }
    }

    &.is-modified {
      border-color: #fa8c16;
      box-shadow: 0 0 0 2px #ffe7ba;
      
      .group-header {
        background: #fff7e6;
        border-bottom-color: #ffd591;
      }
    }

    .group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 20px;
      background: var(--gray-50);
      border-bottom: 1px solid var(--gray-200);

      .group-info {
        display: flex;
        align-items: center;
        gap: 12px;

        .group-type {
          font-size: 16px;
          font-weight: 600;
          color: var(--gray-800);
        }

        .group-divider {
          color: var(--gray-400);
        }

        .group-address {
          font-size: 14px;
          color: var(--gray-600);
          font-family: monospace;
        }

        .group-count {
          margin-left: 8px;
        }
      }

      .group-actions {
        display: flex;
        gap: 8px;
        align-items: center;

        .graph-btn {
          white-space: normal;
          height: auto;
          line-height: 1.25;
          padding: 4px 12px;
        }
      }
    }

    .group-content {
      padding: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 16px;
    }
  }
}

.database,
.graphbase {
  background: linear-gradient(145deg, var(--gray-0) 0%, var(--gray-10) 100%);
  box-shadow: 0px 1px 2px 0px var(--shadow-2);
  border: 1px solid var(--gray-100);
  transition: none;
  position: relative;
}

.dbcard,
.database {
  width: 100%;
  padding: 10px;
  border-radius: 16px;
  // height: 156px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  position: relative; // 为绝对定位的锁定图标提供参考
  overflow: hidden;

  .private-lock-icon {
    position: absolute;
    top: 20px;
    right: 20px;
    color: var(--gray-600);
    background: linear-gradient(135deg, var(--gray-0) 0%, var(--gray-100) 100%);
    font-size: 12px;
    border-radius: 8px;
    padding: 6px;
    z-index: 2;
    box-shadow: 0px 2px 4px var(--shadow-2);
    border: 1px solid var(--gray-100);
  }

  .top {
    display: flex;
    align-items: center;
    height: 54px;
    margin-bottom: 14px;

    .icon {
      width: 54px;
      height: 54px;
      font-size: 26px;
      margin-right: 14px;
      display: flex;
      justify-content: center;
      align-items: center;
      background: var(--main-30);
      border-radius: 12px;
      border: 1px solid var(--gray-150);
      color: var(--main-color);
      position: relative;
    }

    .info {
      flex: 1;
      min-width: 0;

      h3,
      p {
        margin: 0;
        color: var(--gray-10000);
      }

      h3 {
        font-size: 17px;
        font-weight: 600;
        letter-spacing: -0.02em;
        line-height: 1.4;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      p {
        color: var(--gray-700);
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 4px;
        font-weight: 400;

        .created-time-inline {
          color: var(--gray-700);
          font-size: 11px;
          font-weight: 400;
          background: var(--gray-50);
          padding: 2px 6px;
          border-radius: 4px;
        }
      }
    }
  }

  .description {
    color: var(--gray-600);
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 1;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
    margin-bottom: 2px;
    font-size: 13px;
    font-weight: 500;
    flex: 1;
  }
}

.database-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  flex-direction: column;
  color: var(--gray-900);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  text-align: center;

  .empty-title {
    font-size: 20px;
    font-weight: 600;
    color: var(--gray-900);
    margin: 0 0 12px 0;
    letter-spacing: -0.02em;
  }

  .empty-description {
    font-size: 14px;
    color: var(--gray-600);
    margin: 0 0 32px 0;
    line-height: 1.5;
    max-width: 320px;
  }

  .ant-btn {
    height: 44px;
    padding: 0 24px;
    font-size: 15px;
    font-weight: 500;
  }
}

.database-container {
  padding: 0;
}

.loading-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 300px;
  gap: 16px;
}

.new-database-modal {
  h3 {
    margin-top: 10px;
  }
}
</style>
