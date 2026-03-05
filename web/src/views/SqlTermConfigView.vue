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
        <template v-if="column.key === 'enabled'">
          <a-switch 
            :checked="record.enabled" 
            @change="(checked) => handleStatusChange(record, checked)"
            :loading="record.statusLoading"
          />
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
          <a-switch v-model:checked="formData.statusActive" />
          <span style="margin-left: 8px">{{ formData.statusActive ? '启用' : '禁用' }}</span>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="editModalVisible"
      title="编辑术语"
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
        <a-form-item label="术语名称" name="name">
          <a-input v-model:value="editFormData.name" placeholder="请输入术语名称" />
        </a-form-item>
        <a-form-item label="术语描述" name="description">
          <a-textarea 
            v-model:value="editFormData.description" 
            placeholder="请输入术语描述"
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="同义词">
          <div class="synonyms-list">
            <div 
              v-for="(synonym, index) in editFormData.synonyms" 
              :key="index"
              style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;"
            >
              <a-input 
                v-model:value="editFormData.synonyms[index]" 
                placeholder="请输入同义词"
              />
              <a-button type="text" danger size="small" @click="removeSynonym(index)">
                <DeleteOutlined />
              </a-button>
            </div>
            <a-button type="dashed" block @click="addSynonym">
              <PlusOutlined /> 添加同义词
            </a-button>
          </div>
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
import { useDatabaseStore } from '@/stores/sql_database'

const databaseStore = useDatabaseStore()
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
  statusActive: true
})

const formRules = {
  name: [{ required: true, message: '请输入术语名称', trigger: 'blur' }]
}

const editModalVisible = ref(false)
const editFormRef = ref(null)
const editFormData = reactive({
  name: '',
  description: '',
  synonyms: []
})

const editFormRules = {
  name: [{ required: true, message: '请输入术语名称', trigger: 'blur' }]
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
    dataIndex: 'word',
    key: 'word',
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

const loadTerms = async () => {
  loading.value = true
  try {
    const data = await databaseStore.getAllTerms()
    terms.value = data
    pagination.total = data.length
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
  formData.statusActive = true
  modalVisible.value = true
}

const handleEdit = (record) => {
  isEdit.value = true
  editingId.value = record.id
  editFormData.name = record.word
  editFormData.description = record.description
  editFormData.synonyms = record.other_words ? [...record.other_words] : []
  editModalVisible.value = true
}

const handleStatusChange = async (record, checked) => {
  record.statusLoading = true
  try {
    await new Promise(resolve => setTimeout(resolve, 300))
    record.enabled = checked
    message.success(checked ? '已启用' : '已禁用')
  } catch (error) {
    message.error('状态更新失败')
  } finally {
    record.statusLoading = false
  }
}

const addSynonym = () => {
  editFormData.synonyms.push('')
}

const removeSynonym = (index) => {
  editFormData.synonyms.splice(index, 1)
}

const handleEditSubmit = async () => {
  try {
    await editFormRef.value.validate()
    submitting.value = true
    
    await new Promise(resolve => setTimeout(resolve, 500))
    
    const index = terms.value.findIndex(t => t.id === editingId.value)
    if (index !== -1) {
      terms.value[index] = { 
        ...terms.value[index], 
        word: editFormData.name,
        description: editFormData.description,
        other_words: editFormData.synonyms.filter(s => s.trim())
      }
    }
    message.success('更新成功')
    editModalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
  }
}

const handleEditCancel = () => {
  editModalVisible.value = false
  editFormRef.value?.resetFields()
}

const handleDelete = (record) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除术语「${record.word}」吗？`,
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
    
    terms.value.unshift({
      id: Date.now(),
      word: formData.name,
      description: formData.description,
      enabled: formData.statusActive,
      create_time: new Date().toLocaleString('zh-CN'),
      other_words: []
    })
    pagination.total = terms.value.length
    message.success('添加成功')
    
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
