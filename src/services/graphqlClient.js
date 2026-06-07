/**
 * graphqlClient.js - M9 D3 前端 GraphQL 兼容层（最小 POC）
 *
 * 设计原则（关注现有代码 + 减少影响）：
 * - 0 新依赖（不用 Apollo / urql / graphql-request）
 * - 0 改 useMetaList（仅作为可选 callPost 来源）
 * - 100% 兼容 boService API（callPost 接口）
 * - 100% 复用 fetch（无新 HTTP 库）
 * - 走 v1 相同的 CORS + auth（保持一致）
 *
 * 用法（未来 useMetaList 适配）：
 *   import { graphqlClient } from '@/services/graphqlClient'
 *   // 替换 useMetaList.js 中的 callPost 来源
 *   const callPost = graphqlClient.callPost
 *
 * 0 阶段：仅作为"可用库"，不主动改 useMetaList
 */

import { useAuthStore } from '@/stores/authStore'

const GRAPHQL_ENDPOINT = '/graphql'

/**
 * 内部：通用 GraphQL query（支持 query / mutation）
 * @param {string} queryString - GraphQL query 字符串
 * @param {object} variables - variables（v1 POC 暂不支持）
 * @returns {Promise<{success: boolean, data?: any, errors?: any[]}>}
 */
async function _graphqlFetch(queryString, variables = {}) {
  const authStore = useAuthStore()
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  }
  // 复用 v1 认证头（保持一致）
  if (authStore && authStore.getAuthHeaders) {
    Object.assign(headers, authStore.getAuthHeaders())
  }

  const response = await fetch(GRAPHQL_ENDPOINT, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify({ query: queryString, variables }),
  })

  // 401 处理（复用 v1 行为）
  if (response.status === 401) {
    return { success: false, errors: [{ message: 'Unauthorized' }] }
  }

  const result = await response.json()

  if (result.errors && result.errors.length > 0) {
    return { success: false, errors: result.errors }
  }
  return { success: true, data: result.data }
}

/**
 * 兼容 boService.X API
 * 用途：useMetaList 等 composable 可以从 boService.callPost 切到 graphqlClient.callPost
 *
 * 支持 URL 模式：
 *   POST /api/v2/bo/{entity}        → GraphQL create{Entity}(input)
 *   GET  /api/v2/bo/{entity}/{id}  → GraphQL {entity}(id)
 *   GET  /api/v2/bo/{entity}        → GraphQL {entity}s(page, pageSize)
 *
 * 注：v1 兼容层。完整 GraphQL 客户端是 graphqlClient.query() / .mutation()。
 */
async function callPost(url, body) {
  // 仅处理 v2 BO API 路径
  // 1. POST /api/v2/bo/{entity} - create
  const createMatch = url.match(/\/api\/v2\/bo\/(\w+)$/)
  if (createMatch && body && Object.keys(body).length > 0) {
    // POST + body = create
    const entityName = createMatch[1]
    const pascalName = _snakeToPascal(entityName)
    return _graphqlFetch(
      `mutation($input: ${pascalName}Input!) { create${pascalName}(input: $input) { id } }`,
      { input: body }
    )
  }

  // 2. GET /api/v2/bo/{entity}/{id} - getById
  const getByIdMatch = url.match(/\/api\/v2\/bo\/(\w+)\/(\d+)$/)
  if (getByIdMatch) {
    const entityName = getByIdMatch[1]
    const id = parseInt(getByIdMatch[2], 10)
    const singleRoot = _entityNameToRoot(entityName)
    return _graphqlFetch(
      `query($id: Int!) { ${singleRoot}(id: $id) { id name code } }`,
      { id }
    )
  }

  // 3. GET /api/v2/bo/{entity} - list
  const listMatch = url.match(/\/api\/v2\/bo\/(\w+)$/)
  if (listMatch) {
    const entityName = listMatch[1]
    const listRoot = _entityNameToRoot(entityName) + 's'
    return _graphqlFetch(
      `query { ${listRoot}(page: 1, pageSize: 20) { items { id name code } total page pageSize } }`,
      {}
    )
  }

  // 其他 URL 模式暂不处理
  return { success: false, errors: [{ message: `graphqlClient.callPost: URL not supported in POC: ${url}` }] }
}

/**
 * 直接 GraphQL query（高层 API）
 */
async function query(queryString, variables = {}) {
  return _graphqlFetch(queryString, variables)
}

/**
 * 直接 GraphQL mutation（高层 API）
 */
async function mutation(mutationString, variables = {}) {
  return _graphqlFetch(mutationString, variables)
}

// =============================================================================
// 工具函数
// =============================================================================

/**
 * snake_case → PascalCase: user_group → UserGroup
 */
function _snakeToPascal(snakeStr) {
  return snakeStr
    .split('_')
    .map(s => s.charAt(0).toUpperCase() + s.slice(1))
    .join('')
}

/**
 * entity snake_case → GraphQL root field: user_group → userGroup
 */
function _entityNameToRoot(snakeStr) {
  const pascal = _snakeToPascal(snakeStr)
  return pascal.charAt(0).toLowerCase() + pascal.slice(1)
}

// =============================================================================
// 导出
// =============================================================================

export const graphqlClient = {
  query,
  mutation,
  callPost,
  // 暴露配置（便于测试）
  _endpoint: GRAPHQL_ENDPOINT,
  _snakeToPascal,
  _entityNameToRoot,
}

export default graphqlClient
