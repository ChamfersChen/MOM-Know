<template>
  <div class="term-config-container">
    <div class="page-header">
      <div class="header-left">
        <a-button @click="goBack">
          <LeftOutlined /> 返回
        </a-button>
        <div class="page-title">
          <SettingOutlined />
          <span>术语配置</span>
          <a-tag color="blue">{{ groupInfo }}</a-tag>
        </div>
      </div>
      <a-button type="primary" @click="handleAdd">
        <PlusOutlined /> 添加术语
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="terms"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="record.status === 'active' ? 'green' : 'default'">
            {{ record.status === 'active' ? '启用' : '禁用' }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'created_at'">
          {{ formatDate(record.created_at) }}
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
      :title="isEdit ? '编辑术语' : '添加术语'"
      @ok="handleSubmit"
      @cancel="handleCancel"
      :confirm-loading="submitting"
    >
      <a-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        layout="vertical"
      >
        <a-form-item label="术语名称" name="name">
          <a-input v-model:value="formData.name" placeholder="请输入术语名称" />
        </a-form-item>
        <a-form-item label="术语描述" name="description">
          <a-textarea 
            v-model:value="formData.description" 
            placeholder="请输入术语描述"
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="状态" name="status">
          <a-select v-model:value="formData.status" placeholder="请选择状态">
            <a-select-option value="active">启用</a-select-option>
            <a-select-option value="inactive">禁用</a-select-option>
          </a-select>
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
  SettingOutlined 
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()

const dbType = computed(() => route.query.dbType || '')
const host = computed(() => route.query.host || '')
const port = computed(() => route.query.port || '')
const groupInfo = computed(() => `${dbType.value} - ${host.value}:${port.value}`)

const loading = ref(false)
const terms = ref([])
const modalVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const formData = reactive({
  name: '',
  description: '',
  status: 'active'
})

const formRules = {
  name: [{ required: true, message: '请输入术语名称', trigger: 'blur' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }]
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
    title: '术语名称',
    dataIndex: 'name',
    key: 'name',
    width: '25%'
  },
  {
    title: '术语描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: '10%'
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
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

const loadTerms = async () => {
  loading.value = true
  try {
    const mockData = [
      {
        id: 1,
        name: '客户',
        description: '指购买产品或服务的用户或组织',
        status: 'active',
        created_at: '2024-01-15 10:30:00'
      },
      {
        id: 2,
        name: '订单',
        description: '客户下达的购买请求',
        status: 'active',
        created_at: '2024-01-16 14:20:00'
      },
      {
        id: 3,
        name: '产品',
        description: '公司提供的商品或服务',
        status: 'inactive',
        created_at: '2024-01-17 09:15:00'
      }
    ]
    terms.value = mockData
    pagination.total = mockData.length
  } catch (error) {
    message.error('加载术语列表失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = () => {
  isEdit.value = false
  editingId.value = null
  formData.name = ''
  formData.description = ''
  formData.status = 'active'
  modalVisible.value = true
}

const handleEdit = (record) => {
  isEdit.value = true
  editingId.value = record.id
  formData.name = record.name
  formData.description = record.description
  formData.status = record.status
  modalVisible.value = true
}

const handleDelete = (record) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除术语「${record.name}」吗？`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        terms.value = terms.value.filter(t => t.id !== record.id)
        pagination.total = terms.value.length
        message.success('删除成功')
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
    
    await new Promise(resolve => setTimeout(resolve, 500))
    
    if (isEdit.value) {
      const index = terms.value.findIndex(t => t.id === editingId.value)
      if (index !== -1) {
        terms.value[index] = { 
          ...terms.value[index], 
          ...formData 
        }
      }
      message.success('更新成功')
    } else {
      terms.value.unshift({
        id: Date.now(),
        ...formData,
        created_at: new Date().toLocaleString('zh-CN')
      })
      pagination.total = terms.value.length
      message.success('添加成功')
    }
    
    modalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
  }
}

const handleCancel = () => {
  modalVisible.value = false
  formRef.value?.resetFields()
}

onMounted(() => {
  loadTerms()
})
</script>

<style lang="less" scoped>
.term-config-container {
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
