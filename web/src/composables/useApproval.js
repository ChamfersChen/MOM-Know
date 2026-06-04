import { reactive } from 'vue'
import { normalizeQuestions } from '@/utils/questionUtils'

const extractQuestionPayload = (chunk) => {
  const interruptInfo = chunk?.interrupt_info || {}
  const rawQuestions = chunk?.questions || interruptInfo?.questions || []
  const source = chunk?.source || interruptInfo?.source || 'interrupt'
  const questions = normalizeQuestions(rawQuestions)

  return {
    questions,
    source
  }
}

export function useApproval({ getThreadState, fetchThreadMessages }) {
  const approvalState = reactive({
    showModal: false,
    questions: [],
    status: '',
    threadId: null,
    parentRunId: null
  })

  const processApprovalInStream = (chunk, threadId, currentAgentId) => {
    if (
      chunk.status !== 'ask_user_question_required' &&
      chunk.status !== 'human_approval_required'
    ) {
      return false
    }

    const threadState = getThreadState(threadId)
    if (!threadState) return false

    const payload = extractQuestionPayload(chunk)
    if (!payload.questions.length) return false

    threadState.isStreaming = false

    approvalState.showModal = true
    approvalState.questions = payload.questions
    approvalState.status = chunk.status || ''
    approvalState.threadId = chunk.thread_id || threadId
    approvalState.parentRunId = chunk.run_id || null

    fetchThreadMessages({ agentId: currentAgentId, threadId })

    return true
  }

  const resetApprovalState = () => {
    approvalState.showModal = false
    approvalState.questions = []
    approvalState.status = ''
    approvalState.threadId = null
    approvalState.parentRunId = null
  }

  return {
    approvalState,
    processApprovalInStream,
    resetApprovalState
  }
}
