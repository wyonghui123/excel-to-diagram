<template>
  <div class="config-app">
    <!-- 顶部标题栏 -->
    <header class="app-header">
      <div class="header-left">
        <button class="back-btn" @click="$emit('back-to-landing')">
          <span>←</span> 返回
        </button>
        <h1>系统配置</h1>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <div class="config-container">
        <!-- 左侧导航 -->
        <aside class="config-sidebar">
          <nav class="config-nav">
            <div
              v-for="item in configMenus"
              :key="item.key"
              :class="['nav-item', { active: currentMenu === item.key }]"
              @click="currentMenu = item.key"
            >
              <span class="nav-icon">{{ item.icon }}</span>
              <span class="nav-label">{{ item.label }}</span>
            </div>
          </nav>
        </aside>

        <!-- 右侧配置内容 -->
        <div class="config-content">
          <!-- AI 配置 -->
          <div v-if="currentMenu === 'ai'" class="config-section">
            <h2 class="section-title">AI 服务配置</h2>
            <p class="section-desc">配置 AI 服务提供商和 API 密钥</p>

            <div class="config-form">
              <div class="form-group">
                <label class="form-label">默认 AI 服务提供商</label>
                <div class="radio-group">
                  <label class="radio-option">
                    <input
                      type="radio"
                      v-model="config.aiProvider"
                      value="zhipu"
                    />
                    <span class="radio-text">智谱 AI</span>
                  </label>
                  <label class="radio-option">
                    <input
                      type="radio"
                      v-model="config.aiProvider"
                      value="deepseek"
                    />
                    <span class="radio-text">DeepSeek</span>
                  </label>
                </div>
              </div>

              <div class="form-group">
                <label class="form-label">智谱 API Key</label>
                <input
                  type="password"
                  v-model="config.zhipuApiKey"
                  class="form-input"
                  placeholder="请输入智谱 API Key"
                />
                <span class="form-hint">用于关系说明的智能检查</span>
              </div>

              <div class="form-group">
                <label class="form-label">DeepSeek API Key</label>
                <input
                  type="password"
                  v-model="config.deepseekApiKey"
                  class="form-input"
                  placeholder="请输入 DeepSeek API Key"
                />
                <span class="form-hint">备用 AI 服务</span>
              </div>

              <div class="form-group">
                <label class="form-label">AI 校验模型</label>
                <select v-model="config.aiModel" class="form-select">
                  <option value="glm-4-flash">GLM-4-Flash (智谱)</option>
                  <option value="glm-4">GLM-4 (智谱)</option>
                  <option value="deepseek-chat">DeepSeek Chat</option>
                  <option value="deepseek-coder">DeepSeek Coder</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 飞书配置 -->
          <div v-if="currentMenu === 'feishu'" class="config-section">
            <h2 class="section-title">飞书集成配置</h2>
            <p class="section-desc">配置飞书开放平台，实现图表发送到飞书、从飞书获取数据等功能</p>

            <div class="config-form">
              <div class="form-group">
                <label class="form-label">飞书 App ID</label>
                <input
                  type="text"
                  v-model="config.feishuAppId"
                  class="form-input"
                  placeholder="请输入飞书 App ID"
                />
                <span class="form-hint">飞书开放平台应用标识</span>
              </div>

              <div class="form-group">
                <label class="form-label">飞书 App Secret</label>
                <input
                  type="password"
                  v-model="config.feishuAppSecret"
                  class="form-input"
                  placeholder="请输入飞书 App Secret"
                />
                <span class="form-hint">用于获取访问令牌</span>
              </div>

              <div class="form-group">
                <label class="form-label">飞书 Access Token</label>
                <input
                  type="password"
                  v-model="config.feishuAccessToken"
                  class="form-input"
                  placeholder="请输入飞书 Access Token"
                />
                <span class="form-hint">用于调用飞书API（可选，会自动刷新）</span>
              </div>

              <div class="form-group">
                <label class="form-label">默认发送目标</label>
                <input
                  type="text"
                  v-model="config.feishuDefaultChatId"
                  class="form-input"
                  placeholder="请输入群ID或用户ID"
                />
                <span class="form-hint">图表默认发送到该聊天（群ID以oc_开头，用户ID以ou_开头）</span>
              </div>

              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.feishuEnabled"
                  />
                  <span class="checkbox-text">启用飞书集成</span>
                </label>
              </div>

              <div class="form-group">
                <button 
                  class="btn-secondary" 
                  @click="testFeishuConnection"
                  :disabled="testingFeishu"
                >
                  <span v-if="testingFeishu">测试中...</span>
                  <span v-else>测试连接</span>
                </button>
                <span v-if="feishuTestResult" :class="['test-result', feishuTestResult.success ? 'success' : 'error']">
                  {{ feishuTestResult.message }}
                </span>
              </div>
            </div>
          </div>

          <!-- 图表配置 -->
          <div v-if="currentMenu === 'diagram'" class="config-section">
            <h2 class="section-title">图表默认配置</h2>
            <p class="section-desc">设置图表生成的默认参数</p>

            <div class="config-form">
              <div class="form-group">
                <label class="form-label">默认配色方案</label>
                <select v-model="config.defaultColorScheme" class="form-select">
                  <option value="vibrant">鲜艳</option>
                  <option value="pastel">柔和</option>
                  <option value="business">商务</option>
                  <option value="tech">科技</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-label">默认标题颜色</label>
                <div class="color-options">
                  <label
                    v-for="color in textColors"
                    :key="color.value"
                    class="color-option"
                    :class="{ active: config.defaultTextColor === color.value }"
                    @click="config.defaultTextColor = color.value"
                  >
                    <input
                      type="radio"
                      :value="color.value"
                      v-model="config.defaultTextColor"
                    />
                    <span
                      class="color-preview"
                      :style="{ backgroundColor: color.preview }"
                    ></span>
                    <span class="color-label">{{ color.label }}</span>
                  </label>
                </div>
              </div>

              <div class="form-group">
                <label class="form-label">默认颜色分组方式</label>
                <select v-model="config.defaultColorGroupBy" class="form-select">
                  <option value="domain">按领域</option>
                  <option value="subDomain">按子领域</option>
                  <option value="serviceModule">按服务模块</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-label">中心域高亮色</label>
                <input
                  type="color"
                  v-model="config.defaultCenterDomainColor"
                  class="form-color-picker"
                />
              </div>
            </div>
          </div>

          <!-- 数据验证配置 -->
          <div v-if="currentMenu === 'validation'" class="config-section">
            <h2 class="section-title">数据验证配置</h2>
            <p class="section-desc">配置数据导入后的验证规则</p>

            <div class="config-form">
              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.validation.enableForeignKeyCheck"
                  />
                  <span class="checkbox-text">启用外键关联检查</span>
                </label>
                <span class="form-hint">检查业务对象编码、服务模块编码等外键引用</span>
              </div>

              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.validation.enableRequiredFieldCheck"
                  />
                  <span class="checkbox-text">启用必填字段检查</span>
                </label>
              </div>

              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.validation.enableDuplicateCheck"
                  />
                  <span class="checkbox-text">启用重复数据检查</span>
                </label>
              </div>

              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.validation.enableAIRelationCheck"
                  />
                  <span class="checkbox-text">启用 AI 关系说明检查</span>
                </label>
                <span class="form-hint">使用 AI 检查关系说明是否清晰</span>
              </div>
            </div>
          </div>

          <!-- 导出配置 -->
          <div v-if="currentMenu === 'export'" class="config-section">
            <h2 class="section-title">导出配置</h2>
            <p class="section-desc">配置图表导出的默认设置</p>

            <div class="config-form">
              <div class="form-group">
                <label class="form-label">默认导出格式</label>
                <select v-model="config.export.defaultFormat" class="form-select">
                  <option value="png">PNG 图片</option>
                  <option value="svg">SVG 矢量图</option>
                  <option value="pdf">PDF 文档</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-label">默认导出分辨率</label>
                <select v-model="config.export.defaultResolution" class="form-select">
                  <option value="1">1x (标准)</option>
                  <option value="2">2x (高清)</option>
                  <option value="3">3x (超清)</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-checkbox">
                  <input
                    type="checkbox"
                    v-model="config.export.includeBackground"
                  />
                  <span class="checkbox-text">导出时包含背景</span>
                </label>
              </div>
            </div>
          </div>

          <!-- 关于 -->
          <div v-if="currentMenu === 'about'" class="config-section">
            <h2 class="section-title">关于 ArchWorkspace</h2>
            <div class="about-content">
              <div class="about-logo">
                <span class="logo-icon">🏛️</span>
                <h3>ArchWorkspace</h3>
                <p class="version">版本 1.0.0</p>
              </div>
              <div class="about-info">
                <p>ArchWorkspace 是一款专业的架构设计工具，提供业务对象关系图生成、数据验证等功能。</p>
                <div class="feature-list">
                  <div class="feature-item">
                    <span class="feature-icon">📊</span>
                    <span>AA图 - 业务对象关系图生成工具</span>
                  </div>
                  <div class="feature-item">
                    <span class="feature-icon">🔍</span>
                    <span>智能数据验证</span>
                  </div>
                  <div class="feature-item">
                    <span class="feature-icon">🤖</span>
                    <span>AI 辅助关系检查</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 保存按钮 -->
          <div class="config-actions">
            <button class="btn-secondary" @click="resetConfig">恢复默认</button>
            <button class="btn-primary" @click="saveConfig" :disabled="saving">
              <span v-if="saving">保存中...</span>
              <span v-else>保存配置</span>
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 保存成功提示 -->
    <div v-if="showSuccess" class="success-toast">
      <span class="success-icon">✓</span>
      <span>配置已保存</span>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ConfigApp',
  emits: ['back-to-landing'],
  data() {
    return {
      currentMenu: 'ai',
      saving: false,
      showSuccess: false,
      configMenus: [
        { key: 'ai', label: 'AI 配置', icon: '🤖' },
        { key: 'feishu', label: '飞书集成', icon: '📱' },
        { key: 'diagram', label: '图表配置', icon: '📊' },
        { key: 'validation', label: '数据验证', icon: '🔍' },
        { key: 'export', label: '导出配置', icon: '📤' },
        { key: 'about', label: '关于', icon: 'ℹ️' }
      ],
      testingFeishu: false,
      feishuTestResult: null,
      textColors: [
        { value: 'black', label: '黑色', preview: '#000000' },
        { value: 'gray', label: '灰色', preview: '#666666' },
        { value: 'white', label: '白色', preview: '#ffffff' }
      ],
      config: {
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
      }
    }
  },
  mounted() {
    this.loadConfig()
  },
  methods: {
    loadConfig() {
      // 从 localStorage 加载配置
      const savedConfig = localStorage.getItem('archWorkspaceConfig')
      if (savedConfig) {
        try {
          const parsed = JSON.parse(savedConfig)
          this.config = { ...this.config, ...parsed }
        } catch (e) {
          console.error('加载配置失败:', e)
        }
      }
    },
    saveConfig() {
      this.saving = true
      // 模拟保存延迟
      setTimeout(() => {
        localStorage.setItem('archWorkspaceConfig', JSON.stringify(this.config))
        this.saving = false
        this.showSuccess = true
        setTimeout(() => {
          this.showSuccess = false
        }, 2000)
      }, 500)
    },
    resetConfig() {
      if (confirm('确定要恢复默认配置吗？')) {
        this.config = {
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
        }
        this.saveConfig()
      }
    },
    async testFeishuConnection() {
      this.testingFeishu = true
      this.feishuTestResult = null
      
      try {
        // 从环境变量获取默认值
        const defaultAppId = import.meta.env.VITE_FEISHU_APP_ID || ''
        const defaultAppSecret = import.meta.env.VITE_FEISHU_APP_SECRET || ''
        
        const appId = this.config.feishuAppId || defaultAppId
        const appSecret = this.config.feishuAppSecret || defaultAppSecret
        
        if (!appId || !appSecret) {
          this.feishuTestResult = { success: false, message: '请先配置 App ID 和 App Secret' }
          return
        }
        
        // 调用飞书API测试连接
        const response = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            app_id: appId,
            app_secret: appSecret
          })
        })
        
        const data = await response.json()
        
        if (data.code === 0 && data.tenant_access_token) {
          this.feishuTestResult = { success: true, message: '连接成功！Token 已获取' }
          // 自动保存获取到的 token
          this.config.feishuAccessToken = data.tenant_access_token
        } else {
          this.feishuTestResult = { success: false, message: `连接失败: ${data.msg || '未知错误'}` }
        }
      } catch (error) {
        this.feishuTestResult = { success: false, message: `请求失败: ${error.message}` }
      } finally {
        this.testingFeishu = false
      }
    }
  }
}
</script>

<style scoped>
.config-app {
  min-height: 100vh;
  background: #f5f7fa;
}

/* 顶部标题栏 */
.app-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.app-header h1 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

/* 主内容区 */
.main-content {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.config-container {
  display: flex;
  gap: 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  min-height: calc(100vh - 140px);
}

/* 左侧导航 */
.config-sidebar {
  width: 200px;
  border-right: 1px solid #f0f0f0;
  padding: 16px 0;
}

.config-nav {
  display: flex;
  flex-direction: column;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.2s;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background: #f5f7fa;
}

.nav-item.active {
  background: #e6f7ff;
  border-left-color: #1890ff;
  color: #1890ff;
}

.nav-icon {
  font-size: 18px;
}

.nav-label {
  font-size: 14px;
}

/* 右侧配置内容 */
.config-content {
  flex: 1;
  padding: 24px;
}

.config-section {
  max-width: 600px;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.section-desc {
  font-size: 14px;
  color: #999;
  margin: 0 0 24px 0;
}

/* 表单样式 */
.config-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.form-input,
.form-select {
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.1);
}

.form-hint {
  font-size: 12px;
  color: #999;
}

.form-color-picker {
  width: 60px;
  height: 36px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}

/* 单选组 */
.radio-group {
  display: flex;
  gap: 16px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.radio-option input[type='radio'] {
  width: 16px;
  height: 16px;
  accent-color: #1890ff;
}

/* 复选框 */
.form-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.form-checkbox input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: #1890ff;
}

/* 颜色选项 */
.color-options {
  display: flex;
  gap: 16px;
}

.color-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 80px;
}

.color-option:hover {
  border-color: #d9d9d9;
}

.color-option.active {
  border-color: #1890ff;
  background: #e6f7ff;
}

.color-option input {
  display: none;
}

.color-preview {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid #e8e8e8;
}

.color-label {
  font-size: 12px;
  color: #666;
}

/* 操作按钮 */
.config-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #f0f0f0;
}

.btn-primary {
  padding: 10px 24px;
  background: #1890ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #40a9ff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 24px;
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: #1890ff;
  color: #1890ff;
}

/* 关于页面 */
.about-content {
  text-align: center;
  padding: 40px 0;
}

.about-logo {
  margin-bottom: 32px;
}

.about-logo .logo-icon {
  font-size: 64px;
  display: block;
  margin-bottom: 16px;
}

.about-logo h3 {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.about-logo .version {
  font-size: 14px;
  color: #999;
  margin: 0;
}

.about-info {
  max-width: 500px;
  margin: 0 auto;
}

.about-info p {
  font-size: 14px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 24px;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
  font-size: 14px;
  color: #333;
}

.feature-icon {
  font-size: 18px;
}

/* 测试结果提示 */
.test-result {
  margin-left: 12px;
  font-size: 14px;
}

.test-result.success {
  color: #52c41a;
}

.test-result.error {
  color: #f5222d;
}

/* 成功提示 */
.success-toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: #52c41a;
  color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  animation: slideIn 0.3s ease;
}

.success-icon {
  font-size: 16px;
  font-weight: bold;
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

/* ==================== 响应式设计 ==================== */

/* 平板设备 (768px - 1024px) */
@media screen and (max-width: 1024px) {
  .main-content {
    padding: 20px;
  }

  .config-container {
    flex-direction: column;
  }

  .config-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid #f0f0f0;
    padding: 12px 0;
  }

  .config-nav {
    flex-direction: row;
    overflow-x: auto;
    padding: 0 16px;
    gap: 8px;
  }

  .nav-item {
    flex-shrink: 0;
    padding: 10px 16px;
    border-left: none;
    border-bottom: 3px solid transparent;
    border-radius: 8px;
  }

  .nav-item.active {
    border-left-color: transparent;
    border-bottom-color: #1890ff;
  }

  .config-content {
    padding: 20px;
  }
}

/* 手机设备 (< 768px) */
@media screen and (max-width: 768px) {
  .app-header {
    padding: 12px 16px;
  }

  .back-btn {
    padding: 6px 12px;
    font-size: 13px;
  }

  .app-header h1 {
    font-size: 16px;
  }

  .main-content {
    padding: 16px;
  }

  .config-container {
    border-radius: 8px;
  }

  .config-nav {
    padding: 0 12px;
  }

  .nav-item {
    padding: 8px 12px;
    font-size: 13px;
  }

  .nav-icon {
    font-size: 16px;
  }

  .config-content {
    padding: 16px;
  }

  .section-title {
    font-size: 18px;
  }

  .section-desc {
    font-size: 13px;
  }

  .config-form {
    gap: 16px;
  }

  .form-group {
    gap: 6px;
  }

  .form-label {
    font-size: 13px;
  }

  .form-input,
  .form-select {
    padding: 8px 10px;
    font-size: 13px;
  }

  .radio-group {
    flex-direction: column;
    gap: 10px;
  }

  .color-options {
    flex-wrap: wrap;
  }

  .color-option {
    min-width: 70px;
    padding: 10px;
  }

  .config-actions {
    flex-direction: column-reverse;
    gap: 10px;
    margin-top: 24px;
    padding-top: 20px;
  }

  .btn-primary,
  .btn-secondary {
    width: 100%;
    padding: 12px;
  }

  /* 关于页面 */
  .about-content {
    padding: 24px 0;
  }

  .about-logo .logo-icon {
    font-size: 48px;
  }

  .about-logo h3 {
    font-size: 20px;
  }

  .feature-item {
    font-size: 13px;
    padding: 10px;
  }

  /* 成功提示 */
  .success-toast {
    left: 16px;
    right: 16px;
    bottom: 16px;
    justify-content: center;
  }
}

/* 小屏手机 (< 480px) */
@media screen and (max-width: 480px) {
  .app-header {
    padding: 10px 12px;
  }

  .back-btn span {
    font-size: 16px;
  }

  .app-header h1 {
    font-size: 14px;
  }

  .main-content {
    padding: 12px;
  }

  .nav-item {
    padding: 6px 10px;
    font-size: 12px;
  }

  .nav-icon {
    font-size: 14px;
  }

  .config-content {
    padding: 12px;
  }

  .section-title {
    font-size: 16px;
  }

  .form-input,
  .form-select {
    font-size: 16px; /* 防止 iOS 缩放 */
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  .back-btn:hover {
    border-color: #d9d9d9;
    color: #666;
  }

  .back-btn:active {
    background: #f0f0f0;
  }

  .nav-item:hover {
    background: transparent;
  }

  .nav-item.active {
    background: #e6f7ff;
  }

  .color-option:hover {
    border-color: #e8e8e8;
  }

  .color-option.active {
    border-color: #1890ff;
  }

  .btn-primary:hover {
    background: #1890ff;
  }

  .btn-primary:active {
    background: #096dd9;
  }

  .btn-secondary:hover {
    border-color: #d9d9d9;
    color: #666;
  }

  .btn-secondary:active {
    border-color: #1890ff;
    color: #1890ff;
  }
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .config-app {
    background: #1a1a1a;
  }

  .app-header {
    background: #2a2a2a;
    border-bottom-color: #3a3a3a;
  }

  .app-header h1 {
    color: #fff;
  }

  .back-btn {
    background: #3a3a3a;
    border-color: #4a4a4a;
    color: #ccc;
  }

  .back-btn:hover {
    border-color: #1890ff;
    color: #1890ff;
  }

  .config-container {
    background: #2a2a2a;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .config-sidebar {
    border-right-color: #3a3a3a;
    border-bottom-color: #3a3a3a;
  }

  .nav-item:hover {
    background: #3a3a3a;
  }

  .nav-item.active {
    background: rgba(24, 144, 255, 0.2);
    color: #1890ff;
  }

  .nav-label {
    color: #ccc;
  }

  .config-content {
    background: #2a2a2a;
  }

  .section-title {
    color: #fff;
  }

  .section-desc {
    color: #999;
  }

  .form-label {
    color: #ccc;
  }

  .form-input,
  .form-select {
    background: #3a3a3a;
    border-color: #4a4a4a;
    color: #fff;
  }

  .form-input:focus,
  .form-select:focus {
    border-color: #1890ff;
    box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.2);
  }

  .form-hint {
    color: #666;
  }

  .radio-text,
  .checkbox-text {
    color: #ccc;
  }

  .color-option {
    background: #3a3a3a;
    border-color: #4a4a4a;
  }

  .color-option.active {
    background: rgba(24, 144, 255, 0.2);
  }

  .color-label {
    color: #ccc;
  }

  .btn-secondary {
    background: #3a3a3a;
    border-color: #4a4a4a;
    color: #ccc;
  }

  .btn-secondary:hover {
    border-color: #1890ff;
    color: #1890ff;
  }

  .about-logo h3 {
    color: #fff;
  }

  .about-logo .version {
    color: #666;
  }

  .about-info p {
    color: #999;
  }

  .feature-item {
    background: #3a3a3a;
    color: #ccc;
  }
}
</style>
