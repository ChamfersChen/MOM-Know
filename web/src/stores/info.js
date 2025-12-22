import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { brandApi } from '@/apis/system_api'

export const useInfoStore = defineStore('info', () => {
  // 状态
  const infoConfig = ref({})
  const isLoading = ref(false)
  const isLoaded = ref(false)
  const debugMode = ref(false)

  // 计算属性 - 组织信息
  const organization = computed(() => infoConfig.value.organization || {
    name: "LCMOM",
    logo: "/favicon.svg",
    avatar: "/avatar.jpg"
  })

  // 计算属性 - 品牌信息
  const branding = computed(() => infoConfig.value.branding || {
    name: "MOM-Know",
    title: "MOM-Know",
    subtitle: "MOM-Know: 更智能的MOM智能体平台",
    description: "结合知识库与工具，提供更准确、更全面的回答"
  })

  // 计算属性 - 功能特性
  const features = computed(() => infoConfig.value.features || [{
    label: "📚 灵活知识库",
    value: "2600+",
    description: "开发者社区的认可与支持",
    icon: "stars"
  }, {
    label: "已解决 Issues",
    value: "200+",
    description: "持续改进和问题解决能力",
    icon: "issues"
  }, {
    label: "累计 Commits",
    value: "1000+",
    description: "活跃的开发迭代和功能更新",
    icon: "commits"
  }, {
    label: "开源协议",
    value: "MIT 协议",
    description: "完全免费，支持商业使用",
    icon: "license"
  }])

  const actions = computed(() => infoConfig.value.actions || [{
    name: "演示视频",
    icon: "video",
    url: "https://www.bilibili.com/video/BV1DF14BTETq"
  }, {
    name: "文档中心",
    icon: "docs",
    url: "https://xerrors.github.io/Yuxi-Know/"
  }, {
    name: "提交 Issue",
    icon: "issue",
    url: "https://github.com/xerrors/Yuxi-Know/issues/new/choose"
  }, {
    name: "开发路线图",
    icon: "roadmap",
    url: "https://github.com/xerrors/Yuxi-Know#roadmap"
  }])

  // 计算属性 - 页脚信息
  const footer = computed(() => infoConfig.value.footer || {
    copyright: "© 江南语析 2025 [WIP] v0.12.138"
  })

  // 动作方法
  function setInfoConfig(newConfig) {
    infoConfig.value = newConfig
    isLoaded.value = true
  }

  function setDebugMode(enabled) {
    debugMode.value = enabled
  }

  function toggleDebugMode() {
    debugMode.value = !debugMode.value
  }

  async function loadInfoConfig(force = false) {
    // 如果已经加载过且不强制刷新，则不重新加载
    if (isLoaded.value && !force) {
      return infoConfig.value
    }

    try {
      isLoading.value = true
      const response = await brandApi.getInfoConfig()

      if (response.success && response.data) {
        setInfoConfig(response.data)
        console.debug('信息配置加载成功:', response.data)
        return response.data
      } else {
        console.warn('信息配置加载失败，使用默认配置')
        return null
      }
    } catch (error) {
      console.error('加载信息配置时发生错误:', error)
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function reloadInfoConfig() {
    try {
      isLoading.value = true
      const response = await brandApi.reloadInfoConfig()

      if (response.success && response.data) {
        setInfoConfig(response.data)
        console.debug('信息配置重新加载成功:', response.data)
        return response.data
      } else {
        console.warn('信息配置重新加载失败')
        return null
      }
    } catch (error) {
      console.error('重新加载信息配置时发生错误:', error)
      return null
    } finally {
      isLoading.value = false
    }
  }

    return {
    // 状态
    infoConfig,
    isLoading,
    isLoaded,
    debugMode,

    // 计算属性
    organization,
    branding,
    features,
    footer,
    actions,

    // 方法
    setInfoConfig,
    setDebugMode,
    toggleDebugMode,
    loadInfoConfig,
    reloadInfoConfig
  }
})
