<template>
  <div class="file-table-container">
    <div class="panel-header">
      <div class="upload-btn-group">
        <a-button type="primary" size="small" class="upload-btn">
          <!-- <FileUp size="14" style="margin-left: 4px" /> -->
          同步数据库表信息
          <!-- <ChevronDown size="14" style="margin-left: 4px" /> -->
        </a-button>

      </div>
      <div class="panel-actions">
        <a-input
          v-model:value="tablenameFilter"
          placeholder="搜索"
          size="small"
          class="action-searcher"
          allow-clear
          @change="onFilterChange"
        >
          <template #prefix>
            <Search size="14" style="color: var(--gray-400)" />
          </template>
        </a-input>

        <a-button
          type="text"
          @click="handleRefresh"
          :loading="refreshing"
          title="刷新"
          class="panel-action-btn"
        >
          <template #icon><RotateCw size="16" /></template>
        </a-button>
        <a-button
          type="text"
          @click="toggleSelectionMode"
          title="多选"
          class="panel-action-btn"
          :class="{ active: isSelectionMode }"
        >
          <template #icon><CheckSquare size="16" /></template>
        </a-button>
        <a-button
          type="text"
          @click="toggleRightPanel"
          title="切换右侧面板"
          class="panel-action-btn expand"
          :class="{ expanded: props.rightPanelVisible }"
        >
          <template #icon><ChevronLast size="16" /></template>
        </a-button>
      </div>
    </div>

    <div class="batch-actions" v-if="isSelectionMode">
      <div class="batch-info">
        <a-checkbox
          :checked="isAllSelected"
          :indeterminate="isPartiallySelected"
          @change="onSelectAllChange"
          style="margin-right: 8px"
        />
        <span>{{ selectedRowKeys.length }} 项</span>
      </div>
      <div style="display: flex; gap: 2px">
        <a-button
          type="link"
          @click="handleBatchChoose"
          :loading="batchDeleting"
          :icon="h(CheckSquare, { size: 16 })"
        >
          确认选择
        </a-button>
        <a-button
          type="link"
          danger
          @click="handleBatchUnchoose"
          :loading="batchDeleting"
          :icon="h(X, { size: 16 })"
        >
          取消选择
        </a-button>
      </div>
    </div>

    <!-- 入库/重新入库参数配置模态框 -->
    <a-modal
      v-model:open="updateTableDescriptionModalVisible"
      :title="updateTableDescriptionModalTitle"
      width="600px"
    >
      <div class="index-params">
        <a-form layout="vertical">
          <a-form-item label="描述">
            <a-textarea
              v-model:value="descriptionForm"
              placeholder="请输入描述"
              :rows="4"
            />
          </a-form-item>
        </a-form>
      </div>

      <template #footer>
        <a-button @click="handleUpdateTableDescriptionCancel">
          取消
        </a-button>
        <a-button type="primary" @click="handleUpdateTableDescriptionConfirm">
          确定
        </a-button>
      </template>
    </a-modal>
    <a-table
      :columns="columnsCompact"
      :data-source="paginatedTables"
      row-key="table_id"
      class="my-table"
      size="small"
      :show-header="false"
      :pagination="tablePagination"
      @change="handleTableChange"
      v-model:expandedRowKeys="expandedRowKeys"
      :custom-row="customRow"
      :row-selection="
        isSelectionMode
          ? {
              selectedRowKeys: selectedRowKeys,
              onChange: onSelectChange
            }
          : null
      "
      :locale="{
        emptyText: emptyText
      }"
    >
      <template #bodyCell="{ column, text, record }">
        <div v-if="column.key === 'tablename'">
          <a-popover
            placement="right"
            overlayClassName="file-info-popover"
            :mouseEnterDelay="0.5"
          >
            <template #content>
              <div class="file-info-card">
                <div class="info-row">
                  <span class="label">ID:</span> <span class="value">{{ record.table_id }}</span>
                </div>
                <div class="info-row">
                  <span class="label">时间:</span>
                  <span class="value">{{ formatRelativeTime(record.created_at) }}</span>
                </div>
              </div>
            </template>
            <a-button class="main-btn" type="link" @click="handleReindexFile(record)">
              <component
                :is="getFileIcon(record.displayName || text)"
                :style="{
                  marginRight: '0',
                  color: getFileIconColor(record.displayName || text),
                  fontSize: '16px'
                }"
              />
              {{ record.displayName || text }}
            </a-button>
          </a-popover>
        </div>
        <div
          v-else-if="column.key === 'description'"
          style="display: flex; align-items: center; justify-content: flex-end"
        >
          <template v-if="!record.is_folder">
            <a-tooltip :title="getStatusText(text)">
              <span>{{ text }}</span>
            </a-tooltip>
          </template>
        </div>
        <div
          v-else-if="column.key === 'is_choose'"
          style="display: flex; align-items: center; justify-content: flex-end"
        >
          <template v-if="!record.is_folder">
            <a-tooltip :title="getStatusText(text)">
              <span
                v-if="text === false"
                style="color: var(--color-error-500)"
                ><CloseCircleFilled
              /></span>
              <span v-else
                style="color: var(--color-success-500)"
                ><CheckCircleFilled
              /></span>
            </a-tooltip>
          </template>
        </div>
        <div v-else-if="column.key === 'action'" class="table-row-actions">
          <a-popover
            placement="bottomRight"
            trigger="click"
            overlayClassName="file-action-popover"
            v-model:open="popoverVisibleMap[record.table_id]"
          >
            <template #content>
              <div class="file-action-list">
                  <a-button
                    type="text"
                    block
                    @click="handleReindexFile(record); closePopover(record.table_id)"
                  >
                    <template #icon><component :is="h(RotateCw)" size="14" /></template>
                    修改描述
                  </a-button>
              </div>
            </template>
            <a-button type="text" :icon="h(Ellipsis)" class="action-trigger-btn" />
          </a-popover>
        </div>
        <span v-else>{{ text }}</span>
      </template>
    </a-table>
  </div>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue'
import { useDatabaseStore } from '@/stores/sql_database'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
import { documentApi } from '@/apis/knowledge_api'
import {
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  FolderFilled,
  FolderOpenFilled,
  FileTextFilled,
  HddOutlined,
} from '@ant-design/icons-vue'
import {
  Trash2,

  Download,
  RotateCw,
  ChevronLast,
  Ellipsis,
  FolderPlus,
  CheckSquare,
  X,
  FileText,
  FileCheck,
  Plus,
  Database,
  FileUp,
  FolderUp,
  Search,
  Filter,
  ArrowUpDown,
  ChevronDown
} from 'lucide-vue-next'

const store = useDatabaseStore()
const userStore = useUserStore()

const sortField = ref('filename')
const sortOptions = [
  { label: '文件名', value: 'filename' },
  { label: '创建时间', value: 'created_at' },
  { label: '状态', value: 'status' }
]

const descriptionForm = ref('')
const singleChooseTable = ref(null)

const handleSortMenuClick = (e) => {
  sortField.value = e.key
  // 排序变化时重置到第一页
  paginationConfig.value.current = 1
}

// Status text mapping
const getStatusText = (status) => {
  const map = {
    false: '未选择',
    true: '已选择',
    uploaded: '已上传',
    parsing: '解析中',
    parsed: '已解析',
    error_parsing: '解析失败',
    indexing: '入库中',
    indexed: '已入库',
    error_indexing: '入库失败',
    done: '已入库',
    failed: '入库失败',
    processing: '处理中',
    waiting: '等待中'
  }
  return map[status] || status
}

const props = defineProps({
  rightPanelVisible: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['showAddFilesModal', 'toggleRightPanel'])

const files = computed(() => Object.values(store.database.files || {}))
const tables = computed(() => Object.values(store.database.tables || {}))
const refreshing = computed(() => store.state.refrashing)
const lock = computed(() => store.state.lock)
const batchDeleting = computed(() => store.state.batchDeleting)
const batchParsing = computed(() => store.state.chunkLoading)
const batchIndexing = computed(() => store.state.chunkLoading)
const autoRefresh = computed(() => store.state.autoRefresh)
const selectedRowKeys = computed({
  get: () => store.selectedRowKeys,
  set: (keys) => (store.selectedRowKeys = keys)
})

const isSelectionMode = ref(false)

const allSelectableTables = computed(() => {
  const nameFilter = tablenameFilter.value.trim().toLowerCase()
  return tables.value.filter((table) => {

    if (nameFilter) {
      const nameMatch =
        !nameFilter || (table.tablename && table.tablename.toLowerCase().includes(nameFilter))
      return nameMatch
    }
    return true
  })
})


const isAllSelected = computed(() => {
  const selectableIds = allSelectableTables.value.map((t) => t.table_id)
  if (selectableIds.length === 0) return false
  return selectableIds.every((id) => selectedRowKeys.value.includes(id))
})

const isPartiallySelected = computed(() => {
  const selectableIds = allSelectableTables.value.map((t) => t.table_id)
  const selectedCount = selectableIds.filter((id) => selectedRowKeys.value.includes(id)).length
  return selectedCount > 0 && selectedCount < selectableIds.length
})

const onSelectAllChange = (e) => {
  if (e.target.checked) {
    selectedRowKeys.value = allSelectableTables.value.map((t) => t.table_id)
  } else {
    selectedRowKeys.value = []
  }
}

const expandedRowKeys = ref([])

const popoverVisibleMap = ref({})
const closePopover = (fileId) => {
  if (fileId) {
    popoverVisibleMap.value[fileId] = false
  }
}


const toggleSelectionMode = () => {
  isSelectionMode.value = !isSelectionMode.value
  if (!isSelectionMode.value) {
    selectedRowKeys.value = []
  }
}


// 拖拽相关逻辑
const customRow = (record) => {
  return {
    draggable: true,
    onClick: () => {
      console.log('Clicked file record:', record)
    },
    onDragstart: (event) => {
      // 检查是否是真实文件/文件夹（存在于 store 中）
      const files = store.database?.tables || {}
      if (!files[record.table_id]) {
        event.preventDefault()
        return
      }

      event.dataTransfer.setData(
        'application/json',
        JSON.stringify({
          table_id: record.table_id,
          tablename: record.tablename
        })
      )
      event.dataTransfer.effectAllowed = 'move'
      // 可以设置一个更好看的拖拽图像
    },
    onDragleave: (event) => {
      event.currentTarget.classList.remove('drop-over-folder')
    },
    onDrop: async (event) => {
      event.preventDefault()
      event.currentTarget.classList.remove('drop-over-folder')

      const data = event.dataTransfer.getData('application/json')
      if (!data) return

      try {
        const { file_id, filename } = JSON.parse(data)
        if (file_id === record.table_id) return

        // 确认移动
        Modal.confirm({
          title: '移动文件',
          content: `确定要将 "${filename}" 移动到 "${record.filename}" 吗？`,
          onOk: async () => {
            try {
              await store.moveFile(file_id, record.file_id)
            } catch (error) {
              // error handled in store
            }
          }
        })
      } catch (e) {
        console.error('Drop error:', e)
      }
    }
  }
}

// 入库/重新入库参数配置相关
const updateTableDescriptionModalVisible = ref(false)
const indexConfigModalLoading = computed(() => store.state.chunkLoading)
const updateTableDescriptionModalTitle = ref('修改数据库表描述')

const indexParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  qa_separator: ''
})
const currentIndexFileIds = ref([])
const isBatchIndexOperation = ref(false)

// 分页配置
const paginationConfig = ref({
  current: 1,
  pageSize: 100,
  pageSizeOptions: ['100', '300', '500', '1000']
})

// 文件总数
const totalFiles = computed(() => files.value.length)

// 是否显示分页
const showPagination = computed(() => totalFiles.value > paginationConfig.value.pageSize)

// 分页后的数据
const paginatedFiles = computed(() => {
  const list = filteredFiles.value
  if (!showPagination.value) return list

  const start = (paginationConfig.value.current - 1) * paginationConfig.value.pageSize
  const end = start + paginationConfig.value.pageSize
  return list.slice(start, end)
})

const paginatedTables = computed(() => {
  const list = filteredTables.value
  if (!showPagination.value) return list

  const start = (paginationConfig.value.current - 1) * paginationConfig.value.pageSize
  const end = start + paginationConfig.value.pageSize
  return list.slice(start, end)
})

// 表格分页配置
const tablePagination = computed(() => ({
  current: paginationConfig.value.current,
  pageSize: paginationConfig.value.pageSize,
  total: filteredFiles.value.length,
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 项`,
  pageSizeOptions: paginationConfig.value.pageSizeOptions,
  hideOnSinglePage: true
}))

// 处理表格变化（分页、每页条数切换）
const handleTableChange = (pagination) => {
  paginationConfig.value.current = pagination.current
  paginationConfig.value.pageSize = pagination.pageSize
}

// 文件名过滤
const filenameFilter = ref('')
const tablenameFilter = ref('')
const statusFilter = ref('all')
const statusOptions = [
  { label: '已上传', value: 'uploaded' },
  { label: '解析中', value: 'parsing' },
  { label: '已解析', value: 'parsed' },
  { label: '解析失败', value: 'error_parsing' },
  { label: '入库中', value: 'indexing' },
  { label: '已入库', value: 'indexed' },
  { label: '入库失败', value: 'error_indexing' }
]

// 紧凑表格列定义
const columnsCompact = [
  {
    title: '文件名',
    dataIndex: 'tablename',
    key: 'tablename',
    ellipsis: true,
    width: undefined, // 不设置宽度，让它占据剩余空间
    sorter: (a, b) => {
      return (a.tablename || '').localeCompare(b.tablename || '')
    },
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true,
    width: undefined, // 不设置宽度，让它占据剩余空间
    sorter: (a, b) => {
      return (a.description || '').localeCompare(b.description || '')
    },
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '状态',
    dataIndex: 'is_choose',
    key: 'is_choose',
    width: 60,
    align: 'right',
    sorter: (a, b) => {
      const aStatus = a.is_choose ? 'done' : 'waiting'
      const bStatus = b.is_choose ? 'done' : 'waiting'
      const statusOrder = {
        done: 1,
        indexed: 1,
        processing: 2,
        indexing: 2,
        parsing: 2,
        waiting: 3,
        uploaded: 3,
        parsed: 3,
        failed: 4,
        error_indexing: 4,
        error_parsing: 4
      }
      return (statusOrder[aStatus] || 5) - (statusOrder[bStatus] || 5)
    },
    sortDirections: ['ascend', 'descend']
  },
  { title: '', key: 'action', dataIndex: 'tablename', width: 40, align: 'center' }
]

const buildTableTree = (tableList) => {
  const nodeMap = new Map()
  const roots = []
  const processedIds = new Set()
  // 1. 初始化节点映射，确保 explicit folder 有 children
  tableList.forEach((table) => {
    const item = { ...table, displayName: table.tablename }
    nodeMap.set(item.table_id, item)
  })
  console.log('nodeMap', nodeMap)

  // 3. 处理剩余项 (Roots 或 路径解析)
  tableList.forEach((table) => {
    if (processedIds.has(table.table_id)) return

    const item = nodeMap.get(table.table_id)
    const normalizedName = table.tablename.replace(/\\/g, '/')
    const parts = normalizedName.split('/')

    if (parts.length === 1) {
      // Root item
      // Check if it's an explicit folder that should merge with an existing implicit one?
      roots.push(item)
    } else {
      // Path based logic for files like "A/B.txt"
      let currentLevel = roots
      let currentPath = ''

      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i]
        currentPath = currentPath ? `${currentPath}/${part}` : part

        // Find existing node in currentLevel
        let node = currentLevel.find((n) => n.tablename === part)

        if (!node) {
          node = {
            table_id: `table-${currentPath}`,
            tablename: part,
            displayName: part,
            created_at: table.created_at,
            status: 'done'
          }
          currentLevel.push(node)
        }
      }

      const tableName = parts[parts.length - 1]
      item.displayName = tableName
      currentLevel.push(item)
    }
  })
  return roots
}
// 构建文件树
const buildFileTree = (fileList) => {
  const nodeMap = new Map()
  const roots = []
  const processedIds = new Set()

  // 1. 初始化节点映射，确保 explicit folder 有 children
  fileList.forEach((file) => {
    const item = { ...file, displayName: file.filename }
    if (item.is_folder && !item.children) {
      item.children = []
    }
    nodeMap.set(item.file_id, item)
  })

  // 2. 处理 parent_id (强关联)
  fileList.forEach((file) => {
    if (file.parent_id && nodeMap.has(file.parent_id)) {
      const parent = nodeMap.get(file.parent_id)
      const child = nodeMap.get(file.file_id)
      if (parent && child) {
        if (!parent.children) parent.children = []
        parent.children.push(child)
        processedIds.add(file.file_id)
      }
    }
  })

  // 3. 处理剩余项 (Roots 或 路径解析)
  fileList.forEach((file) => {
    if (processedIds.has(file.file_id)) return

    const item = nodeMap.get(file.file_id)
    const normalizedName = file.filename.replace(/\\/g, '/')
    const parts = normalizedName.split('/')

    if (parts.length === 1) {
      // Root item
      // Check if it's an explicit folder that should merge with an existing implicit one?
      if (item.is_folder) {
        const existingIndex = roots.findIndex((n) => n.is_folder && n.filename === item.filename)
        if (existingIndex !== -1) {
          const existing = roots[existingIndex]
          // Merge children from implicit to explicit
          if (existing.children && existing.children.length > 0) {
            item.children = [...(item.children || []), ...existing.children]
          }
          // Replace implicit with explicit
          roots[existingIndex] = item
        } else {
          roots.push(item)
        }
      } else {
        roots.push(item)
      }
    } else {
      // Path based logic for files like "A/B.txt"
      let currentLevel = roots
      let currentPath = ''

      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i]
        currentPath = currentPath ? `${currentPath}/${part}` : part

        // Find existing node in currentLevel
        let node = currentLevel.find((n) => n.filename === part && n.is_folder)

        if (!node) {
          node = {
            file_id: `folder-${currentPath}`,
            filename: part,
            displayName: part,
            is_folder: true,
            children: [],
            created_at: file.created_at,
            status: 'done'
          }
          currentLevel.push(node)
        }
        currentLevel = node.children
      }

      const fileName = parts[parts.length - 1]
      item.displayName = fileName
      currentLevel.push(item)
    }
  })

  // 排序：文件夹在前，文件在后，按名称排序
  const sortNodes = (nodes) => {
    nodes.sort((a, b) => {
      if (a.is_folder && !b.is_folder) return -1
      if (!a.is_folder && b.is_folder) return 1

      if (sortField.value === 'filename') {
        return (a.filename || '').localeCompare(b.filename || '')
      } else if (sortField.value === 'created_at') {
        return new Date(b.created_at || 0) - new Date(a.created_at || 0)
      } else if (sortField.value === 'status') {
        const statusOrder = {
          done: 1,
          indexed: 1,
          processing: 2,
          indexing: 2,
          parsing: 2,
          waiting: 3,
          uploaded: 3,
          parsed: 3,
          failed: 4,
          error_indexing: 4,
          error_parsing: 4
        }
        return (statusOrder[a.status] || 5) - (statusOrder[b.status] || 5)
      }
      return 0
    })
    nodes.forEach((node) => {
      if (node.children) sortNodes(node.children)
    })
  }

  sortNodes(roots)
  return roots
}

// 过滤后的文件列表
const filteredFiles = computed(() => {
  let filtered = files.value
  const nameFilter = filenameFilter.value.trim().toLowerCase()
  const status = statusFilter.value

  // 应用过滤
  if (nameFilter || status !== 'all') {
    // 搜索/过滤模式下使用扁平列表
    return files.value
      .filter((file) => {
        const nameMatch =
          !nameFilter || (file.filename && file.filename.toLowerCase().includes(nameFilter))
        const statusMatch =
          status === 'all' ||
          file.status === status ||
          (status === 'indexed' && file.status === 'done') ||
          (status === 'error_indexing' && file.status === 'failed')
        return nameMatch && statusMatch
      })
      .map((f) => ({ ...f, displayName: f.filename }))
  }

  return buildFileTree(filtered)
})


// 过滤后的文件列表
const filteredTables = computed(() => {
  let filtered = tables.value
  const nameFilter = tablenameFilter.value.trim().toLowerCase()
  // const status = statusFilter.value

  // 应用过滤
  if (nameFilter) {
    // 搜索/过滤模式下使用扁平列表
    return tables.value
      .filter((table) => {
        const nameMatch =
          !nameFilter || (table.tablename && table.tablename.toLowerCase().includes(nameFilter))
        return nameMatch
      })
      .map((f) => ({ ...f, displayName: f.tablename }))
  }

  // return filtered
  return buildTableTree(filtered)
})

// 空状态文本
const emptyText = computed(() => {
  return filenameFilter.value ? `没有找到包含"${filenameFilter.value}"的文件` : '暂无文件'
})

const handleRefresh = () => {
  // 刷新时重置分页
  paginationConfig.value.current = 1
  store.getDatabaseInfo(undefined, true) // Skip query params for manual refresh
}

const toggleAutoRefresh = () => {
  store.toggleAutoRefresh()
}

const toggleRightPanel = () => {
  console.log(props.rightPanelVisible)
  emit('toggleRightPanel')
}

const onSelectChange = (keys, selectedRows) => {
  selectedRowKeys.value = keys
}

const onFilterChange = (e) => {
  filenameFilter.value = e.target.value
  // 过滤变化时重置到第一页
  paginationConfig.value.current = 1
}

const handleBatchChoose= () => {
  store.handleBatchChoose(true)
  isSelectionMode.value = false
}
const handleBatchUnchoose= () => {
  store.handleBatchChoose(false)
  isSelectionMode.value = false
}

const openFileDetail = (record) => {
  console.log('openFileDetail', record)
  store.openFileDetail(record)
}

const handleReindexFile = async (record) => {
  closePopover(record.tablename)
  updateTableDescriptionModalTitle.value = '修改数据库表描述'
  descriptionForm.value = record.description || ''
  singleChooseTable.value = record
  // 显示参数配置模态框
  updateTableDescriptionModalVisible.value = true
}

const handleUpdateTableDescriptionCancel = () => {
  updateTableDescriptionModalVisible.value = false
  // 重置参数为默认值
  descriptionForm.value = ''
  singleChooseTable.value = null
}
const handleUpdateTableDescriptionConfirm =  async () => {
  closePopover(singleChooseTable.value.tablename)
  const dbId = store.databaseId
  console.log('updateTableDescriptionConfirm >> ', dbId, descriptionForm.value, singleChooseTable.value)
  try {
    const newTableInfo = {
          ...singleChooseTable.value,
          description: descriptionForm.value
        }
    const newTable = {
      [singleChooseTable.value.tablename]: newTableInfo
    }
    console.log('updateTableDescriptionConfirm >> ', newTable)
    store.updateTables(newTable)
  } catch (error) {
    console.error(error)
    message.error(error.message || '更新失败')
  }
  updateTableDescriptionModalVisible.value = false
}



// 导入工具函数
import { getFileIcon, getFileIconColor, formatRelativeTime } from '@/utils/file_utils'
import { parseToShanghai } from '@/utils/time'
import ChunkParamsConfig from '@/components/ChunkParamsConfig.vue'
</script>

<style scoped>
.file-table-container {
  display: flex;
  flex-grow: 1;
  flex-direction: column;
  max-height: 100%;
  background: var(--gray-10);
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--gray-150);
  /* padding-top: 6px; */
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  padding: 8px 8px;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;

  .action-searcher {
    width: 120px;
    margin-right: 8px;
    border-radius: 6px;
    padding: 4px 8px;
    border: none;
    box-shadow: 0 0 0 1px var(--shadow-1);
  }
}

.batch-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background-color: var(--main-10);
  border-radius: 4px;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.batch-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.batch-info span {
  font-size: 12px;
  font-weight: 500;
  color: var(--gray-700);
}

.batch-actions .ant-btn {
  font-size: 12px;
  padding: 4px 8px;
  height: auto;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 4px;

  svg {
    width: 14px;
    height: 14px;
  }
}

.my-table {
  flex: 1;
  overflow: auto;
  background-color: transparent;
  min-height: 0;
  table-layout: fixed;
  padding-left: 4px;
}

.my-table .main-btn {
  padding: 0;
  height: auto;
  line-height: 1.4;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  text-decoration: none;
}

.my-table .main-btn:hover {
  cursor: pointer;
  color: var(--main-color);
}

.my-table .del-btn {
  color: var(--gray-500);
}

.my-table .download-btn {
  color: var(--gray-500);
}

.my-table .download-btn:hover {
  color: var(--main-color);
}

.my-table .rechunk-btn {
  color: var(--gray-500);
}

/* 统一设置表格操作按钮的图标尺寸 */
.my-table .table-row-actions {
  display: flex;
}

.my-table .table-row-actions button {
  display: flex;
  align-items: center;
}

.my-table .table-row-actions button svg {
  width: 16px;
  height: 16px;
}

.my-table .rechunk-btn:hover {
  color: var(--color-warning-500);
}

.my-table .del-btn:hover {
  color: var(--color-error-500);
}

.my-table .del-btn:disabled {
  cursor: not-allowed;
}

.my-table .span-type {
  display: inline-block;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: bold;
  color: var(--gray-0);
  border-radius: 4px;
  text-transform: uppercase;
  opacity: 0.9;
}

.my-table .span-type.md,
.my-table .span-type.markdown {
  background-color: var(--gray-200);
  color: var(--gray-800);
}

.auto-refresh-btn {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}

.panel-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  padding: 4px;
  color: var(--gray-600);
  transition: all 0.1s ease;
  font-size: 12px;
  width: auto;
  height: auto;

  &.expand {
    transform: scaleX(-1);
  }

  &.expanded {
    transform: scaleX(1);
  }
}

.panel-action-btn.auto-refresh-btn.ant-btn-primary {
  background-color: var(--main-color);
  border-color: var(--main-color);
  color: var(--gray-0);
}

.panel-action-btn:hover {
  background-color: var(--gray-50);
  color: var(--main-color);
  /* border: 1px solid var(--main-100); */
}

.panel-action-btn.active {
  color: var(--main-color);
  background-color: var(--gray-100);
  font-weight: 600;
  box-shadow: 0 0 0 1px var(--shadow-1);
}

.action-trigger-btn {
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--gray-500);
  transition: all 0.2s;

  &:hover {
    background-color: var(--gray-100);
    color: var(--main-color);
  }

  svg {
    width: 16px;
    height: 16px;
  }
}

/* Table row selection styling */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background-color: var(--main-5);
}

:deep(.ant-table-tbody > tr.ant-table-row-selected.ant-table-row:hover > td) {
  background-color: var(--main-20);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--main-5);
}

.folder-row {
  display: flex;
  align-items: center;
  cursor: pointer;

  &:hover {
    color: var(--main-color);
  }
}

:deep(.drop-over-folder) {
  background-color: var(--primary-50) !important;
  outline: 2px dashed var(--main-color);
  outline-offset: -2px;
  z-index: 10;

  td {
    background-color: transparent !important;
  }
}

.upload-btn-group {
  display: flex;
  align-items: center;
  gap: 8px;

  .upload-btn {
    height: 28px;
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
  }
}
</style>

<style lang="less">
.file-action-popover {
  .ant-popover-inner {
    padding: 4px;
  }

  .ant-popover-inner {
    border-radius: 8px;
    border: 1px solid var(--gray-150);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }

  .ant-popover-arrow {
    display: none;
  }
}

.file-action-list {
  display: flex;
  flex-direction: column;
  gap: 2px;

  .ant-btn {
    text-align: left;
    height: 30px;
    font-size: 14px;
    display: flex;
    align-items: center;
    border-radius: 6px;
    padding: 0 8px;
    border: none;
    box-shadow: none;

    &:hover {
      background-color: var(--gray-50);
      color: var(--main-color);
    }

    &.ant-btn-dangerous:hover {
      background-color: var(--color-error-50);
      color: var(--color-error-500);
    }

    .anticon,
    .lucide {
      margin-right: 10px;
    }

    span {
      font-size: 13px;
    }
  }

  .ant-btn:disabled {
    background-color: transparent;
    color: var(--gray-300);
    cursor: not-allowed;
  }
}

.file-info-popover {
  .ant-popover-inner {
    border-radius: 8px;
  }

  // .ant-popover-inner-content {
  //   padding: 16px;
  // }

  .file-info-card {
    min-width: 120px;
    max-width: 320px;
    font-size: 13px;

    .info-row {
      display: flex;
      margin-bottom: 8px;
      line-height: 1.5;
      align-items: flex-start;

      &:last-child {
        margin-bottom: 0;
      }

      .label {
        color: var(--gray-500);
        width: 40px;
        flex-shrink: 0;
        text-align: right;
        margin-right: 12px;
        font-weight: 500;
      }

      .value {
        color: var(--gray-900);
        word-break: break-all;
        flex: 1;
        font-family: monospace; /* Optional: for ID and numbers */
      }

      &.error {
        .label {
          color: var(--color-error-500);
        }
        .value {
          color: var(--color-error-500);
        }
      }
    }
  }
}
</style>
