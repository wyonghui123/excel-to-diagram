<template>
  <div class="feishu-data-import">
    <div class="import-header">
      <h3>📥 从飞书导入数据</h3>
      <button class="close-btn" @click="$emit('close')">×</button>
    </div>

    <div class="import-content">
      <!-- 步骤指示器 -->
      <div class="steps">
        <div 
          v-for="(step, index) in steps" 
          :key="index"
          class="step"
          :class="{ active: currentStep === index, completed: currentStep > index }"
        >
          <div class="step-number">{{ index + 1 }}</div>
          <div class="step-label">{{ step }}</div>
        </div>
      </div>

      <!-- 步骤1: 选择数据源 -->
      <div v-if="currentStep === 0" class="step-content">
        <h4>选择数据源类型</h4>
        <div class="source-options">
          <div 
            v-for="source in dataSources" 
            :key="source.key"
            class="source-card"
            :class="{ selected: selectedSource === source.key }"
            @click="selectedSource = source.key"
          >
            <div class="source-icon">{{ source.icon }}</div>
            <div class="source-name">{{ source.name }}</div>
            <div class="source-desc">{{ source.description }}</div>
          </div>
        </div>
      </div>

      <!-- 步骤2: 选择具体数据 -->
      <div v-if="currentStep === 1" class="step-content">
        <div v-if="selectedSource === 'spreadsheet'">
          <h4>选择飞书表格</h4>
          <div class="input-group">
            <label>表格 Token</label>
            <input 
              v-model="spreadsheetToken"
              type="text"
              placeholder="请输入飞书表格的 Token"
            />
            <span class="hint">在飞书表格URL中找到，如：shtcnxxxxxxxx</span>
          </div>
          <div class="input-group">
            <label>工作表名称</label>
            <input 
              v-model="sheetName"
              type="text"
              placeholder="如：Sheet1"
            />
          </div>
          <div class="input-group">
            <label>数据范围</label>
            <input 
              v-model="dataRange"
              type="text"
              placeholder="如：A1:Z100"
            />
          </div>
        </div>

        <div v-if="selectedSource === 'chat'">
          <h4>选择飞书群组</h4>
          <div v-if="loadingChats" class="loading">
            加载群组列表...
          </div>
          <div v-else-if="chatList.length > 0" class="chat-list">
            <div 
              v-for="chat in chatList" 
              :key="chat.chat_id"
              class="chat-item"
              :class="{ selected: selectedChatId === chat.chat_id }"
              @click="selectedChatId = chat.chat_id"
            >
              <div class="chat-avatar">👥</div>
              <div class="chat-info">
                <div class="chat-name">{{ chat.name }}</div>
                <div class="chat-id">ID: {{ chat.chat_id }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <p>未找到群组</p>
            <button class="btn-refresh" @click="loadChatList">刷新</button>
          </div>
        </div>

        <div v-if="selectedSource === 'document'">
          <h4>选择飞书文档</h4>
          <div class="input-group">
            <label>文档 Token</label>
            <input 
              v-model="documentToken"
              type="text"
              placeholder="请输入飞书文档的 Token"
            />
            <span class="hint">在飞书文档URL中找到</span>
          </div>
        </div>
      </div>

      <!-- 步骤3: 预览和确认 -->
      <div v-if="currentStep === 2" class="step-content">
        <h4>数据预览</h4>
        <div v-if="loadingPreview" class="loading">
          加载预览数据...
        </div>
        <div v-else-if="previewData" class="preview-container">
          <div class="preview-info">
            <span>共 {{ previewData.rowCount }} 行数据</span>
            <span>共 {{ previewData.columnCount }} 列</span>
          </div>
          <div class="preview-table-wrapper">
            <table class="preview-table">
              <thead>
                <tr>
                  <th v-for="(header, index) in previewData.headers" :key="index">
                    {{ header }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIndex) in previewData.rows" :key="rowIndex">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="preview-hint">仅显示前 5 行数据作为预览</p>
        </div>
        <div v-else class="empty-state">
          <p>暂无预览数据</p>
          <button class="btn-primary" @click="loadPreview">加载预览</button>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <button 
          v-if="currentStep > 0" 
          class="btn-secondary"
          @click="prevStep"
        >
          上一步
        </button>
        <button 
          v-if="currentStep < steps.length - 1" 
          class="btn-primary"
          @click="nextStep"
          :disabled="!canProceed"
        >
          下一步
        </button>
        <button 
          v-if="currentStep === steps.length - 1" 
          class="btn-primary"
          @click="confirmImport"
          :disabled="!previewData"
        >
          确认导入
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import feishuService from '../services/feishuService.js'

export default {
  name: 'FeishuDataImport',
  emits: ['close', 'import'],
  setup(props, { emit }) {
    const currentStep = ref(0)
    const steps = ['选择数据源', '配置数据', '预览确认']

    // 数据源选项
    const dataSources = [
      { 
        key: 'spreadsheet', 
        name: '飞书表格', 
        icon: '📊',
        description: '从飞书多维表格导入数据'
      },
      { 
        key: 'chat', 
        name: '群组消息', 
        icon: '💬',
        description: '从飞书群组获取历史消息'
      },
      { 
        key: 'document', 
        name: '飞书文档', 
        icon: '📄',
        description: '从飞书文档提取结构化数据'
      }
    ]

    const selectedSource = ref('')

    // 表格相关
    const spreadsheetToken = ref('')
    const sheetName = ref('Sheet1')
    const dataRange = ref('A1:Z100')

    // 群组相关
    const chatList = ref([])
    const loadingChats = ref(false)
    const selectedChatId = ref('')

    // 文档相关
    const documentToken = ref('')

    // 预览相关
    const loadingPreview = ref(false)
    const previewData = ref(null)

    // 是否可以进入下一步
    const canProceed = computed(() => {
      if (currentStep.value === 0) {
        return !!selectedSource.value
      }
      if (currentStep.value === 1) {
        if (selectedSource.value === 'spreadsheet') {
          return !!spreadsheetToken.value && !!sheetName.value && !!dataRange.value
        }
        if (selectedSource.value === 'chat') {
          return !!selectedChatId.value
        }
        if (selectedSource.value === 'document') {
          return !!documentToken.value
        }
      }
      return true
    })

    // 下一步
    const nextStep = async () => {
      if (currentStep.value === 1 && selectedSource.value === 'chat') {
        await loadChatList()
      }
      if (currentStep.value === 1) {
        await loadPreview()
      }
      if (currentStep.value < steps.length - 1) {
        currentStep.value++
      }
    }

    // 上一步
    const prevStep = () => {
      if (currentStep.value > 0) {
        currentStep.value--
      }
    }

    // 加载群组列表
    const loadChatList = async () => {
      loadingChats.value = true
      try {
        const savedConfig = localStorage.getItem('archWorkspaceConfig')
        if (!savedConfig) return

        const config = JSON.parse(savedConfig)
        feishuService.init({
          appId: config.feishuAppId,
          appSecret: config.feishuAppSecret,
          accessToken: config.feishuAccessToken
        })

        const chats = await feishuService.getChatList()
        chatList.value = chats
      } catch (error) {
        console.error('加载群组列表失败:', error)
        alert('加载群组列表失败: ' + error.message)
      } finally {
        loadingChats.value = false
      }
    }

    // 加载预览数据
    const loadPreview = async () => {
      loadingPreview.value = true
      try {
        const savedConfig = localStorage.getItem('archWorkspaceConfig')
        if (!savedConfig) return

        const config = JSON.parse(savedConfig)
        feishuService.init({
          appId: config.feishuAppId,
          appSecret: config.feishuAppSecret,
          accessToken: config.feishuAccessToken
        })

        if (selectedSource.value === 'spreadsheet') {
          const data = await feishuService.getSpreadsheetData(
            spreadsheetToken.value,
            sheetName.value,
            dataRange.value
          )
          
          // 解析表格数据
          if (data.valueRange && data.valueRange.values) {
            const values = data.valueRange.values
            previewData.value = {
              headers: values[0] || [],
              rows: values.slice(1, 6), // 只显示前5行
              rowCount: values.length - 1,
              columnCount: values[0]?.length || 0
            }
          }
        }
        // 其他数据源的处理可以在这里扩展
      } catch (error) {
        console.error('加载预览数据失败:', error)
        alert('加载预览数据失败: ' + error.message)
      } finally {
        loadingPreview.value = false
      }
    }

    // 确认导入
    const confirmImport = () => {
      emit('import', {
        source: selectedSource.value,
        data: previewData.value,
        config: {
          spreadsheetToken: spreadsheetToken.value,
          sheetName: sheetName.value,
          dataRange: dataRange.value
        }
      })
    }

    onMounted(() => {
      // 检查飞书配置
      const savedConfig = localStorage.getItem('archWorkspaceConfig')
      if (savedConfig) {
        const config = JSON.parse(savedConfig)
        if (!config.feishuEnabled) {
          alert('飞书集成未启用，请先在配置中开启')
        }
      }
    })

    return {
      currentStep,
      steps,
      dataSources,
      selectedSource,
      spreadsheetToken,
      sheetName,
      dataRange,
      chatList,
      loadingChats,
      selectedChatId,
      documentToken,
      loadingPreview,
      previewData,
      canProceed,
      nextStep,
      prevStep,
      loadChatList,
      loadPreview,
      confirmImport
    }
  }
}
</script>

<style scoped>
.feishu-data-import {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 600px;
  max-width: 90vw;
  max-height: 80vh;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
}

.import-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid #e8e8e8;
}

.import-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.import-content {
  flex: 1;
  overflow: auto;
  padding: 24px;
}

/* 步骤指示器 */
.steps {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin-bottom: 32px;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.step-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f2f5;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
}

.step.active .step-number {
  background: #3370ff;
  color: #fff;
}

.step.completed .step-number {
  background: #52c41a;
  color: #fff;
}

.step-label {
  font-size: 13px;
  color: #999;
}

.step.active .step-label {
  color: #3370ff;
  font-weight: 500;
}

/* 步骤内容 */
.step-content {
  min-height: 300px;
}

.step-content h4 {
  margin: 0 0 20px 0;
  font-size: 16px;
  color: #333;
}

/* 数据源选项 */
.source-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.source-card {
  padding: 20px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.source-card:hover {
  border-color: #3370ff;
}

.source-card.selected {
  border-color: #3370ff;
  background: #f0f5ff;
}

.source-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.source-name {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.source-desc {
  font-size: 12px;
  color: #999;
}

/* 输入组 */
.input-group {
  margin-bottom: 20px;
}

.input-group label {
  display: block;
  font-size: 14px;
  color: #333;
  margin-bottom: 8px;
  font-weight: 500;
}

.input-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.input-group input:focus {
  outline: none;
  border-color: #3370ff;
}

.input-group .hint {
  display: block;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

/* 群组列表 */
.chat-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
}

.chat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.chat-item:last-child {
  border-bottom: none;
}

.chat-item:hover {
  background: #f5f7fa;
}

.chat-item.selected {
  background: #f0f5ff;
}

.chat-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #3370ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.chat-info {
  flex: 1;
}

.chat-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 2px;
}

.chat-id {
  font-size: 12px;
  color: #999;
}

/* 预览表格 */
.preview-container {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.preview-info {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e8e8e8;
  font-size: 13px;
  color: #666;
}

.preview-table-wrapper {
  max-height: 300px;
  overflow: auto;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.preview-table th,
.preview-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
}

.preview-table th {
  background: #fafafa;
  font-weight: 600;
  color: #333;
  position: sticky;
  top: 0;
}

.preview-table td {
  color: #666;
}

.preview-hint {
  padding: 10px 16px;
  margin: 0;
  font-size: 12px;
  color: #999;
  background: #fafafa;
  border-top: 1px solid #f0f0f0;
}

/* 加载状态 */
.loading {
  text-align: center;
  padding: 40px;
  color: #999;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #999;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid #e8e8e8;
  margin-top: 24px;
}

.btn-primary {
  padding: 10px 24px;
  background: #3370ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #2c5de6;
}

.btn-primary:disabled {
  background: #ccc;
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
  border-color: #3370ff;
  color: #3370ff;
}

.btn-refresh {
  padding: 8px 16px;
  background: #3370ff;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  margin-top: 12px;
}
</style>
