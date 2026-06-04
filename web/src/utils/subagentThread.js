// 复刻后端 yuxi/utils/subagent_thread_utils.py 的 make_child_thread_id：
// child_thread_id = "subagent_" + sha256("{parent}:{slug}:{tool_call_id}")[:55]
// 子智能体由 graph.ainvoke 独立调用，流式事件不带 tool_call_id，前端据此自行推算 child_thread_id。
const PREFIX = 'subagent_'
const DIGEST_LENGTH = 64 - PREFIX.length

export async function makeChildThreadId(parentThreadId, agentSlug, toolCallId) {
  if (!parentThreadId || !agentSlug || !toolCallId) return ''
  const data = new TextEncoder().encode(`${parentThreadId}:${agentSlug}:${toolCallId}`)
  const buffer = await crypto.subtle.digest('SHA-256', data)
  const hex = Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
  return `${PREFIX}${hex.slice(0, DIGEST_LENGTH)}`
}
