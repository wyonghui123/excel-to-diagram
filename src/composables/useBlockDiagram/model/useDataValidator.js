import { DiagramNode, DiagramLink, DiagramContainer, BlockDiagramData } from './useDataModel'

export const ValidationErrorType = {
  MISSING_ID: 'missing_id',
  MISSING_NAME: 'missing_name',
  DUPLICATE_ID: 'duplicate_id',
  INVALID_LINK_SOURCE: 'invalid_link_source',
  INVALID_LINK_TARGET: 'invalid_link_target',
  EMPTY_CONTAINER: 'empty_container',
  INVALID_CONTAINER_NODE: 'invalid_container_node',
  INVALID_PARENT_CONTAINER: 'invalid_parent_container'
}

export class ValidationError {
  constructor(type, message, context = {}) {
    this.type = type
    this.message = message
    this.context = context
    this.timestamp = new Date().toISOString()
  }

  toString() {
    return `[${this.type}] ${this.message}`
  }
}

export class ValidationResult {
  constructor() {
    this.errors = []
    this.warnings = []
  }

  addError(type, message, context = {}) {
    this.errors.push(new ValidationError(type, message, context))
  }

  addWarning(type, message, context = {}) {
    this.warnings.push(new ValidationError(type, message, context))
  }

  isValid() {
    return this.errors.length === 0
  }

  hasWarnings() {
    return this.warnings.length > 0
  }

  getErrors() {
    return this.errors
  }

  getWarnings() {
    return this.warnings
  }

  getAllIssues() {
    return [...this.errors, ...this.warnings]
  }
}

export function useDataValidator() {
  const validateNode = (node) => {
    const result = new ValidationResult()

    if (!node.id && !node.name) {
      result.addError(
        ValidationErrorType.MISSING_ID,
        '节点缺少id和name',
        { node }
      )
    }

    if (!node.name) {
      result.addWarning(
        ValidationErrorType.MISSING_NAME,
        '节点缺少name',
        { node }
      )
    }

    return result
  }

  const validateLink = (link, nodeIds) => {
    const result = new ValidationResult()

    if (!link.source) {
      result.addError(
        ValidationErrorType.INVALID_LINK_SOURCE,
        '连线缺少source',
        { link }
      )
    } else if (!nodeIds.has(link.source)) {
      result.addError(
        ValidationErrorType.INVALID_LINK_SOURCE,
        `连线source "${link.source}" 不存在于节点列表中`,
        { link }
      )
    }

    if (!link.target) {
      result.addError(
        ValidationErrorType.INVALID_LINK_TARGET,
        '连线缺少target',
        { link }
      )
    } else if (!nodeIds.has(link.target)) {
      result.addError(
        ValidationErrorType.INVALID_LINK_TARGET,
        `连线target "${link.target}" 不存在于节点列表中`,
        { link }
      )
    }

    return result
  }

  const validateContainer = (container, nodeIds, containerIds) => {
    const result = new ValidationResult()

    if (!container.id) {
      result.addError(
        ValidationErrorType.MISSING_ID,
        '容器缺少id',
        { container }
      )
    }

    if (!container.nodes || container.nodes.length === 0) {
      result.addWarning(
        ValidationErrorType.EMPTY_CONTAINER,
        `容器 "${container.name || container.id}" 没有包含任何节点`,
        { container }
      )
    } else {
      container.nodes.forEach(nodeId => {
        if (!nodeIds.has(nodeId)) {
          result.addError(
            ValidationErrorType.INVALID_CONTAINER_NODE,
            `容器 "${container.name}" 包含不存在的节点 "${nodeId}"`,
            { container, nodeId }
          )
        }
      })
    }

    if (container.parent && !containerIds.has(container.parent)) {
      result.addError(
        ValidationErrorType.INVALID_PARENT_CONTAINER,
        `容器 "${container.name}" 的父容器 "${container.parent}" 不存在`,
        { container }
      )
    }

    return result
  }

  const validateDiagramData = (data) => {
    const result = new ValidationResult()

    if (!data) {
      result.addError(
        ValidationErrorType.MISSING_ID,
        '数据为空'
      )
      return result
    }

    const nodeIds = new Set()
    const nodeIdCounts = new Map()

    if (data.nodes && Array.isArray(data.nodes)) {
      data.nodes.forEach((node, index) => {
        const nodeResult = validateNode(node)
        result.errors.push(...nodeResult.errors)
        result.warnings.push(...nodeResult.warnings)

        if (node.id) {
          nodeIdCounts.set(node.id, (nodeIdCounts.get(node.id) || 0) + 1)
          nodeIds.add(node.id)
        }
      })

      nodeIdCounts.forEach((count, id) => {
        if (count > 1) {
          result.addError(
            ValidationErrorType.DUPLICATE_ID,
            `节点ID "${id}" 重复出现 ${count} 次`
          )
        }
      })
    }

    if (data.links && Array.isArray(data.links)) {
      data.links.forEach((link, index) => {
        const linkResult = validateLink(link, nodeIds)
        result.errors.push(...linkResult.errors)
        result.warnings.push(...linkResult.warnings)
      })
    }

    const containerIds = new Set()
    if (data.containers && Array.isArray(data.containers)) {
      data.containers.forEach(container => {
        if (container.id) {
          containerIds.add(container.id)
        }
      })

      data.containers.forEach(container => {
        const containerResult = validateContainer(container, nodeIds, containerIds)
        result.errors.push(...containerResult.errors)
        result.warnings.push(...containerResult.warnings)
      })
    }

    return result
  }

  const validateAndFix = (data) => {
    const result = validateDiagramData(data)

    if (result.isValid()) {
      return { data, result }
    }

    const fixedData = { ...data }

    if (fixedData.nodes) {
      fixedData.nodes = fixedData.nodes.filter(node => node.id && node.name)
    }

    if (fixedData.links) {
      const validNodeIds = new Set(fixedData.nodes.map(n => n.id))
      fixedData.links = fixedData.links.filter(link => 
        validNodeIds.has(link.source) && validNodeIds.has(link.target)
      )
    }

    if (fixedData.containers) {
      const validNodeIds = new Set(fixedData.nodes.map(n => n.id))
      fixedData.containers = fixedData.containers.map(container => ({
        ...container,
        nodes: (container.nodes || []).filter(nodeId => validNodeIds.has(nodeId))
      }))
    }

    return { data: fixedData, result }
  }

  return {
    validateNode,
    validateLink,
    validateContainer,
    validateDiagramData,
    validateAndFix,
    ValidationResult,
    ValidationError
  }
}

export function validateRequired(value, fieldName) {
  if (value === undefined || value === null || value === '') {
    return {
      valid: false,
      error: `${fieldName} 是必填项`
    }
  }
  return { valid: true }
}

export function validateType(value, expectedType, fieldName) {
  const actualType = typeof value
  if (actualType !== expectedType) {
    return {
      valid: false,
      error: `${fieldName} 应该是 ${expectedType} 类型，实际是 ${actualType}`
    }
  }
  return { valid: true }
}

export function validateArray(value, fieldName, itemValidator = null) {
  if (!Array.isArray(value)) {
    return {
      valid: false,
      error: `${fieldName} 应该是数组`
    }
  }

  if (itemValidator) {
    const errors = []
    value.forEach((item, index) => {
      const result = itemValidator(item, index)
      if (!result.valid) {
        errors.push({ index, error: result.error })
      }
    })
    if (errors.length > 0) {
      return { valid: false, errors }
    }
  }

  return { valid: true }
}

export function validateRange(value, min, max, fieldName) {
  if (typeof value !== 'number') {
    return {
      valid: false,
      error: `${fieldName} 应该是数字`
    }
  }

  if (value < min || value > max) {
    return {
      valid: false,
      error: `${fieldName} 应该在 ${min} 到 ${max} 之间`
    }
  }

  return { valid: true }
}
