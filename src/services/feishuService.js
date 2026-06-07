/**
 * feishuService - 飞书开放平台API服务
 *
 * 所属模块：飞书集成
 * 主要功能：
 *   - 获取访问令牌
 *   - 发送消息到飞书群
 *   - 上传图片/文件到飞书
 *   - 获取群成员信息
 *
 * 使用方式：
 *   import feishuService from '@/services/feishuService.js'
 *   feishuService.init(config)
 *   await feishuService.sendMessage(chatId, content)
 *
 * @see FeishuBotPanel.vue - 飞书机器人面板组件
 * @see FeishuDataImport.vue - 飞书数据导入组件
 */

class FeishuService {
  constructor() {
    this.appId = ''
    this.appSecret = ''
    this.accessToken = ''
    this.baseUrl = 'https://open.feishu.cn/open-apis'
  }

  /**
   * 初始化配置
   * @param {Object} config - 配置对象
   * @param {string} config.appId - 飞书 App ID
   * @param {string} config.appSecret - 飞书 App Secret
   * @param {string} config.accessToken - 访问令牌（可选）
   */
  init(config) {
    this.appId = config.appId || import.meta.env.VITE_FEISHU_APP_ID || ''
    this.appSecret = config.appSecret || import.meta.env.VITE_FEISHU_APP_SECRET || ''
    this.accessToken = config.accessToken || import.meta.env.VITE_FEISHU_ACCESS_TOKEN || ''
  }

  /**
   * 获取租户访问令牌
   * @returns {Promise<string>} 访问令牌
   */
  async getTenantAccessToken() {
    if (!this.appId || !this.appSecret) {
      throw new Error('App ID 和 App Secret 未配置')
    }

    try {
      const response = await fetch(`${this.baseUrl}/auth/v3/tenant_access_token/internal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          app_id: this.appId,
          app_secret: this.appSecret
        })
      })

      const data = await response.json()

      if (data.code === 0 && data.tenant_access_token) {
        this.accessToken = data.tenant_access_token
        return data.tenant_access_token
      } else {
        throw new Error(data.msg || '获取访问令牌失败')
      }
    } catch (error) {
      console.error('获取飞书访问令牌失败:', error)
      throw error
    }
  }

  /**
   * 确保有有效的访问令牌
   */
  async ensureAccessToken() {
    if (!this.accessToken) {
      await this.getTenantAccessToken()
    }
  }

  /**
   * 发送文本消息到飞书
   * @param {string} receiveId - 接收者ID（群ID以oc_开头，用户ID以ou_开头）
   * @param {string} content - 消息内容
   * @param {string} receiveType - 接收者类型：'chat_id' | 'open_id' | 'union_id' | 'email' | 'user_id'
   * @returns {Promise<Object>} 发送结果
   */
  async sendTextMessage(receiveId, content, receiveType = 'chat_id') {
    await this.ensureAccessToken()

    try {
      const response = await fetch(`${this.baseUrl}/im/v1/messages?receive_id_type=${receiveType}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          receive_id: receiveId,
          content: JSON.stringify({ text: content }),
          msg_type: 'text'
        })
      })

      const data = await response.json()

      if (data.code === 0) {
        return { success: true, data: data.data }
      } else {
        throw new Error(data.msg || '发送消息失败')
      }
    } catch (error) {
      console.error('发送飞书消息失败:', error)
      throw error
    }
  }

  /**
   * 发送图片消息到飞书
   * @param {string} receiveId - 接收者ID
   * @param {string} imageKey - 图片key（需先上传图片获取）
   * @param {string} receiveType - 接收者类型
   * @returns {Promise<Object>} 发送结果
   */
  async sendImageMessage(receiveId, imageKey, receiveType = 'chat_id') {
    await this.ensureAccessToken()

    try {
      const response = await fetch(`${this.baseUrl}/im/v1/messages?receive_id_type=${receiveType}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          receive_id: receiveId,
          content: JSON.stringify({ image_key: imageKey }),
          msg_type: 'image'
        })
      })

      const data = await response.json()

      if (data.code === 0) {
        return { success: true, data: data.data }
      } else {
        throw new Error(data.msg || '发送图片消息失败')
      }
    } catch (error) {
      console.error('发送飞书图片消息失败:', error)
      throw error
    }
  }

  /**
   * 上传图片到飞书
   * @param {Blob|File} imageFile - 图片文件
   * @returns {Promise<string>} 图片key
   */
  async uploadImage(imageFile) {
    await this.ensureAccessToken()

    try {
      const formData = new FormData()
      formData.append('image_type', 'message')
      formData.append('image', imageFile)

      const response = await fetch(`${this.baseUrl}/im/v1/images`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`
        },
        body: formData
      })

      const data = await response.json()

      if (data.code === 0 && data.data && data.data.image_key) {
        return data.data.image_key
      } else {
        throw new Error(data.msg || '上传图片失败')
      }
    } catch (error) {
      console.error('上传图片到飞书失败:', error)
      throw error
    }
  }

  /**
   * 发送图表到飞书（图片形式）
   * @param {string} receiveId - 接收者ID
   * @param {Blob|File} imageFile - 图表图片文件
   * @param {string} message - 附加消息文本
   * @returns {Promise<Object>} 发送结果
   */
  async sendDiagramToFeishu(receiveId, imageFile, message = '') {
    try {
      // 先上传图片
      const imageKey = await this.uploadImage(imageFile)
      
      // 发送图片消息
      const result = await this.sendImageMessage(receiveId, imageKey)
      
      // 如果有附加消息，再发送文本消息
      if (message) {
        await this.sendTextMessage(receiveId, message)
      }
      
      return { success: true, data: result.data }
    } catch (error) {
      console.error('发送图表到飞书失败:', error)
      throw error
    }
  }

  /**
   * 获取用户列表
   * @param {Object} params - 查询参数
   * @returns {Promise<Array>} 用户列表
   */
  async getUserList(params = {}) {
    await this.ensureAccessToken()

    const queryParams = new URLSearchParams({
      page_size: params.pageSize || 50,
      ...params
    })

    try {
      const response = await fetch(`${this.baseUrl}/contact/v3/users?${queryParams}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`
        }
      })

      const data = await response.json()

      if (data.code === 0) {
        return data.data.items || []
      } else {
        throw new Error(data.msg || '获取用户列表失败')
      }
    } catch (error) {
      console.error('获取飞书用户列表失败:', error)
      throw error
    }
  }

  /**
   * 获取群组列表
   * @returns {Promise<Array>} 群组列表
   */
  async getChatList() {
    await this.ensureAccessToken()

    try {
      const response = await fetch(`${this.baseUrl}/im/v1/chats?page_size=100`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`
        }
      })

      const data = await response.json()

      if (data.code === 0) {
        return data.data.items || []
      } else {
        throw new Error(data.msg || '获取群组列表失败')
      }
    } catch (error) {
      console.error('获取飞书群组列表失败:', error)
      throw error
    }
  }

  /**
   * 从飞书表格读取数据
   * @param {string} spreadsheetToken - 表格token
   * @param {string} sheetId - 工作表ID
   * @param {string} range - 数据范围，如 'A1:Z100'
   * @returns {Promise<Object>} 表格数据
   */
  async getSpreadsheetData(spreadsheetToken, sheetId, range) {
    await this.ensureAccessToken()

    try {
      const response = await fetch(
        `${this.baseUrl}/sheets/v2/spreadsheets/${spreadsheetToken}/values/${sheetId}!${range}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${this.accessToken}`
          }
        }
      )

      const data = await response.json()

      if (data.code === 0) {
        return data.data
      } else {
        throw new Error(data.msg || '获取表格数据失败')
      }
    } catch (error) {
      console.error('从飞书表格获取数据失败:', error)
      throw error
    }
  }

  /**
   * 获取机器人信息
   * @returns {Promise<Object>} 机器人信息
   */
  async getBotInfo() {
    await this.ensureAccessToken()

    try {
      const response = await fetch(`${this.baseUrl}/bot/v3/info`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`
        }
      })

      const data = await response.json()

      if (data.code === 0) {
        return data.data
      } else {
        throw new Error(data.msg || '获取机器人信息失败')
      }
    } catch (error) {
      console.error('获取飞书机器人信息失败:', error)
      throw error
    }
  }

  /**
   * 回复机器人消息（用于Webhook回调）
   * @param {string} messageId - 消息ID
   * @param {string} content - 回复内容
   * @param {string} msgType - 消息类型
   * @returns {Promise<Object>} 发送结果
   */
  async replyMessage(messageId, content, msgType = 'text') {
    await this.ensureAccessToken()

    try {
      const response = await fetch(`${this.baseUrl}/im/v1/messages/${messageId}/reply`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          content: msgType === 'text' ? JSON.stringify({ text: content }) : content,
          msg_type: msgType
        })
      })

      const data = await response.json()

      if (data.code === 0) {
        return { success: true, data: data.data }
      } else {
        throw new Error(data.msg || '回复消息失败')
      }
    } catch (error) {
      console.error('回复飞书消息失败:', error)
      throw error
    }
  }
}

// 创建单例实例
const feishuService = new FeishuService()

export default feishuService
export { FeishuService }
