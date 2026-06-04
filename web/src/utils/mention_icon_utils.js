import { FolderFilled } from '@ant-design/icons-vue'
import { BookMarked, BookOpen, Bot, Plug } from 'lucide-vue-next'
import { getFileIcon, getFileIconColor } from '@/utils/file_utils'

export const MENTION_ICON_SIZE = 15
export const MENTION_ICON_STROKE_WIDTH = 2.2

const MENTION_TYPE_ICON_COMPONENTS = {
  knowledge: BookOpen,
  skill: BookMarked,
  mcp: Plug,
  subagent: Bot
}

export const getMentionIconComponent = (type, value = '') => {
  if (type === 'file') {
    return String(value || '').endsWith('/') ? FolderFilled : getFileIcon(value)
  }
  return MENTION_TYPE_ICON_COMPONENTS[type] || Plug
}

export const getMentionIconStyle = (type, value = '') => {
  if (type !== 'file') return null
  return {
    color: String(value || '').endsWith('/') ? '#ffa940' : getFileIconColor(value)
  }
}
