import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSelectedGraphGroupsStore = defineStore('selectedGraphGroups', () => {
  const selectedGroup = ref(null)
  const modifiedTables = ref({})

  const loadFromLocalStorage = () => {
    try {
      const saved = localStorage.getItem('selectedGraphGroup')
      if (saved) {
        selectedGroup.value = JSON.parse(saved)
      }
      const savedModified = localStorage.getItem('modifiedTables')
      if (savedModified) {
        modifiedTables.value = JSON.parse(savedModified)
      }
    } catch (e) {
      console.error('Failed to load selected group from localStorage:', e)
    }
  }

  const saveToLocalStorage = () => {
    try {
      if (selectedGroup.value) {
        localStorage.setItem('selectedGraphGroup', JSON.stringify(selectedGroup.value))
      } else {
        localStorage.removeItem('selectedGraphGroup')
      }
      localStorage.setItem('modifiedTables', JSON.stringify(modifiedTables.value))
    } catch (e) {
      console.error('Failed to save selected group to localStorage:', e)
    }
  }

  const selectGroup = (group) => {
    selectedGroup.value = {
      dbType: group.dbType,
      host: group.host,
      port: group.port,
      importedAt: new Date().toISOString()
    }
    modifiedTables.value = {}
    saveToLocalStorage()
  }

  const clearSelection = () => {
    selectedGroup.value = null
    modifiedTables.value = {}
    saveToLocalStorage()
  }

  const markTableModified = (dbId, tableId) => {
    if (!selectedGroup.value) return
    
    const groupKey = `${selectedGroup.value.dbType}:${selectedGroup.value.host}:${selectedGroup.value.port}`
    if (!modifiedTables.value[groupKey]) {
      modifiedTables.value[groupKey] = []
    }
    
    const tableKey = `${dbId}:${tableId}`
    if (!modifiedTables.value[groupKey].includes(tableKey)) {
      modifiedTables.value[groupKey].push(tableKey)
      saveToLocalStorage()
    }
  }

  const clearModifiedTables = (groupKey) => {
    if (modifiedTables.value[groupKey]) {
      modifiedTables.value[groupKey] = []
      saveToLocalStorage()
    }
  }

  const isGroupSelected = (group) => {
    if (!selectedGroup.value) return false
    return selectedGroup.value.dbType === group.dbType && 
           selectedGroup.value.host === group.host && 
           selectedGroup.value.port === group.port
  }

  const getGroupKey = (group) => {
    return `${group.dbType}:${group.host}:${group.port}`
  }

  const hasModifiedTables = (group) => {
    const groupKey = getGroupKey(group)
    return modifiedTables.value[groupKey] && modifiedTables.value[groupKey].length > 0
  }

  const isAnyGroupSelected = computed(() => selectedGroup.value !== null)

  loadFromLocalStorage()

  return {
    selectedGroup,
    modifiedTables,
    selectGroup,
    clearSelection,
    markTableModified,
    clearModifiedTables,
    isGroupSelected,
    hasModifiedTables,
    getGroupKey,
    isAnyGroupSelected,
    loadFromLocalStorage
  }
})
