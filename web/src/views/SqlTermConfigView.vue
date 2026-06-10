<template>
  <div class="term-config-container layout-container">
    <div class="config-header">
      <div class="config-header-left">
        <button class="detail-back-btn" @click="goBack">
          <ArrowLeft :size="16" />
          <span>返回</span>
        </button>
        <h1 class="config-header-title">术语配置</h1>
        <a-tag color="blue">{{ groupInfo }}</a-tag>
      </div>
    </div>

    <PageShoulder v-model:search="searchQuery" search-placeholder="搜索术语名称或描述...">
      <template #actions>
        <a-button type="primary" @click="handleAdd">
          <PlusOutlined /> 添加术语
        </a-button>
      </template>
    </PageShoulder>

    <div class="config-content">
      <a-table
        :columns="columns"
        :data-source="filteredTerms"
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
        <a-form-item label="同义词">
          <div class="synonyms-list">
            <div 
              v-for="(synonym, index) in formData.synonyms" 
              :key="index"
              style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;"
            >
              <a-input 
                v-model:value="formData.synonyms[index]" 
                placeholder="请输入同义词"
              />
              <a-button type="text" danger size="small" @click="removeFormSynonym(index)">
                <DeleteOutlined />
              </a-button>
            </div>
            <a-button type="dashed" block @click="addFormSynonym">
              <PlusOutlined /> 添加同义词
            </a-button>
          </div>
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
const terms = ref([])
const searchQuery = ref('')
const filteredTerms = computed(() => {
  if (!searchQuery.value) return terms.value
  const q = searchQuery.value.toLowerCase()
  return terms.value.filter(
    (t) =>
      (t.word && t.word.toLowerCase().includes(q)) ||
      (t.description && t.description.toLowerCase().includes(q))
  )
})
watch(filteredTerms, (val) => {
  pagination.total = val.length
  pagination.current = 1
})
const modalVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const formData = reactive({
  name: '',
  description: '',
  statusActive: true,
  synonyms: []
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
    const data = await databaseStore.getTermsByHostPort(host.value, Number(port.value))
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
  formData.synonyms = []
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
    console.log(record)
    await databaseStore.enableTerm(record.id, record.enabled)
    // 模拟异步操作
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

const addFormSynonym = () => {
  formData.synonyms.push('')
}

const removeFormSynonym = (index) => {
  formData.synonyms.splice(index, 1)
}

const handleEditSubmit = async () => {
  try {
    await editFormRef.value.validate()
    
    const filteredSynonyms = editFormData.synonyms.filter(s => s.trim())
    const wordLower = editFormData.name.trim().toLowerCase()
    const invalidSynonyms = filteredSynonyms.filter(s => s.toLowerCase() === wordLower)
    
    if (invalidSynonyms.length > 0) {
      message.warning('同义词不能与术语名称相同')
      return
    }
    
    submitting.value = true
    
    const index = terms.value.findIndex(t => t.id === editingId.value)
    if (index !== -1) {
      terms.value[index] = { 
        ...terms.value[index], 
        word: editFormData.name,
        description: editFormData.description,
        other_words: filteredSynonyms
      }
    }
    await databaseStore.updateTerm(terms.value[index])
    editModalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
    loadTerms()
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
        // 删除术语
        const res = await databaseStore.deleteTerm(record.id)
        console.log('删除成功:', res)
        if (res) {
          terms.value = terms.value.filter(t => t.id !== record.id)
          pagination.total = terms.value.length
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
    
    const filteredSynonyms = formData.synonyms.filter(s => s.trim())
    const wordLower = formData.name.trim().toLowerCase()
    const invalidSynonyms = filteredSynonyms.filter(s => s.toLowerCase() === wordLower)
    
    if (invalidSynonyms.length > 0) {
      message.warning('同义词不能与术语名称相同')
      return
    }
    
    submitting.value = true
    
    const newTerm = {
      id: Date.now(),
      word: formData.name,
      description: formData.description,
      enabled: formData.statusActive,
      create_time: new Date().toISOString().replace('T', ' ').substring(0, 19),
      other_words: filteredSynonyms,
      datasource_host: host.value,
      datasource_port: Number(port.value),
    }
    pagination.total = terms.value.length + 1
    await databaseStore.addTerm(newTerm) // 新增术语接口
    modalVisible.value = false
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
    loadTerms()
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
