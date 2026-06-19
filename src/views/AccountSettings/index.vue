<template>
  <div class="account-settings-page">
    <div class="page-header">
      <h1 class="page-title">账户设置</h1>
      <p class="page-subtitle">管理您的个人信息和安全设置</p>
    </div>

    <div class="settings-layout">
      <nav class="settings-nav">
        <button
          v-for="nav in navItems"
          :key="nav.key"
          class="nav-item"
          :class="{ active: activeNav === nav.key }"
          @click="activeNav = nav.key"
        >
          <AppIcon :name="nav.icon" size="16" />
          <span>{{ nav.label }}</span>
        </button>
      </nav>

      <main class="settings-content">
        <div v-show="activeNav === 'profile'" class="section">
          <AppCard>
            <template #header>
              <div class="card-header">
                <div class="card-header-left">
                  <AppIcon name="user" size="18" />
                  <span>个人信息</span>
                </div>
              </div>
            </template>

            <div class="profile-view" v-if="!isEditingProfile">
              <div class="profile-avatar-row">
                <div class="profile-avatar">{{ avatarText }}</div>
                <div class="profile-info">
                  <div class="profile-username">{{ profileForm.username }}</div>
                  <div class="profile-role">{{ userRoles }}</div>
                </div>
              </div>

              <div class="profile-fields">
                <div class="profile-field">
                  <span class="field-label">用户名</span>
                  <span class="field-value">{{ profileForm.username }}</span>
                </div>
                <div class="profile-field">
                  <span class="field-label">显示名称</span>
                  <span class="field-value">{{ profileForm.displayName || '-' }}</span>
                </div>
                <div class="profile-field">
                  <span class="field-label">电子邮件</span>
                  <span class="field-value">{{ profileForm.email || '-' }}</span>
                </div>
              </div>

              <div class="card-footer">
                <AppButton variant="primary" @click="startEditProfile">
                  <AppIcon name="edit" size="14" />
                  编辑资料
                </AppButton>
              </div>
            </div>

            <div class="profile-edit" v-else>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">用户名</label>
                  <AppInput
                    v-model="profileForm.username"
                    placeholder="请输入用户名"
                    disabled
                  />
                  <span class="form-hint">用户名不可修改</span>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">显示名称</label>
                  <AppInput
                    v-model="profileForm.displayName"
                    placeholder="请输入显示名称"
                    :error="profileErrors.displayName"
                  />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">电子邮件</label>
                  <AppInput
                    v-model="profileForm.email"
                    placeholder="请输入电子邮件"
                    :error="profileErrors.email"
                  />
                </div>
              </div>

              <div v-if="profileSubmitError" class="submit-error">
                <AppIcon name="warning" size="14" />
                {{ profileSubmitError }}
              </div>

              <div class="card-footer">
                <AppButton variant="secondary" @click="cancelEditProfile">取消</AppButton>
                <AppButton variant="primary" :loading="profileSubmitting" @click="saveProfile">
                  保存修改
                </AppButton>
              </div>
            </div>
          </AppCard>
        </div>

        <div v-show="activeNav === 'security'" class="section">
          <AppCard>
            <template #header>
              <div class="card-header">
                <div class="card-header-left">
                  <AppIcon name="lock" size="18" />
                  <span>修改密码</span>
                </div>
              </div>
            </template>

            <div class="password-form">
              <div v-if="!authStore.mustChangePassword" class="form-intro">
                为保障账户安全，建议您定期更换密码
              </div>

              <div v-if="authStore.mustChangePassword" class="password-force-notice">
                <AppIcon name="warning" size="16" />
                <span>您的密码已被管理员重置，请设置新密码</span>
              </div>

              <div class="form-row">
                <div class="form-group" v-if="!authStore.mustChangePassword">
                  <label class="form-label">旧密码 <span class="required">*</span></label>
                  <AppInput
                    v-model="passwordForm.oldPassword"
                    type="password"
                    placeholder="请输入旧密码"
                    show-password-toggle
                    :error="passwordErrors.oldPassword"
                  />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">新密码 <span class="required">*</span></label>
                  <AppInput
                    v-model="passwordForm.newPassword"
                    type="password"
                    placeholder="请输入新密码（至少6位）"
                    show-password-toggle
                    :error="passwordErrors.newPassword"
                  />
                  <div class="password-strength" v-if="passwordForm.newPassword">
                    <div class="strength-bar">
                      <div
                        class="strength-fill"
                        :class="passwordStrength.class"
                        :style="{ width: passwordStrength.percent + '%' }"
                      ></div>
                    </div>
                    <span class="strength-text" :class="passwordStrength.class">
                      {{ passwordStrength.label }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">确认新密码 <span class="required">*</span></label>
                  <AppInput
                    v-model="passwordForm.confirmPassword"
                    type="password"
                    placeholder="请再次输入新密码"
                    show-password-toggle
                    :error="passwordErrors.confirmPassword"
                  />
                </div>
              </div>

              <div v-if="passwordSubmitError" class="submit-error">
                <AppIcon name="warning" size="14" />
                {{ passwordSubmitError }}
              </div>

              <div class="card-footer">
                <AppButton variant="primary" :loading="passwordSubmitting" @click="savePassword">
                  {{ authStore.mustChangePassword ? '设置密码' : '修改密码' }}
                </AppButton>
              </div>
            </div>
          </AppCard>

          <AppCard class="security-tips">
            <template #header>
              <div class="card-header">
                <div class="card-header-left">
                  <AppIcon name="info" size="18" />
                  <span>安全建议</span>
                </div>
              </div>
            </template>
            <ul class="tips-list">
              <li>密码长度至少 6 位</li>
              <li>建议使用大小写字母、数字和特殊字符的组合</li>
              <li>不要在多个网站使用相同的密码</li>
              <li>定期更换密码可以提高账户安全性</li>
            </ul>
          </AppCard>
        </div>

        <div v-show="activeNav === 'preferences'" class="section">
          <AppCard>
            <template #header>
              <div class="card-header">
                <div class="card-header-left">
                  <AppIcon name="setting" size="18" />
                  <span>区域和语言</span>
                </div>
              </div>
            </template>

            <div class="preferences-form">
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">语言</label>
                  <select v-model="preferenceForm.locale" class="select-input">
                    <option v-for="opt in localeOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">时区</label>
                  <select v-model="preferenceForm.timezone" class="select-input">
                    <option v-for="tz in commonTimezones" :key="tz" :value="tz">
                      {{ tz }}
                    </option>
                  </select>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">日期格式</label>
                  <div class="radio-group">
                    <label
                      v-for="opt in dateStyleOptions"
                      :key="opt.value"
                      class="radio-item"
                      :class="{ active: preferenceForm.dateStyle === opt.value }"
                    >
                      <input
                        type="radio"
                        :value="opt.value"
                        v-model="preferenceForm.dateStyle"
                        class="radio-input"
                      />
                      <span class="radio-label">{{ opt.label }}</span>
                      <span class="radio-hint">{{ opt.hint }}</span>
                    </label>
                  </div>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">时间格式</label>
                  <div class="radio-group">
                    <label
                      v-for="opt in timeStyleOptions"
                      :key="opt.value"
                      class="radio-item"
                      :class="{ active: preferenceForm.timeStyle === opt.value }"
                    >
                      <input
                        type="radio"
                        :value="opt.value"
                        v-model="preferenceForm.timeStyle"
                        class="radio-input"
                      />
                      <span class="radio-label">{{ opt.label }}</span>
                      <span class="radio-hint">{{ opt.hint }}</span>
                    </label>
                  </div>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">时间制式</label>
                  <div class="radio-group inline">
                    <label
                      v-for="opt in hourCycleOptions"
                      :key="opt.value"
                      class="radio-item"
                      :class="{ active: preferenceForm.hourCycle === opt.value }"
                    >
                      <input
                        type="radio"
                        :value="opt.value"
                        v-model.number="preferenceForm.hourCycle"
                        class="radio-input"
                      />
                      <span class="radio-label">{{ opt.label }}</span>
                    </label>
                  </div>
                </div>
              </div>

              <div class="preview-section">
                <label class="form-label">预览</label>
                <div class="preview-box">
                  <span class="preview-text">{{ previewFormatted }}</span>
                </div>
              </div>

              <div class="card-footer">
                <AppButton variant="primary" :loading="prefSubmitting" @click="savePreferences">
                  保存偏好设置
                </AppButton>
              </div>
            </div>
          </AppCard>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useMessage } from '@/composables/useMessage'
import { useUserPreferencesStore } from '@/stores/userPreferences'
import { dateFormatService } from '@/services/DateFormatService'
import { AppCard, AppButton, AppInput, AppIcon } from '@/components/common'
import * as authService from '@/services/authService'

const authStore = useAuthStore()
const prefStore = useUserPreferencesStore()
const message = useMessage()

const activeNav = ref('profile')
const isEditingProfile = ref(false)
const profileSubmitting = ref(false)
const profileSubmitError = ref('')
const passwordSubmitting = ref(false)
const passwordSubmitError = ref('')

const profileForm = reactive({
  username: '',
  displayName: '',
  email: ''
})

const profileErrors = reactive({
  displayName: '',
  email: ''
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const passwordErrors = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const prefSubmitting = ref(false)
const prefErrors = reactive({})

const preferenceForm = reactive({
  locale: 'zh-CN',
  timezone: 'Asia/Shanghai',
  dateStyle: 'medium',
  timeStyle: 'short',
  hourCycle: 24
})

const localeOptions = [
  { value: 'zh-CN', label: '中文（简体）' },
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' }
]

const dateStyleOptions = [
  { value: 'full', label: '完整', hint: '如: 2025年5月24日 星期六' },
  { value: 'long', label: '长', hint: '如: 2025年5月24日' },
  { value: 'medium', label: '中', hint: '如: 2025-05-24' },
  { value: 'short', label: '短', hint: '如: 25-05-24' }
]

const timeStyleOptions = [
  { value: 'full', label: '完整', hint: '如: 14:30:00 CST' },
  { value: 'long', label: '长', hint: '如: 14:30:00' },
  { value: 'medium', label: '中', hint: '如: 14:30:00' },
  { value: 'short', label: '短', hint: '如: 14:30' }
]

const hourCycleOptions = [
  { value: 24, label: '24小时制' },
  { value: 12, label: '12小时制' }
]

const commonTimezones = [
  'Asia/Shanghai', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Singapore',
  'Asia/Kolkata', 'Asia/Dubai',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo', 'America/Mexico_City',
  'Pacific/Auckland', 'Australia/Sydney',
  'UTC'
]

const navItems = [
  { key: 'profile', label: '个人信息', icon: 'user' },
  { key: 'security', label: '安全设置', icon: 'lock' },
  { key: 'preferences', label: '偏好设置', icon: 'setting' }
]

const avatarText = computed(() => {
  const name = profileForm.displayName || authStore.userDisplayName
  return name ? name.charAt(0).toUpperCase() : '?'
})

const userRoles = computed(() => {
  const roles = authStore.user?.roles || []
  if (roles.length === 0) return '普通用户'
  const names = roles.map(r => typeof r === 'string' ? r : r.name).filter(Boolean)
  return names.join(', ') || '普通用户'
})

const passwordStrength = computed(() => {
  const pwd = passwordForm.newPassword
  if (!pwd) return { class: '', label: '', percent: 0 }

  let score = 0
  if (pwd.length >= 6) score++
  if (pwd.length >= 8) score++
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
  if (/\d/.test(pwd)) score++
  if (/[^a-zA-Z0-9]/.test(pwd)) score++

  if (score <= 2) return { class: 'weak', label: '弱', percent: 33 }
  if (score <= 3) return { class: 'medium', label: '中', percent: 66 }
  return { class: 'strong', label: '强', percent: 100 }
})

const previewFormatted = computed(() => {
  const now = new Date()
  return dateFormatService.format(now, {
    locale: preferenceForm.locale,
    dateStyle: preferenceForm.dateStyle,
    timeStyle: preferenceForm.timeStyle,
    timeZone: preferenceForm.timezone,
    hourCycle: preferenceForm.hourCycle
  })
})

onMounted(() => {
  loadProfile()
  loadPreferences()
  if (authStore.mustChangePassword) {
    activeNav.value = 'security'
  }
})

async function loadProfile() {
  try {
    const data = await authService.getProfile()
    if (data.success && data.data) {
      profileForm.username = data.data.username || authStore.user?.username || ''
      profileForm.displayName = data.data.display_name || authStore.user?.display_name || ''
      profileForm.email = data.data.email || ''
    }
  } catch (e) {
    console.error('Failed to load profile:', e)
    profileForm.username = authStore.user?.username || ''
    profileForm.displayName = authStore.user?.display_name || ''
    profileForm.email = authStore.user?.email || ''
  }
}

function startEditProfile() {
  isEditingProfile.value = true
  profileSubmitError.value = ''
  profileErrors.displayName = ''
  profileErrors.email = ''
}

function cancelEditProfile() {
  isEditingProfile.value = false
  profileErrors.displayName = ''
  profileErrors.email = ''
  profileSubmitError.value = ''
  loadProfile()
}

function validateProfile() {
  let valid = true
  profileErrors.displayName = ''
  profileErrors.email = ''

  if (!profileForm.displayName.trim()) {
    profileErrors.displayName = '显示名称不能为空'
    valid = false
  }

  if (profileForm.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profileForm.email) && !/^[^\s@]+@[^\s@]+$/.test(profileForm.email)) {
    profileErrors.email = '请输入有效的电子邮件地址'
    valid = false
  }

  return valid
}

async function saveProfile() {
  if (!validateProfile()) return

  profileSubmitting.value = true
  profileSubmitError.value = ''

  try {
    const data = await authService.updateProfile({
      display_name: profileForm.displayName,
      email: profileForm.email
    })

    if (data.success) {
      if (authStore.user) {
        authStore.user.display_name = profileForm.displayName
        authStore.user.email = profileForm.email
      }
      message.success('个人信息已更新')
      isEditingProfile.value = false
    } else {
      profileSubmitError.value = data.message || '保存失败'
    }
  } catch (e) {
    profileSubmitError.value = '网络错误，请稍后重试'
  } finally {
    profileSubmitting.value = false
  }
}

function validatePassword() {
  let valid = true
  passwordErrors.oldPassword = ''
  passwordErrors.newPassword = ''
  passwordErrors.confirmPassword = ''

  if (!authStore.mustChangePassword && !passwordForm.oldPassword) {
    passwordErrors.oldPassword = '请输入旧密码'
    valid = false
  }

  if (!passwordForm.newPassword) {
    passwordErrors.newPassword = '请输入新密码'
    valid = false
  } else if (passwordForm.newPassword.length < 6) {
    passwordErrors.newPassword = '新密码长度不能少于6位'
    valid = false
  }

  if (!passwordForm.confirmPassword) {
    passwordErrors.confirmPassword = '请再次输入新密码'
    valid = false
  } else if (passwordForm.confirmPassword !== passwordForm.newPassword) {
    passwordErrors.confirmPassword = '两次输入的密码不一致'
    valid = false
  }

  return valid
}

async function savePassword() {
  if (!validatePassword()) return

  passwordSubmitting.value = true
  passwordSubmitError.value = ''

  try {
    const data = await authService.changePassword(passwordForm.oldPassword, passwordForm.newPassword)

    if (data.success) {
      message.success(authStore.mustChangePassword ? '密码设置成功' : '密码修改成功')
      passwordForm.oldPassword = ''
      passwordForm.newPassword = ''
      passwordForm.confirmPassword = ''

      if (authStore.mustChangePassword) {
        authStore.mustChangePassword = false
      }
    } else {
      passwordSubmitError.value = data.message || '密码修改失败'
    }
  } catch (e) {
    passwordSubmitError.value = '网络错误，请稍后重试'
  } finally {
    passwordSubmitting.value = false
  }
}

async function loadPreferences() {
  try {
    const data = await authService.getProfile()
    if (data.success && data.data) {
      const d = data.data
      preferenceForm.locale = d.locale || 'zh-CN'
      preferenceForm.timezone = d.timezone || 'Asia/Shanghai'
      preferenceForm.dateStyle = d.date_style || 'medium'
      preferenceForm.timeStyle = d.time_style || 'short'
      preferenceForm.hourCycle = d.hour_cycle || 24
      prefStore.loadFromUser(d)
    }
  } catch (e) {
    console.error('Failed to load preferences:', e)
  }
}

async function savePreferences() {
  prefSubmitting.value = true
  try {
    const success = await prefStore.save({
      locale: preferenceForm.locale,
      timezone: preferenceForm.timezone,
      dateStyle: preferenceForm.dateStyle,
      timeStyle: preferenceForm.timeStyle,
      hourCycle: preferenceForm.hourCycle
    })
    if (success) {
      message.saved('偏好设置')
    } else {
      message.error('保存偏好设置失败，请稍后重试')
    }
  } catch (e) {
    message.error('保存偏好设置失败，请检查网络后重试', e)
  } finally {
    prefSubmitting.value = false
  }
}
</script>

<style scoped lang="scss">
.account-settings-page {
  max-width: 800px;
  margin: 0 auto;
  padding: var(--spacing-lg) var(--spacing-md);
}

.page-header {
  margin-bottom: var(--spacing-lg);
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs);
}

.page-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

.settings-layout {
  display: flex;
  gap: var(--spacing-xl);
  align-items: flex-start;
}

.settings-nav {
  width: 120px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;

  .app-icon {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }

  &:hover {
    background: var(--color-bg-secondary);
    color: var(--color-text-primary);
  }

  &.active {
    background: rgba(234, 88, 12, 0.08);
    color: var(--yonyou-orange-600);
    font-weight: 500;
  }
}

.settings-content {
  flex: 1;
  min-width: 0;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.section {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}

.profile-view {
  .profile-avatar-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }

  .profile-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: var(--yonyou-orange-500);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .profile-username {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .profile-role {
    font-size: 12px;
    color: var(--color-text-tertiary);
    margin-top: 2px;
  }

  .profile-fields {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .profile-field {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    padding: 10px 0;
    border-bottom: 1px solid var(--color-border-secondary);

    &:last-child {
      border-bottom: none;
    }
  }

  .field-label {
    font-size: 13px;
    color: var(--color-text-tertiary);
    min-width: 70px;
    flex-shrink: 0;
  }

  .field-value {
    font-size: 13px;
    color: var(--color-text-primary);
  }
}

.profile-edit {
  .form-row {
    margin-bottom: var(--spacing-md);
  }
}

.form-row {
  margin-bottom: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.required {
  color: var(--color-error);
}

.form-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.password-form {
  .form-intro {
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-bottom: var(--spacing-md);
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--color-bg-secondary);
    border-radius: var(--radius-md);
  }
}

.password-force-notice {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 13px;
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
}

.password-strength {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-xs);
}

.strength-bar {
  flex: 1;
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s, background 0.3s;

  &.weak { background: var(--color-error); }
  &.medium { background: var(--color-warning); }
  &.strong { background: var(--color-success); }
}

.strength-text {
  font-size: 12px;
  font-weight: 500;

  &.weak { color: var(--color-error); }
  &.medium { color: var(--color-warning); }
  &.strong { color: var(--color-success); }
}

.submit-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 13px;
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
}

.security-tips {
  .tips-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);

    li {
      font-size: 13px;
      color: var(--color-text-secondary);
      padding-left: var(--spacing-md);
      position: relative;

      &::before {
        content: '·';
        position: absolute;
        left: 0;
        color: var(--yonyou-orange-500);
        font-weight: bold;
      }
    }
  }
}

.select-input {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: 13px;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  outline: none;
  cursor: pointer;

  &:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 2px rgba(var(--color-primary-rgb, 24, 144, 255), 0.2);
  }
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);

  &.inline {
    flex-direction: row;
    gap: var(--spacing-lg);
  }
}

.radio-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;

  &:hover {
    border-color: var(--color-primary);
  }

  &.active {
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
  }
}

.radio-input {
  width: 14px;
  height: 14px;
  accent-color: var(--color-primary);
  cursor: pointer;
  flex-shrink: 0;
}

.radio-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  min-width: 36px;
}

.radio-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.preview-section {
  margin-top: var(--spacing-md);
}

.preview-box {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.preview-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
}

@media (max-width: 768px) {
  .settings-layout {
    flex-direction: column;
  }

  .settings-nav {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
    position: static;
  }

  .nav-item {
    white-space: nowrap;
  }
}
</style>
