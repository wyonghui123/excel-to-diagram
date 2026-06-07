<template>
  <div class="system-settings">
    <div class="ss-container">
      <aside class="ss-sidebar">
        <nav class="ss-nav" role="navigation" aria-label="系统设置导航">
          <button
            v-for="item in configMenus"
            :key="item.key"
            :class="['ss-nav-item', { active: currentMenu === item.key }]"
            @click="currentMenu = item.key"
            role="menuitem"
            :aria-current="currentMenu === item.key ? 'page' : undefined"
          >
            <AppIcon :name="item.icon" :size="16" class="nav-icon" />
            <span class="nav-label">{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <main class="ss-content">
        <!-- AI 配置 -->
        <section v-if="currentMenu === 'ai'" class="ss-section" aria-label="AI服务配置">
          <h2 class="section-title">AI 服务配置</h2>
          <p class="section-desc">配置 AI 服务提供商和 API 密钥</p>
          <div class="ss-form">
            <div class="form-group">
              <label class="form-label">默认 AI 服务提供商</label>
              <div class="radio-group" role="radiogroup" aria-label="AI服务提供商选择">
                <label class="radio-option">
                  <input type="radio" v-model="config.aiProvider" value="zhipu" />
                  <span class="radio-text">智谱 AI</span>
                </label>
                <label class="radio-option">
                  <input type="radio" v-model="config.aiProvider" value="deepseek" />
                  <span class="radio-text">DeepSeek</span>
                </label>
              </div>
            </div>
            <div class="form-group">
              <label for="zhipuApiKey" class="form-label">智谱 API Key</label>
              <input id="zhipuApiKey" type="password" v-model="config.zhipuApiKey" class="form-input" placeholder="请输入智谱 API Key" />
              <span class="form-hint">用于关系说明的智能检查</span>
            </div>
            <div class="form-group">
              <label for="deepseekApiKey" class="form-label">DeepSeek API Key</label>
              <input id="deepseekApiKey" type="password" v-model="config.deepseekApiKey" class="form-input" placeholder="请输入 DeepSeek API Key" />
              <span class="form-hint">备用 AI 服务</span>
            </div>
            <div class="form-group">
              <label for="aiModel" class="form-label">AI 校验模型</label>
              <select id="aiModel" v-model="config.aiModel" class="form-select">
                <option value="glm-4-flash">GLM-4-Flash (智谱)</option>
                <option value="glm-4">GLM-4 (智谱)</option>
                <option value="deepseek-chat">DeepSeek Chat</option>
                <option value="deepseek-coder">DeepSeek Coder</option>
              </select>
            </div>
          </div>
        </section>

        <!-- 飞书集成 -->
        <section v-if="currentMenu === 'feishu'" class="ss-section" aria-label="飞书集成配置">
          <h2 class="section-title">飞书集成配置</h2>
          <p class="section-desc">配置飞书开放平台</p>
          <div class="ss-form">
            <div class="form-group">
              <label for="feishuAppId" class="form-label">飞书 App ID</label>
              <input id="feishuAppId" type="text" v-model="config.feishuAppId" class="form-input" placeholder="请输入飞书 App ID" />
            </div>
            <div class="form-group">
              <label for="feishuAppSecret" class="form-label">飞书 App Secret</label>
              <input id="feishuAppSecret" type="password" v-model="config.feishuAppSecret" class="form-input" placeholder="请输入飞书 App Secret" />
            </div>
            <div class="form-group">
              <label for="feishuAccessToken" class="form-label">飞书 Access Token</label>
              <input id="feishuAccessToken" type="password" v-model="config.feishuAccessToken" class="form-input" placeholder="请输入飞书 Access Token" />
            </div>
            <div class="form-group">
              <label for="feishuDefaultChatId" class="form-label">默认发送目标</label>
              <input id="feishuDefaultChatId" type="text" v-model="config.feishuDefaultChatId" class="form-input" placeholder="请输入群ID或用户ID" />
              <span class="form-hint">图表默认发送到该聊天</span>
            </div>
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.feishuEnabled" />
                <span class="checkbox-text">启用飞书集成</span>
              </label>
            </div>
            <div class="form-group">
              <AppButton
                variant="secondary"
                size="sm"
                @click="testFeishuConnection"
                :disabled="testingFeishu"
                :loading="testingFeishu"
                aria-label="测试飞书连接"
              >{{ testingFeishu ? '测试中...' : '测试连接' }}</AppButton>
              <span v-if="feishuTestResult" :class="['test-result', feishuTestResult.success ? 'success' : 'error']">
                {{ feishuTestResult.message }}
              </span>
            </div>
          </div>
        </section>

        <!-- 图表配置 -->
        <section v-if="currentMenu === 'diagram'" class="ss-section" aria-label="图表默认配置">
          <h2 class="section-title">图表默认配置</h2>
          <p class="section-desc">设置图表生成的默认参数</p>
          <div class="ss-form">
            <div class="form-group">
              <label for="colorScheme" class="form-label">默认配色方案</label>
              <select id="colorScheme" v-model="config.defaultColorScheme" class="form-select">
                <option value="vibrant">鲜艳</option>
                <option value="pastel">柔和</option>
                <option value="business">商务</option>
                <option value="tech">科技</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">默认标题颜色</label>
              <div class="color-options" role="radiogroup" aria-label="标题颜色选择">
                <label v-for="color in textColors" :key="color.value" class="color-option" :class="{ active: config.defaultTextColor === color.value }">
                  <input type="radio" :value="color.value" v-model="config.defaultTextColor" />
                  <span class="color-preview" :style="{ backgroundColor: color.preview }"></span>
                  <span class="color-label">{{ color.label }}</span>
                </label>
              </div>
            </div>
            <div class="form-group">
              <label for="colorGroupBy" class="form-label">默认颜色分组方式</label>
              <select id="colorGroupBy" v-model="config.defaultColorGroupBy" class="form-select">
                <option value="domain">按领域</option>
                <option value="subDomain">按子领域</option>
                <option value="serviceModule">按服务模块</option>
              </select>
            </div>
            <div class="form-group">
              <label for="centerDomainColor" class="form-label">中心域高亮色</label>
              <input id="centerDomainColor" type="color" v-model="config.defaultCenterDomainColor" class="form-color-picker" />
            </div>
          </div>
        </section>

        <!-- 数据验证 -->
        <section v-if="currentMenu === 'validation'" class="ss-section" aria-label="数据验证配置">
          <h2 class="section-title">数据验证配置</h2>
          <p class="section-desc">配置数据导入后的验证规则</p>
          <div class="ss-form">
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.validation.enableForeignKeyCheck" />
                <span class="checkbox-text">启用外键关联检查</span>
              </label>
            </div>
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.validation.enableRequiredFieldCheck" />
                <span class="checkbox-text">启用必填字段检查</span>
              </label>
            </div>
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.validation.enableDuplicateCheck" />
                <span class="checkbox-text">启用重复数据检查</span>
              </label>
            </div>
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.validation.enableAIRelationCheck" />
                <span class="checkbox-text">启用 AI 关系说明检查</span>
              </label>
            </div>
          </div>
        </section>

        <!-- 导出配置 -->
        <section v-if="currentMenu === 'export'" class="ss-section" aria-label="导出配置">
          <h2 class="section-title">导出配置</h2>
          <p class="section-desc">配置图表导出的默认设置</p>
          <div class="ss-form">
            <div class="form-group">
              <label for="exportFormat" class="form-label">默认导出格式</label>
              <select id="exportFormat" v-model="config.export.defaultFormat" class="form-select">
                <option value="png">PNG 图片</option>
                <option value="svg">SVG 矢量图</option>
                <option value="pdf">PDF 文档</option>
              </select>
            </div>
            <div class="form-group">
              <label for="exportResolution" class="form-label">默认导出分辨率</label>
              <select id="exportResolution" v-model="config.export.defaultResolution" class="form-select">
                <option value="1">1x (标准)</option>
                <option value="2">2x (高清)</option>
                <option value="3">3x (超清)</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-checkbox">
                <input type="checkbox" v-model="config.export.includeBackground" />
                <span class="checkbox-text">导出时包含背景</span>
              </label>
            </div>
          </div>
        </section>

        <!-- 关于 -->
        <section v-if="currentMenu === 'about'" class="ss-section" aria-label="关于">
          <div class="about-content">
            <h3>ArchWorkspace</h3>
            <p class="version">版本 1.0.0</p>
            <p>ArchWorkspace 是一款专业的架构设计工具。</p>
          </div>
        </section>

        <div class="ss-actions">
          <AppButton
            variant="secondary"
            size="sm"
            @click="resetConfig"
            aria-label="恢复默认配置"
          >恢复默认</AppButton>
          <AppButton
            variant="primary"
            size="sm"
            @click="saveConfig"
            :disabled="saving"
            :loading="saving"
            aria-label="保存配置"
          >{{ saving ? '保存中...' : '保存配置' }}</AppButton>
        </div>
      </main>
    </div>

    <Teleport to="body">
      <div v-if="showSuccess" class="success-toast" role="alert" aria-live="polite">
        <AppIcon name="check-circle" :size="16" class="toast-icon" />
        <span>配置已保存</span>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'

const currentMenu = ref('ai')
const saving = ref(false)
const showSuccess = ref(false)
const testingFeishu = ref(false)
const feishuTestResult = ref(null)

const configMenus = [
  { key: 'ai', label: 'AI 配置', icon: 'robot' },
  { key: 'feishu', label: '飞书集成', icon: 'mobile' },
  { key: 'diagram', label: '图表配置', icon: 'chart-bar' },
  { key: 'validation', label: '数据验证', icon: 'search' },
  { key: 'export', label: '导出配置', icon: 'export' },
  { key: 'about', label: '关于', icon: 'info' }
]

const textColors = [
  { value: 'black', label: '黑色', preview: '#000000' },
  { value: 'gray', label: '灰色', preview: '#666666' },
  { value: 'white', label: '白色', preview: '#ffffff' }
]

const config = reactive({
  aiProvider: 'zhipu',
  zhipuApiKey: '',
  deepseekApiKey: '',
  aiModel: 'glm-4-flash',
  feishuAppId: '',
  feishuAppSecret: '',
  feishuAccessToken: '',
  feishuDefaultChatId: '',
  feishuEnabled: false,
  defaultColorScheme: 'vibrant',
  defaultTextColor: 'black',
  defaultColorGroupBy: 'domain',
  defaultCenterDomainColor: '#ff6b6b',
  validation: {
    enableForeignKeyCheck: true,
    enableRequiredFieldCheck: true,
    enableDuplicateCheck: true,
    enableAIRelationCheck: false
  },
  export: {
    defaultFormat: 'png',
    defaultResolution: '2',
    includeBackground: true
  }
})

const defaultConfig = { ...config, validation: { ...config.validation }, export: { ...config.export } }

onMounted(() => {
  loadConfig()
})

function loadConfig() {
  const savedConfig = localStorage.getItem('archWorkspaceConfig')
  if (savedConfig) {
    try {
      const parsed = JSON.parse(savedConfig)
      Object.assign(config, parsed)
    } catch (e) {
      console.error('加载配置失败:', e)
    }
  }
}

function saveConfig() {
  saving.value = true
  setTimeout(() => {
    localStorage.setItem('archWorkspaceConfig', JSON.stringify(config))
    saving.value = false
    showSuccess.value = true
    setTimeout(() => {
      showSuccess.value = false
    }, 2000)
  }, 500)
}

async function resetConfig() {
  const confirmed = await message.confirm({ content: '确定要恢复默认配置吗？' })
  if (!confirmed) return
  
  Object.assign(config, {
      aiProvider: 'zhipu',
      zhipuApiKey: '',
      deepseekApiKey: '',
      aiModel: 'glm-4-flash',
      feishuAppId: '',
      feishuAppSecret: '',
      feishuAccessToken: '',
      feishuDefaultChatId: '',
      feishuEnabled: false,
      defaultColorScheme: 'vibrant',
      defaultTextColor: 'black',
      defaultColorGroupBy: 'domain',
      defaultCenterDomainColor: '#ff6b6b',
      validation: {
        enableForeignKeyCheck: true,
        enableRequiredFieldCheck: true,
        enableDuplicateCheck: true,
        enableAIRelationCheck: false
      },
      export: {
        defaultFormat: 'png',
        defaultResolution: '2',
        includeBackground: true
      }
    })
    saveConfig()
}

async function testFeishuConnection() {
  testingFeishu.value = true
  feishuTestResult.value = null

  try {
    const appId = config.feishuAppId || import.meta.env.VITE_FEISHU_APP_ID || ''
    const appSecret = config.feishuAppSecret || import.meta.env.VITE_FEISHU_APP_SECRET || ''

    if (!appId || !appSecret) {
      feishuTestResult.value = { success: false, message: '请先配置 App ID 和 App Secret' }
      return
    }

    // eslint-disable-next-line no-restricted-globals -- 外部 API，不走 httpClient
    const response = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret })
    })

    const data = await response.json()

    if (data.code === 0 && data.tenant_access_token) {
      feishuTestResult.value = { success: true, message: '连接成功！Token 已获取' }
      config.feishuAccessToken = data.tenant_access_token
    } else {
      feishuTestResult.value = { success: false, message: `连接失败: ${data.msg || '未知错误'}` }
    }
  } catch (error) {
    feishuTestResult.value = { success: false, message: `请求失败: ${error.message}` }
  } finally {
    testingFeishu.value = false
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.system-settings {
  height: 100%;
}

.ss-container {
  display: flex;
  gap: 0;
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  min-height: calc(100vh - 200px);
  overflow: hidden;
}

/* 侧边栏导航 - yonDesign 规范 */
.ss-sidebar {
  width: 200px;
  border-right: 1px solid var(--color-border);
  padding: var(--spacing-sm) 0;
  flex-shrink: 0;
  background: var(--color-bg-primary);
}

.ss-nav {
  display: flex;
  flex-direction: column;
}

.ss-nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  border-left: 2px solid transparent;
  color: var(--color-text-secondary);
  background: transparent;
  border-right: none;
  border-top: none;
  border-bottom: none;
  font-size: var(--font-size-sm);
  width: 100%;
  text-align: left;

  &:hover {
    color: var(--color-text-primary);
    background: transparent;
  }

  &.active {
    border-left-color: var(--color-primary);
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
    background: transparent;
  }
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.nav-label {
  font-size: var(--font-size-sm);
}

/* 内容区域 */
.ss-content {
  flex: 1;
  padding: var(--spacing-xl) var(--spacing-xl);
  overflow-y: auto;
}

.ss-section {
  max-width: 800px;
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0 0 var(--spacing-xl) 0;
}

/* 表单样式 */
.ss-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.form-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.form-input,
.form-select {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color var(--transition-normal);
  background: var(--color-bg-primary);

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }
}

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.form-color-picker {
  width: 60px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  padding: var(--spacing-xxs);
}

.radio-group {
  display: flex;
  gap: var(--spacing-lg);
}

.radio-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);

  input[type='radio'] {
    width: 16px;
    height: 16px;
    accent-color: var(--color-primary);
  }
}

.form-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  width: fit-content;

  input[type='checkbox'] {
    width: 16px;
    height: 16px;
    accent-color: var(--color-primary);
  }
}

.color-options {
  display: flex;
  gap: var(--spacing-lg);
}

.color-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-normal);
  min-width: 80px;

  &:hover {
    border-color: var(--color-border);
  }

  &.active {
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
  }

  input {
    display: none;
  }
}

.color-preview {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid var(--color-border-light);
}

.color-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

/* 操作按钮区 */
.ss-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
  margin-top: var(--spacing-xl);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-border-light);
}

/* 成功提示Toast */
.success-toast {
  position: fixed;
  bottom: var(--spacing-xl);
  right: var(--spacing-xl);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-success);
  color: #fff;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  animation: slideIn 0.3s ease;
  z-index: var(--z-index-toast);
}

.toast-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: white;
  color: var(--color-success);
  font-size: var(--font-size-xs);
  font-weight: bold;
}

.test-result {
  margin-left: var(--spacing-md);
  font-size: var(--font-size-sm);

  &.success {
    color: var(--color-success);
  }

  &.error {
    color: var(--color-error);
  }
}

/* 关于页面 */
.about-content {
  text-align: center;
  padding: var(--spacing-2xl) 0;

  h3 {
    font-size: var(--font-size-xl);
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
    margin: 0 0 var(--spacing-sm) 0;
  }

  .version {
    font-size: var(--font-size-sm);
    color: var(--color-text-tertiary);
    margin: 0 0 var(--spacing-lg) 0;
  }

  p {
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
    margin: 0;
  }
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>