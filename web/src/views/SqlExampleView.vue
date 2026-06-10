<template>
  <div class="example-config-container layout-container">
    <div class="config-header">
      <div class="config-header-left">
        <button class="detail-back-btn" @click="goBack">
          <ArrowLeft :size="16" />
          <span>返回</span>
        </button>
        <h1 class="config-header-title">SQL 示例库</h1>
        <a-tag color="blue">{{ groupInfo }}</a-tag>
      </div>
    </div>

    <PageShoulder v-model:search="searchQuery" search-placeholder="搜索问题描述或SQL...">
      <template #actions>
        <a-button type="primary" @click="handleAdd">
          <PlusOutlined /> 添加示例
        </a-button>
      </template>
    </PageShoulder>

    <div class="config-content">
      <a-table
        :columns="columns"
        :data-source="filteredExamples"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
      >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-switch 
            :checked="record.enabled" 
            @change="(checked) => handleStatusChange(record, checked)"
            :loading="record.statusLoading"
          />
        </template>
        <template v-else-if="column.key === 'sql'">
          <a-tooltip>
            <template #title>{{ record.sql }}</template>
            <span style="font-family: monospace;">{{ record.sql }}</span>
          </a-tooltip>
        </template>
        <template v-else-if="column.key === 'create_time'">
          {{ formatDate(record.create_time) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-space>
            <a-button type="link" size="small" @click="handleEdit(record)">
              <EditOutlined /> 编辑
            </a-button>
            <a-button type="link" danger size="small" @click="handleDelete(record)">
              <DeleteOutlined /> 删除
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="modalVisible"
      :title="isEdit ? '编辑示例' : '添加示例'"
      @ok="handleSubmit"
      @cancel="handleCancel"
      :confirm-loading="submitting"
      width="600px"
    >
      <a-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        layout="vertical"
      >
        <a-form-item label="问题描述" name="description">
          <a-textarea 
            v-model:value="formData.description" 
            placeholder="请输入问题描述"
            :rows="2"
          />
        </a-form-item>
        <a-form-item label="示例SQL" name="sql">
          <a-textarea 
            v-model:value="formData.sql" 
            placeholder="请输入示例SQL语句"
            :rows="4"
            style="font-family: monospace;"
          />
        </a-form-item>
        <a-form-item label="状态" name="status">
          <a-switch v-model:checked="formData.statusActive" />
          <span style="margin-left: 8px">{{ formData.statusActive ? '启用' : '禁用' }}</span>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="editModalVisible"
      title="编辑示例"
      @ok="handleEditSubmit"
      @cancel="handleEditCancel"
      :confirm-loading="submitting"
      width="600px"
    >
      <a-form
        ref="editFormRef"
        :model="editFormData"
        :rules="editFormRules"
        layout="vertical"
      >
        <a-form-item label="问题描述" name="description">
          <a-textarea 
            v-model:value="editFormData.description" 
            placeholder="请输入问题描述"
            :rows="2"
          />
        </a-form-item>
        <a-form-item label="示例SQL" name="sql">
          <a-textarea 
            v-model:value="editFormData.sql" 
            placeholder="请输入示例SQL语句"
            :rows="4"
            style="font-family: monospace;"
          />
        </a-form-item>
      </a-form>
    </a-modal>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined
} from '@ant-design/icons-vue'
import { ArrowLeft } from 'lucide-vue-next'
import { useDatabaseStore } from '@/stores/sql_database'
import PageShoulder from '@/components/shared/PageShoulder.vue'

const databaseStore = useDatabaseStore()
const route = useRoute()
const router = useRouter()

const dbType = computed(() => route.query.dbType || '')
const host = computed(() => route.query.host || '')
const port = computed(() => route.query.port || '')
const groupInfo = computed(() => `${dbType.value} - ${host.value}:${port.value}`)

const loading = ref(false)
const examples = ref([])
const searchQuery = ref('')
const filteredExamples = computed(() => {
  if (!searchQuery.value) return examples.value
  const q = searchQuery.value.toLowerCase()
  return examples.value.filter(
    (e) =>
      (e.description && e.description.toLowerCase().includes(q)) ||
      (e.sql && e.sql.toLowerCase().includes(q))
  )
})
watch(filteredExamples, (val) => {
  pagination.total = val.length
  pagination.current = 1
})
const modalVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const formData = reactive({
  description: '',
  sql: '',
  statusActive: true
})

const formRules = {
  description: [{ required: true, message: '请输入问题描述', trigger: 'blur' }],
  sql: [{ required: true, message: '请输入示例SQL', trigger: 'blur' }]
}

const editModalVisible = ref(false)
const editFormRef = ref(null)
const editFormData = reactive({
  description: '',
  sql: ''
})

const editFormRules = {
  description: [{ required: true, message: '请输入问题描述', trigger: 'blur' }],
  sql: [{ required: true, message: '请输入示例SQL', trigger: 'blur' }]
}

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 条`
})

const columns = [
  {
    title: '问题描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true
  },
  {
    title: '示例SQL',
    dataIndex: 'sql',
    key: 'sql',
    ellipsis: true,
    width: '35%'
  },
  {
    title: '状态',
    dataIndex: 'enabled',
    key: 'enabled',
    width: '10%'
  },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: '15%'
  },
  {
    title: '操作',
    key: 'action',
    width: '15%'
  }
]

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

const goBack = () => {
  router.back()
}

const loadExamples = async () => {
  loading.value = true
  try {
    // const data = [
    //   {
    //     "id": 1,
    //     "create_time": null,
    //     "description": "查找所有系统用户",
    //     "sql": "select * from `mom`.`sys_user`",
    //     "datasource_host": "127.0.0.1",
    //     "datasource_port": 3306,
    //     "enabled": false
    //   }
    // ]
    const data = await databaseStore.getSqlExamplesByHostPort(host.value, Number(port.value))
    examples.value = data
    pagination.total = data.length
  } catch (error) {
    message.error('加载示例列表失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = () => {
  isEdit.value = false
  editingId.value = null
  formData.description = ''
  formData.sql = ''
  formData.statusActive = true
  modalVisible.value = true
}

const handleEdit = (record) => {
  isEdit.value = true
  editingId.value = record.id
  editFormData.description = record.description
  editFormData.sql = record.sql
  editModalVisible.value = true
}

const handleStatusChange = async (record, checked) => {
  record.statusLoading = true
  try {
    await new Promise(resolve => setTimeout(resolve, 300))
    record.enabled = checked
    await databaseStore.enableExample(record.id, record.enabled)
    message.success(checked ? '已启用' : '已禁用')
  } catch (error) {
    message.error('状态更新失败')
  } finally {
    record.statusLoading = false
  }
}

const handleEditSubmit = async () => {
  try {
    await editFormRef.value.validate()
    submitting.value = true
    
    const index = examples.value.findIndex(t => t.id === editingId.value)
    if (index !== -1) {
      examples.value[index] = { 
        ...examples.value[index], 
        description: editFormData.description,
        sql: editFormData.sql
      }
    }
    await databaseStore.updateExample(examples.value[index])
    editModalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
    loadExamples()
  }
}

const handleEditCancel = () => {
  editModalVisible.value = false
  editFormRef.value?.resetFields()
}

const handleDelete = (record) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除示例「${record.description}」吗？`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        const res = await databaseStore.deleteExample(record.id)
        if (res) {
          examples.value = examples.value.filter(t => t.id !== record.id)
          pagination.total = examples.value.length
        }
      } catch (error) {
        message.error('删除失败')
      }
    }
  })
}

const handleSubmit = async () => {
  try {
    await formRef.value.validate()
    submitting.value = true
    
    const newExample = {
      id: Date.now(),
      description: formData.description,
      sql: formData.sql,
      enabled: formData.statusActive,
      create_time: new Date().toISOString().replace('T', ' ').substring(0, 19),
      datasource_host: host.value,
      datasource_port: Number(port.value),
    }
    console.log('newExample', newExample)
    await databaseStore.addExample(newExample)
    modalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
    loadExamples()
  }
}

const handleCancel = () => {
  modalVisible.value = false
  formRef.value?.resetFields()
}

onMounted(() => {
  loadExamples()
})
</script>

<style lang="less" scoped>
.example-config-container {
  background: var(--gray-0);

  .detail-back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    background: none;
    color: var(--gray-500);
    font-size: 14px;
    cursor: pointer;
    padding: 4px 8px;
    margin-left: -8px;
    border-radius: 6px;
    transition: color 0.15s, background 0.15s;

    &:hover {
      color: var(--gray-700);
      background: var(--gray-50);
    }
  }

  .config-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px var(--page-padding);
    background-color: var(--light-60);
    backdrop-filter: blur(10px);
    position: sticky;
    top: 0;
    z-index: 1000;
    border-bottom: 1px solid var(--gray-100);

    .config-header-left {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .config-header-title {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--gray-2000);
      white-space: nowrap;
    }
  }

  .config-content {
    padding: 16px var(--page-padding);
  }
}
</style>
