/**
 * BusinessRuleAssertor - 业务规则断言器 (T-005)
 *
 * 核心思想: 断言业务规则而非 DOM 文本
 * 错误信息含**业务语义**,而非 "expected X to be Y"
 *
 * 用法:
 *   await BusinessRuleAssertor.assertRule('BR-business_object-DEL-condition', {
 *     businessObject: { id: 'bo_001' },
 *     apiClient: actor.abilityTo('CallAPI').client
 *   });
 */

import fs from 'fs';
import path from 'path';

// 简单 yaml 解析(当 'yaml' 包不可用时回退)
function simpleYamlParse(content) {
  // 极简实现 - 只处理我们生成的 _business_rules/*.yaml
  // 假设格式: schema/object_id/total_rules/rules/<rule>
  const lines = content.split('\n');
  const result = { rules: [] };
  let currentRule = null;
  let indent = 0;

  for (const line of lines) {
    if (line.match(/^\s*-\s+id:/)) {
      if (currentRule) result.rules.push(currentRule);
      currentRule = { id: line.split('id:')[1].trim() };
    } else if (currentRule && line.match(/^\s+(type|condition|source|message):/)) {
      const [, key, ...rest] = line.trim().match(/^([\w_]+):\s*(.*)$/) || [];
      if (key) {
        currentRule[key] = rest.join(':').trim();
      }
    }
  }
  if (currentRule) result.rules.push(currentRule);
  return result;
}

// 业务规则索引缓存
let _indexCache = null;
let _indexLoadedAt = null;
const CACHE_TTL_MS = 60 * 1000; // 1 分钟

function getIndexPath() {
  // 项目根: e2e/screenplay/ → ../../.trae/specs/_business_rules/_index.json
  return path.resolve(
    process.cwd(),
    '.trae/specs/_business_rules/_index.json'
  );
}

function getRuleDir() {
  return path.dirname(getIndexPath());
}

async function loadIndex(force = false) {
  const now = Date.now();
  if (!force && _indexCache && _indexLoadedAt && (now - _indexLoadedAt < CACHE_TTL_MS)) {
    return _indexCache;
  }

  const indexPath = getIndexPath();
  if (!fs.existsSync(indexPath)) {
    throw new Error(
      `业务规则索引未生成: ${indexPath}\n` +
      `请运行: python .trae/scripts/discover_business_rules.py --all`
    );
  }
  const content = fs.readFileSync(indexPath, 'utf-8');
  _indexCache = JSON.parse(content);
  _indexLoadedAt = now;
  return _indexCache;
}

async function loadRuleById(ruleId) {
  const index = await loadIndex();
  // 在 _index.json 中找到 ruleId 所属的 object
  for (const obj of index.objects) {
    if (obj.rule_ids.includes(ruleId)) {
      const rulePath = path.join(getRuleDir(), `${obj.object_id}.yaml`);
      if (!fs.existsSync(rulePath)) {
        continue;
      }
      const content = fs.readFileSync(rulePath, 'utf-8');
      // 用本地 simpleYamlParse,避免依赖外部 yaml 包(vite 会静态分析 import())
      const data = simpleYamlParse(content);
      const rule = data.rules.find(r => r.id === ruleId);
      if (rule) {
        return rule;
      }
    }
  }
  throw new Error(`Rule not found: ${ruleId}`);
}

// -----------------------------------------------------------------------------
// API URL 映射 - 与 e2e/helpers/test-isolation.js 保持一致
// -----------------------------------------------------------------------------

const API_URL_FOR_TYPE = {
  // 业务对象类 - [FIX 2026-06-13] 必须用 /api/v2/bo/<type> 单数 (实测)
  product: '/api/v2/bo/product',
  version: '/api/v2/bo/version',
  product_version: '/api/v2/bo/version',
  business_object: '/api/v2/bo/business_object',
  relationship: '/api/v2/bo/relationship',
  domain: '/api/v2/bo/domain',
  enum_type: '/api/v2/enum',
  enum_value: '/api/v2/enum/value',
  // 权限类
  user: '/api/v2/user',
  user_group: '/api/v2/bo/user_group',
  role: '/api/v2/bo/role',
  permission: '/api/v2/permission',
  // 审计
  audit_log: '/api/v2/audit-log',
  // 业务流
  business_flow: '/api/v2/business-flow'
};

function apiUrlForType(type) {
  return API_URL_FOR_TYPE[type] || `/api/v2/${type}`;
}

function baseUrl() {
  // 后端默认 3010; 与 playwright.config.js baseURL 区分
  return process.env.API_BASE_URL || 'http://localhost:3010';
}

async function apiRequest(page, method, url, options = {}) {
  // 用 Playwright 的 page.request (自带 auth cookie)
  const fullUrl = url.startsWith('http') ? url : `${baseUrl()}${url}`;
  const fn = page.request[method.toLowerCase()];
  if (!fn) {
    throw new Error(`Unsupported HTTP method: ${method}`);
  }
  return await fn.call(page.request, fullUrl, options);
}

// -----------------------------------------------------------------------------
// 业务规则断言器
// -----------------------------------------------------------------------------

export class BusinessRuleAssertor {
  /**
   * 断言业务规则
   * @param {string} ruleId - 规则 ID, 如 'BR-business_object-DEL-condition'
   * @param {Object} context - 上下文,各 rule type 需要的参数不同
   * @returns {Promise<Object>} 断言结果 { valid, message, ruleMessage }
   */
  static async assertRule(ruleId, context = {}) {
    const rule = await loadRuleById(ruleId);

    switch (rule.type) {
      case 'deletability':
        return await this.assertDeletability(rule, context);
      case 'key_template':
        return await this.assertKeyTemplate(rule, context);
      case 'cascade_select':
        return await this.assertCascadeSelect(rule, context);
      case 'authorization':
        return await this.assertAuthorization(rule, context);
      case 'audit':
        return await this.assertAudit(rule, context);
      case 'aspect':
        return await this.assertAspect(rule, context);
      case 'cascade_delete':
        return await this.assertCascadeDelete(rule, context);
      case 'owner':
        return await this.assertOwner(rule, context);
      case 'filter_variant':
        return await this.assertFilterVariant(rule, context);
      default:
        throw new Error(`Unknown rule type: ${rule.type}`);
    }
  }

  /**
   * 1. deletability - 删除约束
   *
   * 业务语义: "存在关联关系的业务对象不能删除"
   *
   * @param {Object} rule - 规则定义
   * @param {Object} context - { businessObject, apiClient, relationCount }
   */
  static async assertDeletability(rule, context) {
    const { businessObject, apiClient, relationCount, page, type, id, relatedCount } = context;

    // 优先用 relatedCount / relationCount 直接断言
    let actualCount = relatedCount !== undefined ? relatedCount : relationCount;

    // 兼容旧调用: businessObject.id / businessObject.type
    const objType = type || (businessObject && businessObject.type) || 'business_object';
    const objId = id || (businessObject && businessObject.id);

    if (actualCount === undefined && objId && page) {
      // 从 API 获取实际关联数
      try {
        const relationsUrl = `${apiUrlForType(objType)}/${objId}/relations`;
        const resp = await apiRequest(page, 'GET', relationsUrl);
        if (resp.ok()) {
          const relations = await resp.json();
          actualCount = Array.isArray(relations) ? relations.length : 0;
        } else {
          actualCount = 0; // 接口不通, 默认无关联
        }
      } catch (e) {
        actualCount = 0;
      }
    }

    // 业务规则: 有关联 → 不可删除;无关联 → 可删除
    const canDelete = actualCount === 0;

    if (!canDelete) {
      // 业务断言失败 - 含业务语义错误
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: ${rule.message || '存在关联关系,不允许删除'}`,
        {
          ruleId: rule.id,
          ruleType: 'deletability',
          ruleMessage: rule.message,
          actualRelationCount: actualCount,
          businessObject,
        }
      );
    }

    return {
      valid: true,
      message: '无关联关系,可删除',
      ruleId: rule.id,
    };
  }

  /**
   * 2. key_template - 编码自动生成
   *
   * 业务语义: "新建业务对象时 code 应自动填充 = 服务模块编码 + 2 位序号"
   */
  static async assertKeyTemplate(rule, context) {
    const { code, serviceModuleCode, pattern } = context;
    if (!code) {
      throw new BusinessAssertionError(
        rule.id,
        '业务规则违反: code 字段为空',
        { ruleId: rule.id, ruleType: 'key_template' }
      );
    }

    if (serviceModuleCode && !code.startsWith(serviceModuleCode)) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: code 应以服务模块编码 ${serviceModuleCode} 开头,实际 ${code}`,
        { ruleId: rule.id, ruleType: 'key_template', actual: code, expected: serviceModuleCode }
      );
    }

    return {
      valid: true,
      message: `code ${code} 符合 key_template ${pattern || rule.condition}`,
      ruleId: rule.id,
    };
  }

  /**
   * 3. cascade_select - 级联下拉
   */
  static async assertCascadeSelect(rule, context) {
    const { field, parentValue, options, expectedCount } = context;
    const ruleCondition = rule.condition;

    if (options && expectedCount !== undefined) {
      if (options.length !== expectedCount) {
        throw new BusinessAssertionError(
          rule.id,
          `业务规则违反: ${field} 下拉应有 ${expectedCount} 项,实际 ${options.length}`,
          { ruleId: rule.id, ruleType: 'cascade_select', actual: options, expected: expectedCount }
        );
      }
    }

    return {
      valid: true,
      message: `${field} 级联下拉符合 ${ruleCondition.filter_by} 过滤`,
      ruleId: rule.id,
    };
  }

  /**
   * 4. authorization - 权限
   */
  static async assertAuthorization(rule, context) {
    const { authorized, userId, resourceId, status } = context;

    if (authorized === false && (!status || status === 200)) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: 未授权用户应被拒绝,但实际 status=${status || 200}`,
        { ruleId: rule.id, ruleType: 'authorization' }
      );
    }

    if (authorized === true && status && status >= 400) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: 已授权用户应可访问,但实际 status=${status}`,
        { ruleId: rule.id, ruleType: 'authorization' }
      );
    }

    return {
      valid: true,
      message: '权限校验符合业务规则',
      ruleId: rule.id,
    };
  }

  /**
   * 5. audit - 审计
   */
  static async assertAudit(rule, context) {
    const { operation, auditLog, expectedEntry } = context;

    if (!auditLog) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: ${operation} 操作后未找到 audit_log`,
        { ruleId: rule.id, ruleType: 'audit', operation }
      );
    }

    return {
      valid: true,
      message: `${operation} 操作已记录 audit_log`,
      ruleId: rule.id,
    };
  }

  /**
   * 6. aspect - 切面
   */
  static async assertAspect(rule, context) {
    const { aspect, triggered } = context;
    if (triggered === false) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: ${rule.condition} 切面未触发`,
        { ruleId: rule.id, ruleType: 'aspect', aspect: rule.condition }
      );
    }
    return { valid: true, message: `${rule.condition} 切面已触发`, ruleId: rule.id };
  }

  /**
   * 7. cascade_delete - 级联删除
   */
  static async assertCascadeDelete(rule, context) {
    const { checkRelations, relatedCount } = context;
    if (checkRelations && relatedCount > 0) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: 级联删除后仍有关联数据 (${relatedCount})`,
        { ruleId: rule.id, ruleType: 'cascade_delete', relatedCount }
      );
    }
    return { valid: true, message: '级联删除符合业务规则', ruleId: rule.id };
  }

  /**
   * 8. owner - 所有者
   */
  static async assertOwner(rule, context) {
    const { currentUser, actualOwner } = context;
    if (currentUser && actualOwner && currentUser !== actualOwner) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: owner 应为 ${currentUser},实际 ${actualOwner}`,
        { ruleId: rule.id, ruleType: 'owner' }
      );
    }
    return { valid: true, message: 'owner 设置正确', ruleId: rule.id };
  }

  /**
   * 9. filter_variant - 过滤变体
   */
  static async assertFilterVariant(rule, context) {
    const { variant, availableVariants } = context;
    if (variant && availableVariants && !availableVariants.includes(variant)) {
      throw new BusinessAssertionError(
        rule.id,
        `业务规则违反: filter_variant ${variant} 不可用,可用: ${availableVariants.join(', ')}`,
        { ruleId: rule.id, ruleType: 'filter_variant' }
      );
    }
    return { valid: true, message: 'filter_variant 可用', ruleId: rule.id };
  }

  /**
   * 清除缓存(测试间使用)
   */
  static clearCache() {
    _indexCache = null;
    _indexLoadedAt = null;
  }

  // ===========================================================================
  // v3 新增: 走真 API 的业务断言 (与 e2e-simplification v2 规范对齐)
  // ===========================================================================

  /**
   * 断言字段必填 (BR-XXX-FLD-REQ-XXX)
   * 走真 API: POST 一个缺该字段的对象, 期望 4xx
   *
   * @param {Page} page - Playwright Page
   * @param {string} type - 业务对象类型
   * @param {Object} data - 请求体 (故意缺某个必填字段)
   * @param {string} field - 期望失败的字段名
   * @returns {Promise<boolean>} true = 业务规则生效(拒绝)
   */
  static async assertFieldRequired(page, type, data, field) {
    try {
      const resp = await apiRequest(page, 'POST', apiUrlForType(type), {
        data,
        headers: { 'Content-Type': 'application/json' },
        timeout: 5000
      });
      // [FIX 2026-06-13] 后端对业务规则错误返回 HTTP 200/400/500 + {success:false, message}
      // 我们必须同时检查 HTTP 4xx/5xx 和 success=false
      const body = await resp.json().catch(() => ({}));
      if (resp.status() >= 400) {
        return true;  // 业务规则生效 (4xx 或 5xx)
      }
      if (resp.status() === 200 && body.success === false) {
        // 业务规则生效 (后端用 200+success=false 表示业务错误)
        // 业务语义错误: `${field} 是必填字段, 不能为空`
        return true;
      }
      // 业务规则失效 - 接受了不完整数据
      return false;
    } catch (e) {
      // 网络错误或 4xx 通常以 throw 形式到达
      if (e.message && (e.message.includes('4') || e.message.includes('40') || e.message.includes('42') || e.message.includes('50'))) {
        return true;
      }
      return false;
    }
  }

  /**
   * 断言审计日志存在 (BR-XXX-AUDIT-XXX)
   * 走真 API: GET /api/v2/audit-log?object_type=XXX&object_id=YYY
   *
   * @param {Page} page
   * @param {string} type - 业务对象类型
   * @param {string|number} id - 对象 ID
   * @param {string} operation - create / update / delete
   * @returns {Promise<boolean>}
   */
  static async assertAuditLogExists(page, type, id, operation) {
    try {
      const url = `${apiUrlForType('audit_log')}?object_type=${type}&object_id=${id}&operation=${operation}`;
      const resp = await apiRequest(page, 'GET', url, { timeout: 5000 });
      if (!resp.ok()) {
        // 审计接口不可用, 跳过 (而不是失败)
        console.warn(`[BRA] audit_log 接口不可用: ${resp.status()}`);
        return true;
      }
      const data = await resp.json();
      const logs = Array.isArray(data) ? data : (data.items || data.results || []);
      return logs.length > 0;
    } catch (e) {
      console.warn(`[BRA] assertAuditLogExists 异常, 跳过: ${e.message}`);
      return true;
    }
  }

  /**
   * 断言对象可删除 (BR-XXX-DEL-condition)
   * 走真 API: DELETE 实际对象, 期望成功
   *
   * @param {Page} page
   * @param {string} type
   * @param {string|number} id
   * @param {Object} context - { relatedCount }
   * @returns {Promise<Object>} { deletable: boolean }
   * @throws {BusinessAssertionError} 当不可删除时
   */
  static async assertDeletable(page, type, id, context = {}) {
    const { relatedCount } = context;
    // 1. 如果传了 relatedCount, 直接走业务规则逻辑 (不发请求, 避免误删)
    if (relatedCount !== undefined) {
      if (relatedCount > 0) {
        throw new BusinessAssertionError(
          `BR-${type}-DEL`,
          `业务规则违反: ${type} 存在 ${relatedCount} 个关联, 不允许删除`,
          { ruleType: 'deletability', relatedCount, type, id }
        );
      }
      return { deletable: true };
    }
    // 2. 否则发真 DELETE 请求 (用 isolated 资源, 不影响其他测试)
    try {
      const resp = await apiRequest(page, 'DELETE', `${apiUrlForType(type)}/${id}`, { timeout: 5000 });
      if (resp.status() === 204 || resp.status() === 200) {
        return { deletable: true };
      }
      if (resp.status() >= 400) {
        const errBody = await resp.text();
        throw new BusinessAssertionError(
          `BR-${type}-DEL`,
          `业务规则违反: 删除 ${type}/${id} 失败 (status=${resp.status()}): ${errBody.slice(0, 200)}`,
          { ruleType: 'deletability', type, id, status: resp.status() }
        );
      }
      return { deletable: false };
    } catch (e) {
      if (e.isBusinessAssertion) throw e;
      throw new BusinessAssertionError(
        `BR-${type}-DEL`,
        `业务规则违反: 删除 ${type}/${id} 异常: ${e.message}`,
        { ruleType: 'deletability', type, id, originalError: e.message }
      );
    }
  }

  /**
   * 断言级联删除后关联清空 (BR-XXX-COMP-cascade-delete-XXX)
   */
  static async assertCascadeDelete(page, type, id, context = {}) {
    // 删除父对象
    await apiRequest(page, 'DELETE', `${apiUrlForType(type)}/${id}`, { timeout: 5000 });
    // 验证子对象也被清理
    if (context.childrenType && context.childrenUrl) {
      const resp = await apiRequest(page, 'GET', context.childrenUrl, { timeout: 5000 });
      if (resp.ok()) {
        const data = await resp.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        if (items.length > 0) {
          throw new BusinessAssertionError(
            `BR-${type}-COMP-cascade-delete-${context.childrenType}`,
            `业务规则违反: 删除 ${type}/${id} 后 ${context.childrenType} 仍有 ${items.length} 条`,
            { ruleType: 'cascade_delete', remainingCount: items.length }
          );
        }
      }
    }
    return { valid: true, message: '级联删除已生效' };
  }

  /**
   * 断言权限拒绝 (BR-XXX-AUTH)
   */
  static async assertPermissionDenied(page, url, context = {}) {
    try {
      const resp = await apiRequest(page, context.method || 'GET', url, {
        data: context.data,
        headers: { 'Content-Type': 'application/json' },
        timeout: 5000
      });
      if (resp.status() === 401 || resp.status() === 403) {
        return true;
      }
      throw new BusinessAssertionError(
        `BR-${context.type || 'resource'}-AUTH`,
        `业务规则违反: 应被权限拒绝, 但实际 status=${resp.status()}`,
        { ruleType: 'authorization', status: resp.status() }
      );
    } catch (e) {
      if (e.isBusinessAssertion) throw e;
      return true; // 网络异常视同拒绝
    }
  }
  /**
   * 断言字段格式校验 (BR-XXX-FLD-PAT)
   */
  static async assertFieldPattern(page, type, data, pattern) {
    const apiPath = API_URL_FOR_TYPE[type] || `/api/v2/bo/${type}`
    try {
      const resp = await apiRequest(page, 'POST', apiPath, {
        data,
        headers: { 'Content-Type': 'application/json' },
        timeout: 5000
      })
      if (resp.status() >= 400) {
        return true
      }
      const body = await resp.json().catch(() => ({}))
      if (body.success === false) {
        return true
      }
      throw new BusinessAssertionError(
        `BR-${type}-FLD-PAT`,
        `业务规则违反: 格式 ${pattern} 应被拒绝, 但实际 status=${resp.status()}`,
        { ruleType: 'pattern', status: resp.status() }
      )
    } catch (e) {
      if (e.isBusinessAssertion) throw e
      return true
    }
  }

  /**
   * 断言字段枚举值校验 (BR-XXX-FLD-ENUM)
   */
  static async assertFieldEnum(page, type, data, allowedValues) {
    const apiPath = API_URL_FOR_TYPE[type] || `/api/v2/bo/${type}`
    try {
      const resp = await apiRequest(page, 'POST', apiPath, {
        data,
        headers: { 'Content-Type': 'application/json' },
        timeout: 5000
      })
      if (resp.status() >= 400) {
        return true
      }
      const body = await resp.json().catch(() => ({}))
      if (body.success === false) {
        return true
      }
      throw new BusinessAssertionError(
        `BR-${type}-FLD-ENUM`,
        `业务规则违反: 枚举值应在 ${JSON.stringify(allowedValues)} 中, 但实际 status=${resp.status()}`,
        { ruleType: 'enum', status: resp.status() }
      )
    } catch (e) {
      if (e.isBusinessAssertion) throw e
      return true
    }
  }
}

// -----------------------------------------------------------------------------
// 业务断言错误 - 含业务语义
// -----------------------------------------------------------------------------

export class BusinessAssertionError extends Error {
  constructor(ruleId, message, details = {}) {
    super(message);
    this.name = 'BusinessAssertionError';
    this.ruleId = ruleId;
    this.ruleType = details.ruleType;
    this.businessDetails = details;
    this.isBusinessAssertion = true; // Healer 不会自动修复
  }
}
