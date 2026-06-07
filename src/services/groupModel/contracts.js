/**
 * 分组处理契约定义
 * 
 * 设计原则：
 * 1. 明确每个处理环节的输入输出格式
 * 2. 提供验证函数检查数据是否符合契约
 * 3. 在开发模式下自动验证
 */

/**
 * 契约定义
 */
export const Contracts = {
  /**
   * 原始分组数据（来自 architectureProcessor）
   */
  RawGroup: {
    required: ['id', 'type', 'title', 'elementRef'],
    optional: ['parentId', 'children', 'layout'],
    layout: {
      required: [],
      optional: ['direction', 'visible', 'enabled', 'style']
    }
  },
  
  /**
   * 扁平化后的分组数据（来自 groupFlattener）
   */
  FlattenedGroup: {
    required: ['id', 'type', 'title', 'elementRef'],
    optional: ['parentId', 'children', 'layout', '_lifted', '_originalParentId'],
    invariants: [
      'parentId 应该指向最近启用的祖先',
      '如果 _lifted=true，说明是从禁用分组提升的'
    ]
  },
  
  /**
   * Legacy 格式分组（来自 useDiagramData）
   */
  LegacyGroup: {
    required: ['id', 'title', 'direction', 'visible', 'enabled'],
    optional: ['containers', 'children', 'directNodes', 'style'],
    containers: {
      required: ['id', 'name', 'nodes'],
      optional: ['fullTitle', 'direction', 'enabled']
    }
  },
  
  /**
   * Mermaid 容器格式（来自 buildVirtualContainers）
   */
  MermaidContainer: {
    required: ['id', 'name', 'nodes'],
    optional: ['fullTitle', 'direction', 'enabled', '_isDirectNodesContainer'],
    invariants: [
      'nodes 应该是 Mermaid 节点 ID（如 N1, N2）',
      '不是业务对象的 code 或 name'
    ]
  }
}

/**
 * 验证数据是否符合契约
 */
export function validateContract(data, contractName, strict = false) {
  const contract = Contracts[contractName]
  if (!contract) {
    console.error(`[Contract] Unknown contract: ${contractName}`)
    return { valid: false, errors: ['Unknown contract'] }
  }
  
  const errors = []
  
  // 检查必填字段
  if (contract.required) {
    contract.required.forEach(field => {
      if (data[field] === undefined) {
        errors.push(`Missing required field: ${field}`)
      }
    })
  }
  
  // 严格模式下检查未知字段
  if (strict) {
    const allowedFields = [...(contract.required || []), ...(contract.optional || [])]
    Object.keys(data).forEach(field => {
      if (!allowedFields.includes(field) && !field.startsWith('_')) {
        errors.push(`Unknown field: ${field}`)
      }
    })
  }
  
  // 检查嵌套契约
  if (contract.containers && data.containers) {
    data.containers.forEach((container, idx) => {
      const containerErrors = validateContract(container, contract.containers, strict)
      containerErrors.errors.forEach(err => {
        errors.push(`containers[${idx}]: ${err}`)
      })
    })
  }
  
  if (errors.length > 0) {
    console.warn(`[Contract] Validation failed for ${contractName}:`, errors)
  }
  
  return {
    valid: errors.length === 0,
    errors
  }
}

/**
 * 断言数据符合契约（开发模式）
 */
export function assertContract(data, contractName) {
  if (process.env.NODE_ENV === 'production') {
    return
  }
  
  const result = validateContract(data, contractName)
  if (!result.valid) {
    console.error(`[Contract] Assertion failed for ${contractName}`)
    console.error('Data:', data)
    console.error('Errors:', result.errors)
  }
}

/**
 * 转换数据格式（带契约验证）
 */
export function transformWithContract(input, outputContract, transformFn, inputContract = null) {
  // 验证输入
  if (inputContract) {
    assertContract(input, inputContract)
  }
  
  // 执行转换
  const output = transformFn(input)
  
  // 验证输出
  assertContract(output, outputContract)
  
  return output
}

/**
 * 打印契约文档
 */
export function printContractDocs() {
  console.log('=== Group Processing Contracts ===\n')
  
  Object.entries(Contracts).forEach(([name, contract]) => {
    console.log(`\n[${name}]`)
    if (contract.required) {
      console.log(`  Required: ${contract.required.join(', ')}`)
    }
    if (contract.optional) {
      console.log(`  Optional: ${contract.optional.join(', ')}`)
    }
    if (contract.invariants) {
      console.log(`  Invariants:`)
      contract.invariants.forEach(inv => console.log(`    - ${inv}`))
    }
  })
}
