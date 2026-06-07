/**
 * 字段提取工具函数
 * 用于从Excel行数据中提取各类字段
 *
 * 设计：大小写不敏感、支持中英文字段名、null 归一为空字符串
 */

/**
 * 判断 key 是否匹配任一模式（大小写不敏感）
 */
function keyMatches(key, patterns) {
  const lower = key.toLowerCase()
  return patterns.some(p => lower.includes(p.toLowerCase()) || key.includes(p))
}

/**
 * 安全取值：null/undefined → ''
 */
function val(v) {
  return v == null ? '' : v
}

/**
 * 从对象中提取备注相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { annotationCategory, annotationContent }
 */
export function extractAnnotationFields(item) {
  const keys = Object.keys(item)
  let annotationCategory = '', annotationContent = ''

  const validCategories = ['important', 'warning', 'info', 'tip']

  for (const key of keys) {
    const lower = key.toLowerCase()
    const value = item[key]

    // 分类字段：包含 category/分类，且不与 content/内容 重叠
    const isCategoryKey =
      (lower.includes('category') || key.includes('分类')) &&
      !(lower.includes('content') || key.includes('内容'))

    if (isCategoryKey) {
      if (value && validCategories.includes(String(value).toLowerCase())) {
        annotationCategory = String(value).toLowerCase()
      }
      continue
    }

    // 内容字段：包含 content/内容/备注/note/annotation
    const isContentKey =
      lower.includes('content') ||
      lower === 'note' ||
      lower.includes('note') ||
      key.includes('备注内容') ||
      key.includes('内容') ||
      (key.includes('备注') && !key.includes('分类')) ||
      lower.includes('annotation')

    if (isContentKey) {
      annotationContent = val(value)
    }
  }

  if (!annotationContent) {
    for (const key of keys) {
      const lower = key.toLowerCase()
      if (lower.includes('content') || key.includes('内容')) {
        const v = item[key]
        if (v && typeof v === 'string' && v.trim()) {
          annotationContent = v
          break
        }
      }
    }
  }

  return { annotationCategory, annotationContent }
}

/**
 * 从对象中提取服务模块相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { smCode, smName, domain, subDomain }
 */
export function extractServiceModuleFields(item) {
  const keys = Object.keys(item)
  let smCode = '', smName = '', domain = '', subDomain = ''

  for (const key of keys) {
    const lower = key.toLowerCase()
    const value = item[key]
    const isSub = lower.includes('sub') || key.includes('子')

    // 服务模块编码（不包含"业务"）
    if (
      (key.includes('服务模块编码') ||
        lower.includes('servicemodulecode') ||
        lower.includes('sm_code')) &&
      !key.includes('业务')
    ) {
      smCode = val(value)
      continue
    }

    // 服务模块名称（不包含"编码"）
    if (
      (key.includes('服务模块名称') ||
        lower.includes('servicemodulename') ||
        lower.includes('sm_name')) &&
      !key.includes('编码')
    ) {
      smName = val(value)
      continue
    }

    // 子领域（先于领域匹配，避免被"领域"误捕获）
    if (
      isSub &&
      (key.includes('子领域') || key.includes('领域') || lower.includes('domain'))
    ) {
      subDomain = val(value)
      continue
    }

    // 领域
    if (key.includes('领域') || lower === 'domain' || lower.endsWith('domain')) {
      domain = val(value)
    }
  }

  return { smCode, smName, domain, subDomain }
}

/**
 * 从对象中提取业务对象相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { boCode, boName, domain, subDomain, serviceModule }
 */
export function extractBusinessObjectFields(item) {
  const keys = Object.keys(item)
  let boCode = '', boName = '', domain = '', subDomain = '', serviceModule = ''

  for (const key of keys) {
    const lower = key.toLowerCase()
    const value = item[key]
    const isSub = lower.includes('sub') || key.includes('子')

    // 业务对象编码
    if (
      key.includes('业务对象编码') ||
      lower.includes('businessobjectcode') ||
      lower.includes('bo_code')
    ) {
      boCode = val(value)
      continue
    }

    // 业务对象名称
    if (
      key.includes('业务对象名称') ||
      lower.includes('businessobjectname') ||
      lower.includes('bo_name')
    ) {
      boName = val(value)
      continue
    }

    // 子领域（先于领域匹配）
    if (
      isSub &&
      (key.includes('子领域') || key.includes('领域') || lower.includes('domain'))
    ) {
      subDomain = val(value)
      continue
    }

    // 领域
    if (key.includes('领域') || lower === 'domain' || lower.endsWith('domain')) {
      domain = val(value)
      continue
    }

    // 服务模块
    if (
      key.includes('服务模块') ||
      lower.includes('servicemodule') ||
      lower === 'sm' ||
      lower.endsWith('sm') ||
      lower.includes('sm_')
    ) {
      serviceModule = val(value)
    }
  }

  return { boCode, boName, domain, subDomain, serviceModule }
}

/**
 * 从对象中提取关系相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { sourceCode, targetCode, relationCode, relationType, description }
 */
export function extractRelationshipFields(item) {
  const keys = Object.keys(item)
  let sourceCode = '', targetCode = '', relationCode = '', relationType = '', description = ''

  for (const key of keys) {
    const lower = key.toLowerCase()
    const value = item[key]

    // 源业务对象编码：包含 source/源业务对象（但不包含 target/目标）
    if (
      (key.includes('源业务对象') ||
        lower.includes('sourcebusinessobject') ||
        lower.includes('source')) &&
      !lower.includes('target') &&
      !key.includes('目标')
    ) {
      // 排除 name/display 等非编码字段
      if (!lower.includes('name') && !lower.includes('display') && !key.includes('名称')) {
        sourceCode = val(value)
        continue
      }
    }

    // 目标业务对象编码
    if (
      (key.includes('目标业务对象') ||
        lower.includes('targetbusinessobject') ||
        lower.includes('target')) &&
      !lower.includes('source') &&
      !key.includes('源')
    ) {
      if (!lower.includes('name') && !lower.includes('display') && !key.includes('名称')) {
        targetCode = val(value)
        continue
      }
    }

    // 关系编码
    if (
      key.includes('关系编码') ||
      lower.includes('relationshipcode') ||
      lower.includes('relation_code')
    ) {
      relationCode = val(value)
      continue
    }

    // 关系类型
    if (
      key.includes('关系类型') ||
      lower.includes('relationshiptype') ||
      lower.includes('relation_type')
    ) {
      relationType = val(value)
      continue
    }

    // 描述/说明
    if (
      key.includes('描述') ||
      key.includes('说明') ||
      lower.includes('description') ||
      lower === 'desc' ||
      lower.endsWith('desc')
    ) {
      description = val(value)
    }
  }

  return { sourceCode, targetCode, relationCode, relationType, description }
}
