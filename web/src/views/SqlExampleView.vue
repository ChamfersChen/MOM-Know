<template>
  <div class="example-config-container">
    <div class="page-header">
      <div class="header-left">
        <a-button @click="goBack">
          <LeftOutlined /> 返回
        </a-button>
        <div class="page-title">
          <CodeOutlined />
          <span>SQL示例库</span>
          <a-tag color="blue">{{ groupInfo }}</a-tag>
        </div>
      </div>
      <a-button type="primary" @click="handleAdd">
        <PlusOutlined /> 添加示例
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="examples"
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
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  LeftOutlined,
  CodeOutlined 
} from '@ant-design/icons-vue'
import { useDatabaseStore } from '@/stores/sql_database'

const databaseStore = useDatabaseStore()
const route = useRoute()
const router = useRouter()

const dbType = computed(() => route.query.dbType || '')
const host = computed(() => route.query.host || '')
const port = computed(() => route.query.port || '')
const groupInfo = computed(() => `${dbType.value} - ${host.value}:${port.value}`)

const loading = ref(false)
const examples = ref([])
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
  padding: 24px;
  background: var(--gray-0, #fff);
  min-height: calc(100vh - 64px);

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 16px;

      .page-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 18px;
        font-weight: 600;
        color: var(--gray-800, #1f2937);
      }
    }
  }
}
</style>
