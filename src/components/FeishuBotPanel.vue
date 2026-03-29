<template>
  <div class="feishu-bot-panel">
    <div class="panel-header">
      <h3>🤖 飞书机器人交互</h3>
      <button class="close-btn" @click="$emit('close')">×</button>
    </div>

    <div class="panel-content">
      <!-- 连接状态 -->
      <div class="connection-status" :class="{ connected: isConnected }">
        <span class="status-dot"></span>
        <span class="status-text">{{ isConnected ? '已连接' : '未连接' }}</span>
        <button 
          v-if="!isConnected" 
          class="btn-connect" 
          @click="connectBot"
          :disabled="connecting"
        >
          {{ connecting ? '连接中...' : '连接机器人' }}
        </button>
      </div>

      <!-- 消息列表 -->
      <div class="messages-container" ref="messagesContainer">
        <div 
          v-for="(msg, index) in messages" 
          :key="index"
          class="message-item"
          :class="{ 
            'message-incoming': msg.type === 'incoming',
            'message-outgoing': msg.type === 'outgoing'
          }"
        >
          <div class="message-avatar">
            {{ msg.type === 'incoming' ? '🤖' : '👤' }}
          </div>
          <div class="message-content">
            <div class="message-text">{{ msg.text }}</div>
            <div class="message-time">{{ formatTime(msg.time) }}</div>
          </div>
        </div>

        <div v-if="messages.length === 0" class="empty-state">
          <p>暂无消息</p>
          <p class="hint">发送 "生成图表" 或 "help" 查看支持的命令</p>
        </div>
      </div>

      <!-- 命令快捷按钮 -->
      <div class="quick-commands">
        <button 
          v-for="cmd in quickCommands" 
          :key="cmd.key"
          class="cmd-btn"
          @click="sendCommand(cmd.text)"
        >
          {{ cmd.label }}
        </button>
      </div>

      <!-- 输入区域 -->
      <div class="input-area">
        <input 
          v-model="inputMessage"
          type="text"
          placeholder="输入消息或命令..."
          @keyup.enter="sendMessage"
          :disabled="!isConnected"
        />
        <button 
          class="btn-send" 
          @click="sendMessage"
          :disabled="!isConnected || !inputMessage.trim()"
        >
          发送
        </button>
      </div>
    </div>

    <!-- 帮助弹窗 -->
    <div v-if="showHelp" class="help-modal" @click.self="showHelp = false">
      <div class="help-content">
        <h4>📖 支持的命令</h4>
        <ul>
          <li><code>help</code> - 显示帮助信息</li>
          <li><code>生成图表</code> - 根据当前数据生成图表</li>
          <li><code>导出 [格式]</code> - 导出图表，格式可选：png, pdf, svg</li>
          <li><code>发送飞书</code> - 将当前图表发送到飞书</li>
          <li><code>状态</code> - 查看当前图表状态</li>
        </ul>
        <button class="btn-close-help" @click="showHelp = false">关闭</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, nextTick } from 'vue'
import feishuService from '../services/feishuService.js'

export default {
  name: 'FeishuBotPanel',
  emits: ['close', 'command'],
  setup(props, { emit }) {
    const isConnected = ref(false)
    const connecting = ref(false)
    const inputMessage = ref('')
    const messages = ref([])
    const messagesContainer = ref(null)
    const showHelp = ref(false)

    const quickCommands = [
      { key: 'help', label: '❓ 帮助', text: 'help' },
      { key: 'generate', label: '📊 生成图表', text: '生成图表' },
      { key: 'export', label: '📤 导出PNG', text: '导出 png' },
      { key: 'send', label: '📱 发送飞书', text: '发送飞书' }
    ]

    // 连接机器人
    const connectBot = async () => {
      connecting.value = true
      
      try {
        // 加载配置
        const savedConfig = localStorage.getItem('archWorkspaceConfig')
        if (!savedConfig) {
          addMessage('outgoing', '请先配置飞书集成')
          return
        }

        const config = JSON.parse(savedConfig)
        if (!config.feishuEnabled) {
          addMessage('outgoing', '飞书集成未启用，请在配置中开启')
          return
        }

        // 初始化服务
        feishuService.init({
          appId: config.feishuAppId,
          appSecret: config.feishuAppSecret,
          accessToken: config.feishuAccessToken
        })

        // 获取机器人信息测试连接
        const botInfo = await feishuService.getBotInfo()
        isConnected.value = true
        addMessage('incoming', `你好！我是 ${botInfo.app_name}，可以帮你生成和导出架构图。发送 "help" 查看支持的命令。`)
      } catch (error) {
        console.error('连接飞书机器人失败:', error)
        addMessage('outgoing', '连接失败: ' + error.message)
      } finally {
        connecting.value = false
      }
    }

    // 添加消息
    const addMessage = (type, text) => {
      messages.value.push({
        type,
        text,
        time: new Date()
      })
      
      // 滚动到底部
      nextTick(() => {
        if (messagesContainer.value) {
          messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
        }
      })
    }

    // 发送消息
    const sendMessage = async () => {
      const text = inputMessage.value.trim()
      if (!text) return

      addMessage('outgoing', text)
      inputMessage.value = ''

      // 处理命令
      await processCommand(text)
    }

    // 发送快捷命令
    const sendCommand = (command) => {
      inputMessage.value = command
      sendMessage()
    }

    // 处理命令
    const processCommand = async (text) => {
      const lowerText = text.toLowerCase()

      if (lowerText === 'help' || lowerText === '帮助') {
        showHelp.value = true
        addMessage('incoming', '已显示帮助信息')
      } else if (lowerText === '生成图表') {
        addMessage('incoming', '正在生成图表...')
        emit('command', { type: 'generate' })
      } else if (lowerText.startsWith('导出')) {
        const format = lowerText.split(' ')[1] || 'png'
        addMessage('incoming', `正在导出 ${format.toUpperCase()} 格式...`)
        emit('command', { type: 'export', format })
      } else if (lowerText === '发送飞书') {
        addMessage('incoming', '正在发送到飞书...')
        emit('command', { type: 'sendToFeishu' })
      } else if (lowerText === '状态') {
        emit('command', { type: 'status' })
      } else {
        addMessage('incoming', '抱歉，我不理解这个命令。发送 "help" 查看支持的命令。')
      }
    }

    // 格式化时间
    const formatTime = (date) => {
      return date.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
      })
    }

    onMounted(() => {
      // 自动尝试连接
      const savedConfig = localStorage.getItem('archWorkspaceConfig')
      if (savedConfig) {
        const config = JSON.parse(savedConfig)
        if (config.feishuEnabled && config.feishuAccessToken) {
          connectBot()
        }
      }
    })

    return {
      isConnected,
      connecting,
      inputMessage,
      messages,
      messagesContainer,
      showHelp,
      quickCommands,
      connectBot,
      sendMessage,
      sendCommand,
      formatTime
    }
  }
}
</script>

<style scoped>
.feishu-bot-panel {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 380px;
  height: 500px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: linear-gradient(135deg, #3370ff 0%, #2c5de6 100%);
  border-radius: 12px 12px 0 0;
  color: #fff;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  color: #fff;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e8e8e8;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff4d4f;
}

.connection-status.connected .status-dot {
  background: #52c41a;
}

.status-text {
  flex: 1;
  font-size: 13px;
  color: #666;
}

.btn-connect {
  padding: 4px 12px;
  background: #3370ff;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.btn-connect:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  text-align: center;
  color: #999;
  padding: 40px 20px;
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 8px;
}

.message-item {
  display: flex;
  gap: 8px;
  max-width: 85%;
}

.message-incoming {
  align-self: flex-start;
}

.message-outgoing {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.message-content {
  background: #f5f7fa;
  padding: 10px 14px;
  border-radius: 12px;
  border-top-left-radius: 4px;
}

.message-outgoing .message-content {
  background: #3370ff;
  color: #fff;
  border-top-left-radius: 12px;
  border-top-right-radius: 4px;
}

.message-text {
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.message-outgoing .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.quick-commands {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e8e8e8;
  overflow-x: auto;
}

.cmd-btn {
  padding: 6px 12px;
  background: #f0f2f5;
  border: none;
  border-radius: 16px;
  font-size: 12px;
  color: #333;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.cmd-btn:hover {
  background: #e0e2e5;
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e8e8e8;
}

.input-area input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 20px;
  font-size: 14px;
  outline: none;
}

.input-area input:focus {
  border-color: #3370ff;
}

.input-area input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.btn-send {
  padding: 10px 20px;
  background: #3370ff;
  color: #fff;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-send:hover {
  background: #2c5de6;
}

.btn-send:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* 帮助弹窗 */
.help-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
}

.help-content {
  background: #fff;
  padding: 24px;
  border-radius: 12px;
  width: 320px;
  max-width: 90%;
}

.help-content h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
}

.help-content ul {
  margin: 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 2;
}

.help-content code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.btn-close-help {
  width: 100%;
  margin-top: 16px;
  padding: 10px;
  background: #3370ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
</style>
