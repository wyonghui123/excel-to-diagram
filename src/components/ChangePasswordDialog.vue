<template>
  <AppModal
    :model-value="visible"
    title="修改密码"
    width="440px"
    @close="$emit('close')"
  >
    <div class="change-password-body">
      <AppInput
        v-model="oldPassword"
        type="password"
        label="旧密码"
        placeholder="请输入旧密码"
        required
        show-password-toggle
      />

      <AppInput
        v-model="newPassword"
        type="password"
        label="新密码"
        placeholder="请输入新密码（至少6位）"
        required
        show-password-toggle
      />

      <AppInput
        v-model="confirmPassword"
        type="password"
        label="确认新密码"
        placeholder="请再次输入新密码"
        required
        show-password-toggle
        :error="confirmError"
      />
    </div>

    <template #footer>
      <AppButton variant="secondary" @click="$emit('close')">取消</AppButton>
      <AppButton variant="primary" :loading="submitting" @click="handleSubmit">确认修改</AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useMessage } from '@/composables/useMessage'
import AppModal from '@/components/common/AppModal/AppModal.vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppInput from '@/components/common/AppInput/AppInput.vue'

defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const authStore = useAuthStore()
const message = useMessage()
const emit = defineEmits(['close'])

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)

const confirmError = computed(() => {
  if (!confirmPassword.value) return ''
  if (confirmPassword.value !== newPassword.value) return '两次输入的密码不一致'
  return ''
})

async function handleSubmit() {
  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    message.error('请填写所有字段')
    return
  }

  if (newPassword.value.length < 6) {
    message.error('新密码长度不能少于6位')
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    message.error('两次输入的新密码不一致')
    return
  }

  submitting.value = true
  const result = await authStore.changePassword(oldPassword.value, newPassword.value)
  submitting.value = false

  if (result.success) {
    message.success('密码修改成功')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    setTimeout(() => emit('close'), 1500)
  } else {
    message.error(result.message || '密码修改失败')
  }
}
</script>

<style scoped lang="scss">
.change-password-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
</style>