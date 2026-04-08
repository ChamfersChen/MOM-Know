<script setup>
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { onMounted, ref, reactive } from 'vue'
import { message } from 'ant-design-vue'

const agentStore = useAgentStore()
const userStore = useUserStore()
const themeStore = useThemeStore()

const showPasswordModal = ref(false)
const passwordLoading = ref(false)
const passwordForm = reactive({
  newPassword: '',
  confirmPassword: ''
})

onMounted(async () => {
  if (userStore.isLoggedIn) {
    await agentStore.initialize()
    // 如果用户需要修改密码，且本次会话没有跳过，则显示弹窗
    if (userStore.requirePasswordChange && !sessionStorage.getItem('skipPasswordChange')) {
      showPasswordModal.value = true
    }
  }
})

const handleChangePassword = async () => {
  if (passwordForm.newPassword.length < 6) {
    message.error('密码长度至少为 6 个字符')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    message.error('两次输入的密码不一致')
    return
  }

  try {
    passwordLoading.value = true
    await userStore.changePassword(passwordForm.newPassword)
    message.success('密码修改成功')
    showPasswordModal.value = false
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch (error) {
    console.error('修改密码失败:', error)
    message.error(error.message || '修改密码失败')
  } finally {
    passwordLoading.value = false
  }
}

const skipPasswordChange = () => {
  showPasswordModal.value = false
  // 记录本次会话已跳过密码修改
  sessionStorage.setItem('skipPasswordChange', 'true')
}
</script>
<template>
  <a-config-provider :theme="themeStore.currentTheme" :locale="zhCN">
    <router-view />

    <a-modal
      v-model:open="showPasswordModal"
      title="请修改密码"
      :maskClosable="false"
      :closable="true"
      :keyboard="false"
      :confirmLoading="passwordLoading"
      @ok="handleChangePassword"
      @cancel="skipPasswordChange"
      okText="确认修改"
      cancelText="稍后修改"
    >
      <div class="password-modal-content">
        <p class="password-modal-tip">
          您的账户使用默认密码登录，为了账户安全，请及时修改密码。
        </p>
        <a-form layout="vertical">
          <a-form-item label="新密码" required>
            <a-input-password
              v-model:value="passwordForm.newPassword"
              placeholder="请输入新密码（至少6位）"
            />
          </a-form-item>
          <a-form-item label="确认密码" required>
            <a-input-password
              v-model:value="passwordForm.confirmPassword"
              placeholder="请再次输入新密码"
            />
          </a-form-item>
        </a-form>
      </div>
    </a-modal>
  </a-config-provider>
</template>

<style>
.password-modal-content {
  padding: 8px 0;
}

.password-modal-tip {
  margin-bottom: 16px;
  padding: 12px;
  background-color: #fff7e6;
  border-radius: 6px;
  font-size: 14px;
  color: #ad8b00;
}
</style>
