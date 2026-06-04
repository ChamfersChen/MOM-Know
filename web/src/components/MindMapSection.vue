<template>
  <div class="mindmap-section">
    <div class="section-content">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <a-spin size="small" />
        <span>加载中...</span>
      </div>

      <!-- 生成中状态 -->
      <div v-else-if="generating" class="generating-state">
        <a-spin size="small" />
        <span>AI 正在生成思维导图...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!mindmapData" class="empty-state">
        <div class="empty-icon">
          <MapIcon :size="24" />
        </div>
        <p class="empty-title">暂无思维导图</p>
        <p class="empty-description">从当前知识库内容生成结构化导图。</p>
        <button
          type="button"
          class="lucide-icon-btn mindmap-primary-action"
          @click="generateMindmap"
        >
          <Sparkles :size="14" />
          <span>生成思维导图</span>
        </button>
      </div>

      <!-- 思维导图显示 -->
      <div v-else class="mindmap-container">
        <div class="mindmap-toolbar">
          <a-space :size="8">
            <button
              type="button"
              class="lucide-icon-btn mindmap-toolbar-btn"
              :disabled="generating"
              @click="refreshMindmap"
              title="重新生成"
            >
              <RefreshCw :size="14" :class="{ spin: generating }" />
              <span class="toolbar-text">重新生成</span>
            </button>
            <button
              type="button"
              class="lucide-icon-btn mindmap-toolbar-btn"
              @click="fitView"
              title="适应视图"
            >
              <Maximize2 :size="14" />
              <span class="toolbar-text">适应视图</span>
            </button>
          </a-space>
        </div>
        <div class="mindmap-svg-container">
          <svg ref="mindmapSvg" class="mindmap-svg"></svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { RefreshCw, Map as MapIcon, Sparkles, Maximize2 } from 'lucide-vue-next'
import { mindmapApi } from '@/apis/knowledge_api'
import { Markmap } from 'markmap-view'
import { Transformer } from 'markmap-lib'

const props = defineProps({
  kbId: {
    type: String,
    required: true
  }
})

// ============================================================================
// 状态管理
// ============================================================================

const loading = ref(false)
const generating = ref(false)
const mindmapData = ref(null)
const mindmapSvg = ref(null)
let markmapInstance = null

// ============================================================================
// 方法
// ============================================================================

/**
 * 加载思维导图
 */
const loadMindmap = async () => {
  if (!props.kbId) return

  try {
    loading.value = true
    const response = await mindmapApi.getByDatabase(props.kbId)

    const mindmap = response.mindmap || null
    mindmapData.value = mindmap

    if (markmapInstance) {
      markmapInstance.destroy()
      markmapInstance = null
    }

    if (mindmap) {
      await nextTick()

      // 延迟渲染，确保DOM完全更新
      setTimeout(() => {
        renderMindmap(mindmap)
      }, 100)
    }
  } catch (error) {
    // 如果是404错误，说明还没有生成，静默处理
    if (
      error?.message?.includes('404') ||
      error?.message?.includes('不存在') ||
      error?.message?.includes('还没有生成')
    ) {
      mindmapData.value = null
    } else {
      console.error('加载思维导图失败:', error)
      const errorMsg = error?.message || String(error)
      message.error('加载思维导图失败: ' + errorMsg)
    }
  } finally {
    loading.value = false
  }
}

/**
 * 生成思维导图
 */
const generateMindmap = async () => {
  if (!props.kbId) return

  try {
    generating.value = true

    const response = await mindmapApi.generateMindmap(
      props.kbId,
      [], // 使用所有文件
      '' // 无自定义提示
    )

    mindmapData.value = response.mindmap

    // 等待DOM更新
    await nextTick()

    // 再延迟一点，确保SVG元素完全渲染
    setTimeout(() => {
      renderMindmap(response.mindmap)
      message.success('思维导图生成成功！')
    }, 100)
  } catch (error) {
    console.error('生成思维导图失败:', error)
    const errorMsg = error?.message || String(error)
    message.error('生成失败: ' + errorMsg)
  } finally {
    generating.value = false
  }
}

/**
 * 刷新思维导图
 */
const refreshMindmap = async () => {
  await generateMindmap()
}

/**
 * 将JSON转换为Markdown
 */
const jsonToMarkdown = (node, level = 0) => {
  if (!node || !node.content) return ''

  const indent = '#'.repeat(level + 1)
  let markdown = `${indent} ${node.content}\n\n`

  if (node.children && node.children.length > 0) {
    for (const child of node.children) {
      markdown += jsonToMarkdown(child, level + 1)
    }
  }

  return markdown
}

/**
 * 渲染思维导图
 */
const renderMindmap = (data, retryCount = 0) => {
  if (!data) return

  if (!mindmapSvg.value) {
    // 如果SVG引用还没准备好，最多重试3次
    if (retryCount < 3) {
      setTimeout(() => {
        renderMindmap(data, retryCount + 1)
      }, 100)
      return
    } else {
      console.error('无法获取SVG容器，渲染失败')
      message.error('渲染失败：无法找到SVG容器')
      return
    }
  }

  try {
    // 清空之前的实例
    if (markmapInstance) {
      markmapInstance.destroy()
    }

    // 将JSON转换为Markdown
    const markdown = jsonToMarkdown(data)

    // 使用Transformer转换
    const transformer = new Transformer()
    const { root } = transformer.transform(markdown)

    // 创建Markmap实例
    markmapInstance = Markmap.create(mindmapSvg.value, {
      duration: 300,
      maxWidth: 200,
      nodeMinHeight: 24,
      paddingX: 8,
      spacingVertical: 5,
      spacingHorizontal: 60
    })

    markmapInstance.setData(root)
    markmapInstance.fit()

    // 延迟再次适应，确保布局完全稳定
    setTimeout(() => {
      if (markmapInstance) {
        markmapInstance.fit()
      }
    }, 300)
  } catch (error) {
    console.error('渲染思维导图失败:', error)
    message.error('渲染失败: ' + error.message)
  }
}

/**
 * 适应视图
 */
const fitView = () => {
  if (markmapInstance) {
    markmapInstance.fit()
  }
}

/**
 * 暴露给父组件的方法
 */
defineExpose({
  refreshMindmap,
  generateMindmap
})

// ============================================================================
// 生命周期
// ============================================================================

// 监听数据库ID变化
watch(
  () => props.kbId,
  (newId) => {
    if (newId) {
      loadMindmap()
    }
  },
  { immediate: true }
)

// 监听容器大小变化，自动适应
let resizeObserver = null

onMounted(() => {
  // 设置ResizeObserver监听容器大小变化
  nextTick(() => {
    if (mindmapSvg.value) {
      const container = mindmapSvg.value.parentElement
      if (container) {
        resizeObserver = new ResizeObserver(() => {
          if (markmapInstance) {
            markmapInstance.fit()
          }
        })
        resizeObserver.observe(container)
      }
    }
  })
})

// 清理
onUnmounted(() => {
  if (markmapInstance) {
    markmapInstance.destroy()
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})
</script>

<style scoped lang="less">
.mindmap-section {
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.section-content {
  flex: 1;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.loading-state,
.generating-state,
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px;
  color: var(--gray-500);
  font-size: 13px;
  text-align: center;

  p {
    margin: 0;
  }
}

.empty-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  background: var(--main-30);
  color: var(--main-color);
}

.empty-title {
  margin-top: 2px;
  color: var(--gray-900);
  font-size: 15px;
  font-weight: 600;
}

.empty-description {
  max-width: 280px;
  color: var(--gray-500);
  line-height: 1.5;
}

.mindmap-primary-action {
  min-height: 32px;
  margin-top: 4px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--main-600);
  color: var(--main-0);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  appearance: none;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;

  &:hover,
  &:focus-visible {
    background: var(--main-700);
    color: var(--main-0);
    outline: none;
  }

  &:focus-visible {
    box-shadow: 0 0 0 2px var(--main-200);
  }
}

.mindmap-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.mindmap-toolbar {
  padding: 8px 12px;
  background: var(--gray-0);
  border-bottom: 1px solid var(--gray-150);
  display: flex;
  align-items: center;
  justify-content: flex-end;

  .toolbar-text {
    margin-left: 4px;
    font-size: 13px;
  }
}

.mindmap-toolbar-btn {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-600);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  appearance: none;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;

  &:hover,
  &:focus-visible {
    background: var(--gray-50);
    color: var(--main-color);
    outline: none;
  }

  &:focus-visible {
    box-shadow: 0 0 0 2px var(--main-100);
  }

  &:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  &:disabled:hover {
    background: transparent;
    color: var(--gray-600);
  }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.mindmap-svg-container {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: var(--gray-0);
}

.mindmap-svg {
  width: 100%;
  height: 100%;
  min-height: 150px;
  display: block;
}

// 确保父容器有高度
:deep(.markmap) {
  width: 100% !important;
  height: 100% !important;
}
</style>
