/**
 * Screenplay Pattern - Ability
 *
 * Ability 描述 Actor 能做什么:
 *  - BrowseTheWeb: 浏览器操作(page)
 *  - CallAPI: HTTP API 调用
 *  - IsolateData: 测试数据隔离
 *
 * 用法:
 *   actor.can(BrowseTheWeb.with(page));
 *   const page = actor.abilityTo('BrowseTheWeb').page();
 */

export class BrowseTheWeb {
  constructor(page) {
    this._page = page;
  }

  static with(page) {
    return new BrowseTheWeb(page);
  }

  // Page 实例的 getter
  get page() {
    return this._page;
  }
}

export class CallAPI {
  constructor(client) {
    this.client = client;
  }

  static using(client) {
    return new CallAPI(client);
  }

  async get(path) {
    return await this.client.get(path);
  }

  async post(path, data) {
    return await this.client.post(path, data);
  }

  async delete(path) {
    return await this.client.delete(path);
  }

  async put(path, data) {
    return await this.client.put(path, data);
  }
}

export class IsolateData {
  constructor(isolation) {
    this.isolation = isolation;
  }

  static using(isolation) {
    return new IsolateData(isolation);
  }

  /**
   * 创建追踪数据(测试后自动清理)
   * @param {string} objectType - 对象类型,如 'business_object'
   * @param {Object} data - 数据
   * @returns {Promise<Object>} 创建的对象
   */
  async createTracked(objectType, data) {
    return await this.isolation.createTracked(objectType, data);
  }

  /**
   * 获取追踪数据
   */
  async getTracked(objectType, id) {
    return await this.isolation.get(objectType, id);
  }

  /**
   * 列出所有追踪数据
   */
  async listTracked(objectType) {
    return await this.isolation.list(objectType);
  }
}
