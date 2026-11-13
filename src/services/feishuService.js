/**
 * feishuService - 飞书开放平台API服务（后端代理版）
 *
 * 所属模块：飞书集成
 *
 * [P0-1] 所有飞书调用统一走后端代理 `/api/v2/integrations/feishu/request`：
 *   - App ID / App Secret 只存在后端环境变量（FEISHU_APP_ID / FEISHU_APP_SECRET）
 *   - tenant_access_token 由后端缓存并自动刷新，前端不再持有任何凭证
 *   - 前端产物中不再出现 app_secret / Bearer token
 *
 * 使用方式：
 *   import feishuService from '@/services/feishuService.js'
 *   await feishuService.sendMessage(chatId, content)
 *
 * @see FeishuBotPanel.vue - 飞书机器人面板组件
 * @see FeishuDataImport.vue - 飞书数据导入组件
 */

import { apiV2 } from '@/utils/httpClient';

const PROXY_PATH = '/integrations/feishu/request';

/**
 * Blob/File 转 base64（去掉 data URL 前缀）
 * @param {Blob|File} blob
 * @returns {Promise<string>}
 */
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',')[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error('读取文件失败'));
    reader.readAsDataURL(blob);
  });
}

class FeishuService {
  /**
   * 兼容旧调用方：凭证已由后端托管，此处不再保存任何密钥。
   * @param {Object} [_config] 旧配置对象，忽略
   */
  init(_config) {
    // no-op：App ID / App Secret / accessToken 不再进入前端
  }

  /**
   * 统一代理请求
   * @param {string} method
   * @param {string} path - 飞书 OpenAPI 路径，如 /im/v1/chats
   * @param {Object} [options]
   * @param {Object} [options.query]
   * @param {Object} [options.body]
   * @param {Object} [options.file] - { name, content_type, content_base64 }
   * @returns {Promise<Object>} 上游原始 JSON（含 code/msg/data）
   */
  async _request(method, path, { query, body, file } = {}) {
    const payload = { method, path };
    if (query) payload.query = query;
    if (body) payload.body = body;
    if (file) payload.file = file;

    const result = await apiV2.post(PROXY_PATH, payload);
    if (!result.success) {
      throw new Error(result.message || '飞书接口调用失败');
    }
    return result.data || {};
  }

  /**
   * 兼容旧调用方：凭证由后端管理，此处仅做连通性自检。
   * @returns {Promise<string>} 固定占位值（调用方只用于判断是否成功）
   */
  async getTenantAccessToken() {
    await this.testConnection();
    return 'backend-managed';
  }

  /**
   * 兼容旧调用方：token 由后端缓存，无需前端确保。
   */
  async ensureAccessToken() {
    // no-op
  }

  /**
   * 飞书连通性自检（后端强制刷新 tenant_access_token）
   * @returns {Promise<Object>} { valid, app_id, message }
   */
  async testConnection() {
    const result = await apiV2.post('/integrations/feishu/test', {});
    if (!result.success) {
      throw new Error(result.message || '飞书连通性检测失败');
    }
    const data = result.data || {};
    if (!data.valid) {
      throw new Error(data.message || '飞书凭证无效');
    }
    return data;
  }

  /**
   * 发送文本消息到飞书
   * @param {string} receiveId
   * @param {string} content
   * @param {string} receiveType
   * @returns {Promise<Object>} { success, data }
   */
  async sendTextMessage(receiveId, content, receiveType = 'chat_id') {
    try {
      const data = await this._request('POST', '/im/v1/messages', {
        query: { receive_id_type: receiveType },
        body: {
          receive_id: receiveId,
          content: JSON.stringify({ text: content }),
          msg_type: 'text'
        }
      });
      if (data.code === 0) {
        return { success: true, data: data.data };
      }
      throw new Error(data.msg || '发送消息失败');
    } catch (error) {
      console.error('发送飞书消息失败:', error);
      throw error;
    }
  }

  /**
   * 发送图片消息到飞书
   * @param {string} receiveId
   * @param {string} imageKey
   * @param {string} receiveType
   * @returns {Promise<Object>} { success, data }
   */
  async sendImageMessage(receiveId, imageKey, receiveType = 'chat_id') {
    try {
      const data = await this._request('POST', '/im/v1/messages', {
        query: { receive_id_type: receiveType },
        body: {
          receive_id: receiveId,
          content: JSON.stringify({ image_key: imageKey }),
          msg_type: 'image'
        }
      });
      if (data.code === 0) {
        return { success: true, data: data.data };
      }
      throw new Error(data.msg || '发送图片消息失败');
    } catch (error) {
      console.error('发送飞书图片消息失败:', error);
      throw error;
    }
  }

  /**
   * 上传图片到飞书（后端 base64 解码后以 multipart 转发）
   * @param {Blob|File} imageFile
   * @returns {Promise<string>} 图片key
   */
  async uploadImage(imageFile) {
    try {
      const contentBase64 = await blobToBase64(imageFile);
      const data = await this._request('POST', '/im/v1/images', {
        body: { image_type: 'message' },
        file: {
          name: imageFile.name || 'image.png',
          content_type: imageFile.type || 'image/png',
          content_base64: contentBase64
        }
      });
      if (data.code === 0 && data.data && data.data.image_key) {
        return data.data.image_key;
      }
      throw new Error(data.msg || '上传图片失败');
    } catch (error) {
      console.error('上传图片到飞书失败:', error);
      throw error;
    }
  }

  /**
   * 发送图表到飞书（图片形式）
   * @param {string} receiveId
   * @param {Blob|File} imageFile
   * @param {string} message
   * @returns {Promise<Object>} 发送结果
   */
  async sendDiagramToFeishu(receiveId, imageFile, message = '') {
    try {
      const imageKey = await this.uploadImage(imageFile);
      const result = await this.sendImageMessage(receiveId, imageKey);
      if (message) {
        await this.sendTextMessage(receiveId, message);
      }
      return { success: true, data: result.data };
    } catch (error) {
      console.error('发送图表到飞书失败:', error);
      throw error;
    }
  }

  /**
   * 获取用户列表
   * @param {Object} params
   * @returns {Promise<Array>} 用户列表
   */
  async getUserList(params = {}) {
    try {
      const query = { page_size: params.pageSize || 50, ...params };
      delete query.pageSize;
      const data = await this._request('GET', '/contact/v3/users', { query });
      if (data.code === 0) {
        return (data.data && data.data.items) || [];
      }
      throw new Error(data.msg || '获取用户列表失败');
    } catch (error) {
      console.error('获取飞书用户列表失败:', error);
      throw error;
    }
  }

  /**
   * 获取群组列表
   * @returns {Promise<Array>} 群组列表
   */
  async getChatList() {
    try {
      const data = await this._request('GET', '/im/v1/chats', {
        query: { page_size: 100 }
      });
      if (data.code === 0) {
        return (data.data && data.data.items) || [];
      }
      throw new Error(data.msg || '获取群组列表失败');
    } catch (error) {
      console.error('获取飞书群组列表失败:', error);
      throw error;
    }
  }

  /**
   * 从飞书表格读取数据
   * @param {string} spreadsheetToken
   * @param {string} sheetId
   * @param {string} range
   * @returns {Promise<Object>} 表格数据
   */
  async getSpreadsheetData(spreadsheetToken, sheetId, range) {
    try {
      const path = `/sheets/v2/spreadsheets/${spreadsheetToken}/values/${sheetId}!${range}`;
      const data = await this._request('GET', path);
      if (data.code === 0) {
        return data.data;
      }
      throw new Error(data.msg || '获取表格数据失败');
    } catch (error) {
      console.error('从飞书表格获取数据失败:', error);
      throw error;
    }
  }

  /**
   * 获取机器人信息
   * @returns {Promise<Object>} 机器人信息
   */
  async getBotInfo() {
    try {
      const data = await this._request('GET', '/bot/v3/info');
      if (data.code === 0) {
        return data.data;
      }
      throw new Error(data.msg || '获取机器人信息失败');
    } catch (error) {
      console.error('获取飞书机器人信息失败:', error);
      throw error;
    }
  }

  /**
   * 回复机器人消息（用于Webhook回调）
   * @param {string} messageId
   * @param {string} content
   * @param {string} msgType
   * @returns {Promise<Object>} { success, data }
   */
  async replyMessage(messageId, content, msgType = 'text') {
    try {
      const data = await this._request('POST', `/im/v1/messages/${messageId}/reply`, {
        body: {
          content: msgType === 'text' ? JSON.stringify({ text: content }) : content,
          msg_type: msgType
        }
      });
      if (data.code === 0) {
        return { success: true, data: data.data };
      }
      throw new Error(data.msg || '回复消息失败');
    } catch (error) {
      console.error('回复飞书消息失败:', error);
      throw error;
    }
  }
}

// 创建单例实例
const feishuService = new FeishuService();

export default feishuService;
export { FeishuService };