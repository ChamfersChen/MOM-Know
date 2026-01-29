<template>
  <div class="database-relation-manager">
    <div class="section-header">
      <div class="header-left">
        <span class="section-title">已关联数据库</span>
        <a-tag color="blue" size="small">{{ connectedDatabases.length }} 个</a-tag>
      </div>
      <a-button type="primary" size="small" @click="showAddModal">
        <template #icon><PlusOutlined /></template>
        添加关联
      </a-button>
    </div>

    <div class="relation-content">
      <div v-if="connectedDatabases.length === 0" class="empty-state">
        <a-empty description="暂无关联数据库" />
      </div>
      <a-list
        v-else
        :data-source="connectedDatabases"
        :loading="loading"
        size="small"
        class="relation-list"
      >
        <template #renderItem="{ item }">
          <a-list-item class="relation-item">
            <a-list-item-meta :description="item.description || '暂无描述'">
              <template #title>
                <div class="relation-item-title">
                  <DatabaseOutlined style="margin-right: 8px; color: var(--main-color)" />
                  <span>{{ item.name }}</span>
                  <a-tag size="small" :color="getDbTypeColor(item.db_type)">
                    {{ item.db_type || '未知' }}
                  </a-tag>
                </div>
              </template>
            </a-list-item-meta>
            <template #actions>
              <a-button
                type="text"
                danger
                size="small"
                @click="handleRemoveRelation(item)"
                :loading="removingId === item.id"
              >
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </div>

    <a-modal
      v-model:open="addModalVisible"
      title="添加关联数据库"
      width="600px"
      :footer="null"
    >
      <div class="add-relation-modal">
        <a-input-search
          v-model:value="searchKeyword"
          placeholder="搜索数据库名称"
          style="margin-bottom: 16px; width: 100%"
          @search="handleSearch"
        />

        <a-spin :spinning="searchLoading">
          <a-list
            :data-source="availableDatabases"
            :loading="searchLoading"
            size="small"
            class="available-list"
            :locale="{ emptyText: searchKeyword ? '未找到匹配的数据库' : '暂无可用数据库' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="available-item">
                <a-list-item-meta :description="item.description || '暂无描述'">
                  <template #title>
                    <div class="available-item-title">
                      <DatabaseOutlined style="margin-right: 8px; color: var(--main-color)" />
                      <span>{{ item.name }}</span>
                      <a-tag size="small" :color="getDbTypeColor(item.db_type)">
                        {{ item.db_type || '未知' }}
                      </a-tag>
                    </div>
                  </template>
                </a-list-item-meta>
                <template #actions>
                  <a-button
                    type="primary"
                    size="small"
                    @click="handleAddRelation(item)"
                    :loading="addingId === item.db_id"
                    :disabled="isAlreadyConnected(item.db_id)"
                  >
                    <template #icon><PlusOutlined /></template>
                    {{ isAlreadyConnected(item.db_id) ? '已关联' : '添加' }}
                  </a-button>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-spin>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { DatabaseOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { databaseApi } from '@/apis/sql_database_api'
import { useDatabaseStore } from '@/stores/sql_database'

const store = useDatabaseStore()
const props = defineProps({
  databaseId: {
    type: String,
    required: true
  }
})

const loading = ref(false)
const connectedDatabases = ref([])
const relatedDbIds = ref([])
const availableDatabases = ref([])
const searchKeyword = ref('')
const searchLoading = ref(false)
const addModalVisible = ref(false)
const addingId = ref(null)
const removingId = ref(null)

const getDbTypeColor = (type) => {
  const colors = {
    lightrag: 'blue',
    knowledge_graph: 'green',
    vector: 'orange',
    default: 'default'
  }
  return colors[type?.toLowerCase()] || colors.default
}

const isAlreadyConnected = (dbId) => {
  return connectedDatabases.value.some((db) => db.db_id === dbId)
}

const fetchConnectedDatabases = async () => {
  loading.value = true
  try {
    const data = await databaseApi.getDatabaseInfo(props.databaseId)
    relatedDbIds.value = data['related_db_ids'] || []
    connectedDatabases.value = store.databases.filter((db) => relatedDbIds.value.includes(db.db_id))
  } catch (error) {
    console.error('获取关联数据库失败:', error)
    message.error('获取关联数据库失败')
  } finally {
    loading.value = false
  }
}

const fetchAvailableDatabases = async () => {
  searchLoading.value = true
  try {
    const keyword = searchKeyword.value.trim()
    let data
    if (keyword) {
      data = store.databases.filter(
        (db) => 
        db.name.includes(keyword) && 
        db.db_id !== props.databaseId && 
        store.database.connect_info.host == db.connect_info.host &&
        store.database.connect_info.port == db.connect_info.port 
      )
    } else {
      data = store.databases.filter(
        (db) => 
        db.db_id !== props.databaseId && 
        store.database.connect_info.host == db.connect_info.host &&
        store.database.connect_info.port == db.connect_info.port
      )
    }
    availableDatabases.value = data || []
  } catch (error) {
    console.error('获取可用数据库失败:', error)
    message.error('获取可用数据库失败')
  } finally {
    searchLoading.value = false
  }
}

const showAddModal = () => {
  console.log('showAddModal.database >>:', store.database)
  searchKeyword.value = ''
  fetchAvailableDatabases()
  addModalVisible.value = true
}

const handleSearch = () => {
  fetchAvailableDatabases()
}

const handleAddRelation = async (db) => {
  addingId.value = db.db_id
  try {
    relatedDbIds.value.push(db.db_id)
    console.log('handleAddRelation.relatedDbIds.value >>:', relatedDbIds.value)
    const newDatabase = {...store.database, related_db_ids: relatedDbIds.value.join(";")}
    await databaseApi.updateDatabase(props.databaseId, newDatabase)
    // await databaseApi.addRelatedDatabase(props.databaseId, db.id)
    message.success(`成功关联数据库: ${db.name}`)
    await fetchConnectedDatabases()
    fetchAvailableDatabases()
  } catch (error) {
    console.error('添加关联失败:', error)
    message.error(error.message || '添加关联失败')
  } finally {
    addingId.value = null
  }
}

const handleRemoveRelation = async (db) => {
  removingId.value = db.id
  try {
    relatedDbIds.value = relatedDbIds.value.filter((id) => id !== db.db_id)
    console.log('handleRemoveRelation.relatedDbIds.value >>:', relatedDbIds.value)
    const newDatabase = {...store.database, related_db_ids: relatedDbIds.value.join(";") || ""}

    await databaseApi.updateDatabase(props.databaseId, newDatabase)
    // await databaseApi.addRelatedDatabase(props.databaseId, db.id)
    await fetchConnectedDatabases()
    fetchAvailableDatabases()
    message.success(`已移除关联: ${db.name}`)
  } catch (error) {
    console.error('移除关联失败:', error)
    message.error(error.message || '移除关联失败')
  } finally {
    removingId.value = null
  }
}

onMounted(() => {
  store.loadDatabases()
  fetchConnectedDatabases()
})
</script>

<style lang="less" scoped>
.database-relation-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 8px;

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid var(--gray-200);
    background-color: var(--gray-25);

    .header-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .section-title {
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-700);
      margin: 0;
    }
  }

  .relation-content {
    flex: 1;
    overflow: hidden;

    .empty-state {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
    }
  }

  .relation-list {
    :deep(.ant-list-item) {
      padding: 8px 12px;
      border-bottom: 1px solid var(--gray-100);

      &:hover {
        background-color: var(--gray-50);
      }
    }

    .relation-item-title {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  .add-relation-modal {
    .available-list {
      max-height: 400px;
      overflow-y: auto;

      :deep(.ant-list-item) {
        padding: 8px 12px;
        border-bottom: 1px solid var(--gray-100);

        &:hover {
          background-color: var(--gray-50);
        }
      }

      .available-item-title {
        display: flex;
        align-items: center;
        gap: 8px;
      }
    }
  }
}
</style>
