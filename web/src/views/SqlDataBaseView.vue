<template>
  <div class="database-container layout-container">
    <HeaderComponent title="SQL数据库" :loading="dbState.listLoading">
      <template #actions>
        <a-button type="primary" @click="state.openNewDatabaseModel = true"> 连接数据库 </a-button>
        <a-button type="primary" @click="uploadToNeo4j"> 导入Neo4J </a-button>
      </template>
    </HeaderComponent>

    <a-modal
      :open="state.openNewDatabaseModel"
      title="连接数据库"
      :confirm-loading="dbState.creating"
      @ok="handleCreateDatabase"
      @cancel="cancelCreateDatabase"
      class="new-database-modal"
      width="800px"
      destroyOnClose
    >

      <!-- <h3>数据库名称<span style="color: var(--color-error-500)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" size="large" /> -->

      <h3>数据库配置<span style="color: var(--error-color)">*</span></h3>
      <!-- 数据库配置表单 -->
      <a-form :model="newDatabase" layout="vertical">
        <a-form-item label="主机地址" required>
          <a-input v-model:value="connectInfo.host" placeholder="例如：127.0.0.1" size="large" />
        </a-form-item>

        <a-form-item label="端口" required>
          <a-input-number v-model:value="connectInfo.port" :min="1" :max="65535" size="large" style="width: 100%;" />
        </a-form-item>

        <a-form-item label="用户名" required>
          <a-input v-model:value="connectInfo.user" placeholder="请输入数据库用户名" size="large" />
        </a-form-item>

        <a-form-item label="密码" required>
          <a-input-password v-model:value="connectInfo.password" placeholder="请输入数据库密码" size="large" />
        </a-form-item>

        <a-form-item label="数据库名称" required>
          <a-input v-model:value="connectInfo.database" placeholder="请输入要连接的数据库名称" size="large" />
        </a-form-item>

        <a-form-item label="描述" required>
          <a-textarea
            v-model:value="newDatabase.description"
            placeholder="请输入数据库连接描述（可选）"
            :auto-size="{ minRows: 3, maxRows: 5 }"
          />
        </a-form-item>
      </a-form>
      <!-- 共享配置 -->
      <h3>共享设置</h3>
      <ShareConfigForm v-model="shareConfig" :auto-select-user-dept="true" />
      <template #footer>
        <a-button key="back" @click="cancelCreateDatabase">取消</a-button>
        <a-button
          key="submit"
          type="primary"
          :loading="dbState.creating"
          @click="handleCreateDatabase"
          >创建</a-button
        >
      </template>
    </a-modal>

    <!-- 加载状态 -->
    <div v-if="dbState.listLoading" class="loading-container">
      <a-spin size="large" />
      <p>正在加载知识库...</p>
    </div>

    <!-- 空状态显示 -->
    <div v-else-if="!databases || databases.length === 0" class="empty-state">
      <h3 class="empty-title">暂无知识库</h3>
      <p class="empty-description">创建您的第一个知识库，开始管理文档和知识</p>
      <a-button type="primary" size="large" @click="state.openNewDatabaseModel = true">
        <template #icon>
          <PlusOutlined />
        </template>
        创建知识库
      </a-button>
    </div>

    <!-- 数据库列表 -->
    <div v-else class="databases">
      <div
        v-for="database in databases"
        :key="database.db_id"
        class="database dbcard"
        @click="navigateToDatabase(database.db_id)"
      >
        <!-- 私有知识库锁定图标 -->
        <LockOutlined
          v-if="database.metadata?.is_private"
          class="private-lock-icon"
          title="私有知识库"
        />
        <div class="top">
          <div class="icon">
            <component :is="getKbTypeIcon(database.db_type || 'lightrag')" />
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
        <div class="tags">
          <a-tag color="blue" v-if="database.embed_info?.name">{{
            database.embed_info.name
          }}</a-tag>
          <a-tag
            :color="getKbTypeColor(database.db_type || 'lightrag')"
            class="kb-type-tag"
            size="small"
          >
            {{ getKbTypeLabel(database.db_type || 'lightrag') }}
          </a-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/sql_database'
import { LockOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { databaseApi } from '@/apis/sql_database_api'
import HeaderComponent from '@/components/HeaderComponent.vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue'
import ShareConfigForm from '@/components/ShareConfigForm.vue'
import dayjs, { parseToShanghai } from '@/utils/time'
import AiTextarea from '@/components/AiTextarea.vue'
import { getKbTypeLabel, getKbTypeIcon, getKbTypeColor } from '@/utils/kb_utils'
import { message } from 'ant-design-vue'

const route = useRoute()
const router = useRouter()
const configStore = useConfigStore()
const databaseStore = useDatabaseStore()

// 使用 store 的状态
const { databases, state: dbState } = storeToRefs(databaseStore)

const state = reactive({
  openNewDatabaseModel: false
})

// 共享配置状态（用于提交数据）
const shareConfig = ref({
  is_shared: true,
  accessible_department_ids: []
})

const connectInfo = reactive({
  host: '127.0.0.1',
  port: '3306',
  user: 'root',
  password: '',
  database: 'mom',
})

const createEmptyDatabaseForm = () => ({
  name: '',
  description: '',
  db_type: 'mysql',
})

const newDatabase = reactive(createEmptyDatabaseForm())


const resetNewDatabase = () => {
  Object.assign(newDatabase, createEmptyDatabaseForm())
  // 重置共享配置
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

// 导入Neo4j图数据库
const uploadToNeo4j = async () => {
  // 根据databases info上传图数据库
  console.log('>>> upload to neo4j: ', databaseStore.databases)
  try{
    const ret = await databaseApi.createGraph()
    if(ret.code === 0){ 
      message.success('知识图谱创建成功')
    }else{
      message.error('知识图谱创建失败')
    }
  }catch(e){
    console.log('>>> upload to neo4j error: ', e)
    message.error('知识图谱创建失败')
  }
}

// 构建请求数据（只负责表单数据转换）
const buildRequestData = () => {
  const requestData = {
    database_name: connectInfo.database,
    description: newDatabase.description?.trim() || '',
    db_type: newDatabase.db_type,
  }
  console.log('shareConfig.value:', shareConfig.value)
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
  console.log('requestData:', requestData)

  return requestData
}

// 创建按钮处理
const handleCreateDatabase = async () => {
  const requestData = buildRequestData()
  console.log('requestData >> :', requestData)
  try {
    await databaseStore.createDatabase(requestData)
    resetNewDatabase()
    state.openNewDatabaseModel = false
  } catch (error) {
    // 错误已在 store 中处理
  }
}

const navigateToDatabase = (databaseId) => {
  router.push({ path: `/sqldatabase/${databaseId}` })
}

watch(
  () => route.path,
  (newPath) => {
    if (newPath === '/sqldatabase') {
      databaseStore.loadDatabases()
    }
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
  .kb-type-guide {
    margin: 12px 0;
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
  padding: 16px;
  border-radius: 16px;
  height: 156px;
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
    margin-bottom: 12px;
    font-size: 13px;
    font-weight: 400;
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
