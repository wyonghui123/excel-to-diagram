/**
 * 枚举数据查找器 - 统一数据源 (v3.18-r3)
 * 
 * 解决的问题:
 * - 4 个 spec 文件重复定义 findSystemEnum/findEnumValues/createTestEnumType
 * - V1 API 依赖 (可能 410 sunset)
 * - business enum id=null 导致详情页路由失败
 * - 数据过滤不精确 (E09/E10 未过滤 is_system)
 * 
 * 策略:
 * - 统一用 V2 BO API (稳定, 未 sunset)
 * - system enum 优先用 ActionType (id=action_type, 始终存在)
 * - business enum 优先找有 id 的, 找不到则创建
 * - enum_value 查找支持 is_system 精确过滤
 */

// ============================================================
// 常量
// ============================================================

export const SYSTEM_ENUM_IDS = {
  ACTION_TYPE: 'action_type',
  CHANGE_TYPE: 'change_type',
  DATA_CATEGORY: 'data_category'
}

// ============================================================
// enum_type 查找
// ============================================================

/**
 * 通过 V2 BO 查找 system enum (有有效 id)
 * 默认找 ActionType, 如果不存在则找第一个 category=system 的
 * 
 * @param {Page} page
 * @param {string} preferredId - 优先查找的 id (默认 'action_type')
 * @returns {Promise<{id: string, name: string, category: string, mutability: string}|null>}
 */
export async function findSystemEnum(page, preferredId = 'action_type') {
  // 优先查指定 id
  const resp = await page.request.get(`/api/v2/bo/enum_type?id=${preferredId}&page_size=5`)
  if (resp.ok()) {
    const body = await resp.json()
    const items = body?.data?.items || []
    const found = items.find(i => i.category === 'system' && i.id)
    if (found) {
      return {
        id: found.id,
        name: found.name,
        category: found.category,
        mutability: found.mutability
      }
    }
  }
  
  // fallback: 查所有 system enum
  const resp2 = await page.request.get('/api/v2/bo/enum_type?category=system&page_size=50')
  if (!resp2.ok()) return null
  const body2 = await resp2.json()
  const items2 = body2?.data?.items || []
  const found2 = items2.find(i => i.id)
  if (!found2) return null
  return {
    id: found2.id,
    name: found2.name,
    category: found2.category,
    mutability: found2.mutability
  }
}

/**
 * 通过 V2 BO 查找 locked enum
 * 
 * @param {Page} page
 * @returns {Promise<{id: string, name: string, category: string, mutability: string}|null>}
 */
export async function findLockedEnum(page) {
  const resp = await page.request.get('/api/v2/bo/enum_type?mutability=locked&page_size=50')
  if (!resp.ok()) return null
  const body = await resp.json()
  const items = body?.data?.items || []
  const found = items.find(i => i.id)
  if (!found) return null
  return {
    id: found.id,
    name: found.name,
    category: found.category,
    mutability: found.mutability
  }
}

/**
 * 通过 V2 BO 查找 business enum with valid id
 * business enum 在列表中 id 通常为 null; 需要找有 id 的
 * 
 * @param {Page} page
 * @returns {Promise<{id: string, name: string, category: string, mutability: string}|null>}
 */
export async function findBusinessEnumWithId(page) {
  const resp = await page.request.get('/api/v2/bo/enum_type?category=business&page_size=100')
  if (!resp.ok()) return null
  const body = await resp.json()
  const items = body?.data?.items || []
  const found = items.find(i => i.category === 'business' && i.id)
  if (found) {
    return {
      id: found.id,
      name: found.name,
      category: found.category,
      mutability: found.mutability
    }
  }
  return null
}

/**
 * 创建一个可用于编辑测试的 enum_type
 * V2 BO create 返回数字 id, 但可能不持久化
 * 
 * @param {Page} page
 * @returns {Promise<{id: string, name: string, category: string, mutability: string, cleanup: Function}|null>}
 */
export async function createTestEnumType(page) {
  const ts = Date.now().toString(36).toUpperCase()
  const name = `EVT_${ts}`
  
  const r = await page.request.post('/api/v2/bo/enum_type', {
    data: {
      name: name,
      category: 'business',
      mutability: 'fullEditable',
      description: `E2E test type ${name}`
    }
  })
  
  if (r.ok()) {
    const body = await r.json()
    const id = body?.data?.id
    if (id) {
      // 验证 id 可用: 尝试 V2 BO single
      const check = await page.request.get(`/api/v2/bo/enum_type/${id}`)
      if (check.ok()) {
        return {
          id,
          name,
          category: 'business',
          mutability: 'fullEditable',
          cleanup: async () => {
            await page.request.delete(`/api/v2/bo/enum_type/${id}`).catch(() => {})
          }
        }
      }
    }
  }
  
  // Fallback: 用 ActionType (id=action_type, system enum)
  return {
    id: 'action_type',
    name: 'ActionType',
    category: 'system',
    mutability: 'locked',
    cleanup: async () => {} // 不清理系统枚举
  }
}

// ============================================================
// enum_value 查找
// ============================================================

/**
 * 通过 V2 BO 查找 enum_values
 * 支持 is_system 精确过滤
 * 
 * @param {Page} page
 * @param {Object} filters - 过滤条件
 *   - enum_type_id: 按类型过滤
 *   - is_system: 按 is_system 过滤 (true/false/1/0)
 *   - page_size: 每页数量 (默认 50)
 * @returns {Promise<Array>}
 */
export async function findEnumValues(page, filters = {}) {
  const params = new URLSearchParams({ page_size: '50' })
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null) {
      params.set(k, String(v))
    }
  }
  const r = await page.request.get(`/api/v2/bo/enum_value?${params}`)
  if (!r.ok()) return []
  const body = await r.json()
  return body?.data?.items || body?.data?.data || []
}

/**
 * 查找第一个 system enum_value (is_system=true)
 * 用于 DEC-2 测试 (E09/E10)
 * 
 * @param {Page} page
 * @returns {Promise<Object|null>}
 */
export async function findSystemEnumValue(page) {
  const values = await findEnumValues(page, { is_system: 1 })
  return values[0] || null
}

/**
 * 查找第一个 non-system enum_value (is_system=false)
 * 用于测试可编辑/可删除的场景
 * 
 * @param {Page} page
 * @returns {Promise<Object|null>}
 */
export async function findNonSystemEnumValue(page) {
  const values = await findEnumValues(page, { is_system: 0 })
  return values[0] || null
}

// ============================================================
// enum_value CRUD
// ============================================================

/**
 * 通过 V2 BO 创建 enum_value
 * 
 * @param {Page} page
 * @param {string} enumTypeId
 * @param {string} code
 * @param {string} name
 * @returns {Promise<{id: string, code: string, name: string}|null>}
 */
export async function createEnumValue(page, enumTypeId, code, name) {
  const r = await page.request.post('/api/v2/bo/enum_value', {
    data: {
      enum_type_id: enumTypeId,
      code: code,
      name: name,
      is_active: true
    }
  })
  if (r.ok()) {
    const body = await r.json()
    return { id: body?.data?.id, code, name }
  }
  return null
}

/**
 * 通过 V2 BO 删除 enum_value
 * 
 * @param {Page} page
 * @param {string} valueId
 */
export async function deleteEnumValue(page, valueId) {
  if (!valueId) return
  await page.request.delete(`/api/v2/bo/enum_value/${valueId}`).catch(() => {})
}
