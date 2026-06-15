import { computed } from 'vue'

/**
 * 从 el-tree @check 事件的 checkedNodes 提取 scope 数据
 * 
 * 纯函数，可脱离 Vue 组件进行单元测试。
 * 
 * @param {Array} checkedNodes - el-tree @check 事件的 checkedInfo.checkedNodes
 *   Element Plus Node 对象，原始数据在 node.data 上：
 *   node.data shape: { id: 'd_1', originalId: 1, type: 'domain', ... }
 * @returns {{ boIds: number[], domainIds: number[], subDomainIds: number[], serviceModuleIds: number[] }}
 */
export function treeNodesToScope(checkedNodes) {
  const domainIds = []
  const subDomainIds = []
  const serviceModuleIds = []
  const boIds = []

  for (const node of checkedNodes) {
    // Element Plus Node 对象：originalId 在 node.data 上
    // 原始 data 对象（测试/兼容）：originalId 直接在 node 上
    const id = node.data?.originalId ?? node.originalId ?? node.id
    if (node.type === 'domain') {
      domainIds.push(id)
    } else if (node.type === 'sub_domain') {
      subDomainIds.push(id)
    } else if (node.type === 'service_module') {
      serviceModuleIds.push(id)
    } else if (node.type === 'business_object') {
      boIds.push(id)
    }
  }

  return { boIds, domainIds, subDomainIds, serviceModuleIds }
}

/**
 * 从 scopeIds + treeData 计算 el-tree 的 default-checked-keys
 * 
 * 用于 ObjectScopeSection 的 :default-checked-keys 绑定。
 * scopeIds 格式（来自 useMultiObjectPage）：
 *   { domain: { selected: [], effective: [] }, sub_domain: {...}, ... }
 * 
 * 纯函数，可脱离 Vue 组件进行单元测试。
 * 
 * @param {Array} treeData - 树节点数组
 * @param {Object} scopeIds - 来自 useMultiObjectPage 的 scopeIds reactive 对象
 * @returns {string[]} el-tree node-key 数组
 */
export function scopeToNodeKeys(treeData, scopeIds) {
  if (!treeData?.length || !scopeIds) return []

  const keys = new Set()

  const typeMapping = ['domain', 'sub_domain', 'service_module', 'business_object']

  for (const type of typeMapping) {
    const scopeData = scopeIds[type]
    if (!scopeData) continue

    const ids = (
      Array.isArray(scopeData.selected) && scopeData.selected.length > 0
        ? scopeData.selected
        : (Array.isArray(scopeData.effective) ? scopeData.effective : [])
    )

    if (!ids.length) continue
    _collectKeysByType(treeData, type, ids, keys)
  }

  return [...keys]
}

function _collectKeysByType(nodes, targetType, idList, result) {
  for (const node of nodes) {
    if (node.type === targetType) {
      const id = node.originalId ?? node.id
      if (idList.includes(id)) {
        result.add(node.id)
      }
    }
    if (node.children?.length) {
      _collectKeysByType(node.children, targetType, idList, result)
    }
  }
}

/**
 * 从 el-tree 的 checked node keys 反向提取 relation_codes
 * 
 * 用于 RelationScopeSection 的 @check 处理。
 * 遍历树找到匹配的 module 节点，收集其 relationCodes。
 * 
 * 纯函数，可脱离 Vue 组件进行单元测试。
 * 
 * @param {string[]} nodeKeys - 当前 checked 的 node-key 数组
 * @param {Array} treeData - 关系分类树节点数组
 * @returns {string[]} 去重后的 relation_code 数组
 */
export function nodeKeysToRelationCodes(nodeKeys, treeData) {
  if (!nodeKeys?.length || !treeData?.length) return []

  const nodeKeySet = new Set(nodeKeys)
  const codes = new Set()

  _walkTree(treeData, node => {
    if (nodeKeySet.has(node.id) && node.relationCodes?.length > 0) {
      for (const code of node.relationCodes) {
        codes.add(code)
      }
    }
  })

  return [...codes]
}

/**
 * 从 checked node keys 提取 relation ID 列表
 * 
 * 与 nodeKeysToRelationCodes 不同，relationIds 是关系记录的唯一 ID，
 * 可精确过滤关系列表（relation_code 是类型编码，同一 code 对应多条关系）。
 */
export function nodeKeysToRelationIds(nodeKeys, treeData) {
  if (!nodeKeys?.length || !treeData?.length) return []

  const nodeKeySet = new Set(nodeKeys)
  const ids = new Set()

  _walkTree(treeData, node => {
    if (nodeKeySet.has(node.id) && node.relationIds?.length > 0) {
      for (const id of node.relationIds) {
        ids.add(id)
      }
    }
  })

  return [...ids]
}

/**
 * 从 relation_codes 反向计算 el-tree 的 default-checked-keys
 *
 * 用于 RelationScopeSection 的 :default-checked-keys 绑定。
 * 遍历树找到 relationCodes 完全匹配的 module 节点，收集其 node key。
 * 如果某个 module 节点的所有 relationCodes 都在目标列表中，则该节点被选中。
 *
 * 纯函数，可脱离 Vue 组件进行单元测试。
 *
 * @param {string[]} relationCodes - 当前选中的 relation_code 数组
 * @param {Array} treeData - 关系分类树节点数组
 * @returns {string[]} el-tree node-key 数组（叶子 module 节点）
 */
export function relationCodesToNodeKeys(relationCodes, treeData) {
  if (!relationCodes?.length || !treeData?.length) return []

  const codeSet = new Set(relationCodes)
  const keys = new Set()

  _walkTree(treeData, node => {
    if (node.relationCodes?.length > 0) {
      const allMatch = node.relationCodes.every(c => codeSet.has(c))
      if (allMatch) {
        keys.add(node.id)
      }
    }
  })

  return [...keys]
}

/**
 * 从 relationIds (唯一关系记录 ID) 反向计算 el-tree 的 default-checked-keys
 *
 * v39.4: 修复从图表页返回时关系范围选择状态"漂移"问题。
 * 根因: relationCodes 是类型编码 (如 "CONTAINS")，同一 code 可出现在不同 scope 的模块节点中。
 *   还原时 relationCodesToNodeKeys 会匹配到"范围外"的节点（其 codes 也存在于保存集合中），
 *   导致 el-tree setCheckedKeys 包含父节点后级联勾选所有子节点，状态错位。
 * 修复: 使用 relationIds (唯一 ID) 精确匹配叶子 module 节点，避免跨 scope 误匹配。
 *
 * @param {Array<number|string>} relationIds - 当前选中的关系记录唯一 ID 数组
 * @param {Array} treeData - 关系分类树节点数组
 * @returns {string[]} el-tree node-key 数组（仅叶子 module 节点）
 */
export function relationIdsToNodeKeys(relationIds, treeData) {
  if (!relationIds?.length || !treeData?.length) return []

  const idSet = new Set(relationIds.map(String))
  const keys = new Set()

  _walkTree(treeData, node => {
    // 只匹配叶子 module 节点（有 relationIds 且无 children）
    if (node.relationIds?.length > 0 && (!node.children || node.children.length === 0)) {
      const allMatch = node.relationIds.every(id => idSet.has(String(id)))
      if (allMatch) {
        keys.add(node.id)
      }
    }
  })

  return [...keys]
}

function _walkTree(nodes, visitor) {
  for (const node of nodes) {
    visitor(node)
    if (node.children?.length) {
      _walkTree(node.children, visitor)
    }
  }
}

/**
 * Vue composable：从 scopeIds 计算 el-tree 的 default-checked-keys
 *
 * @param {Object} options
 * @param {import('vue').ComputedRef<Array>} options.treeData - ObjectScopeSection 的 treeData
 * @param {import('vue').ComputedRef<Object>} options.scopeIds - useMultiObjectPage 的 scopeIds
 * @returns {{ objectCheckedNodeKeys: ComputedRef<string[]>, relationCheckedNodeKeys: ComputedRef<string[]> }}
 */
export function useScopeTreeState(options) {
  const objectCheckedNodeKeys = computed(() => {
    return scopeToNodeKeys(options.treeData?.value, options.scopeIds?.value)
  })

  const relationCheckedNodeKeys = computed(() => {
    const codes = options.scopeIds?.value?.relationExtra?.relationCodes || []
    return relationCodesToNodeKeys(codes, options.classifierTreeData?.value || [])
  })

  return {
    objectCheckedNodeKeys,
    relationCheckedNodeKeys
  }
}
