<template>
  <span class="mention-text-renderer">
    <template v-for="segment in segments" :key="`${segment.kind}-${segment.start}-${segment.end}`">
      <span v-if="segment.kind === 'text'" class="mention-text-segment">{{ segment.text }}</span>
      <span
        v-else
        class="mention-ref-token"
        :class="[`mention-ref-${segment.type}`, { 'mention-ref-editable': editable }]"
        :contenteditable="editable ? 'false' : undefined"
        :data-mention-raw="editable ? segment.raw : undefined"
        :data-mention-type="editable ? segment.type : undefined"
        :data-mention-value="editable ? segment.value : undefined"
        :title="segment.raw"
      >
        <component
          :is="getMentionIconComponent(segment.type, segment.value)"
          class="mention-ref-icon"
          :style="getMentionIconStyle(segment.type, segment.value)"
          :stroke-width="MENTION_ICON_STROKE_WIDTH"
          :size="MENTION_ICON_SIZE"
        />
        <span class="mention-ref-label">{{ getTokenLabel(segment) }}</span>
      </span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import {
  getMentionIconComponent,
  getMentionIconStyle,
  MENTION_ICON_SIZE,
  MENTION_ICON_STROKE_WIDTH
} from '@/utils/mention_icon_utils'
import { getMentionDisplayLabel, parseMentionText } from '@/utils/mention_utils'

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  editable: {
    type: Boolean,
    default: false
  },
  displayLabels: {
    type: Object,
    default: () => ({})
  }
})

const segments = computed(() => parseMentionText(props.content))

const getTokenLabel = (segment) =>
  getMentionDisplayLabel(segment.type, segment.value, props.displayLabels)
</script>

<style lang="less" scoped>
.mention-text-renderer {
  white-space: inherit;
}

.mention-text-segment {
  white-space: inherit;
}

.mention-ref-token {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  max-width: 100%;
  color: var(--main-700);
  line-height: normal;
  vertical-align: baseline;
  white-space: nowrap;
}

.mention-ref-editable {
  user-select: all;
}

.mention-ref-icon {
  position: relative;
  top: 2px;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  font-size: 13px;
  line-height: 1;
  margin-left: 4px;
}

.mention-ref-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: normal;
  font-weight: 500;
}
</style>
