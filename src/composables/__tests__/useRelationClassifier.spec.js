import { describe, it, expect, beforeEach } from 'vitest'
import { useRelationClassifier } from '../useRelationClassifier'
import { ref } from 'vue'

const CategoryType = {
  CROSS_DOMAIN: 'cross-domain',
  SAME_DOMAIN_CROSS_SUBDOMAIN: 'same-domain-cross-subdomain',
  SAME_SUBDOMAIN_CROSS_MODULE: 'same-subdomain-cross-module',
  SAME_MODULE: 'same-module'
}

const ScopeType = {
  INTERNAL: 'internal',
  CROSS_BOUNDARY: 'cross-boundary',
  EXTERNAL: 'external'
}

const mockBusinessObjects = [
  { id: 1, code: 'BO01', name: '库存管理', domain: '供应链云', domainId: 1, subDomain: '采购供应', subDomainId: 11, serviceModule: '库存管理模块', serviceModuleId: 111, serviceModuleName: '库存管理模块' },
  { id: 2, code: 'BO02', name: '采购管理', domain: '供应链云', domainId: 1, subDomain: '采购供应', subDomainId: 11, serviceModule: '采购管理模块', serviceModuleId: 112, serviceModuleName: '采购管理模块' },
  { id: 3, code: 'BO03', name: '销售管理', domain: '供应链云', domainId: 1, subDomain: '销售服务', subDomainId: 12, serviceModule: '销售管理模块', serviceModuleId: 121, serviceModuleName: '销售管理模块' },
  { id: 4, code: 'BO04', name: '供应商管理', domain: '采购云', domainId: 2, subDomain: '供应商管理', subDomainId: 21, serviceModule: '供应商管理模块', serviceModuleId: 211, serviceModuleName: '供应商管理模块' },
  { id: 5, code: 'BO05', name: '财务核算', domain: '财务云', domainId: 3, subDomain: '财务管理', subDomainId: 31, serviceModule: '财务核算模块', serviceModuleId: 311, serviceModuleName: '财务核算模块' },
  { id: 6, code: 'BO06', name: '应收账款', domain: '财务云', domainId: 3, subDomain: '财务管理', subDomainId: 31, serviceModule: '应收账款模块', serviceModuleId: 312, serviceModuleName: '应收账款模块' }
]

const DOMAIN_IDS = {
  SUPPLY_CHAIN: 1,
  PROCUREMENT: 2,
  FINANCE: 3
}

const SUB_DOMAIN_IDS = {
  PROCUREMENT_SUPPLY: 11,
  SALES_SERVICE: 12,
  SUPPLIER_MGMT: 21,
  FINANCE_MGMT: 31
}

const SERVICE_MODULE_IDS = {
  INVENTORY: 111,
  PURCHASING: 112,
  SALES: 121,
  SUPPLIER: 211,
  ACCOUNTING: 311,
  RECEIVABLES: 312
}

const BUSINESS_OBJECT_IDS = {
  INVENTORY_MGMT: 1,
  PURCHASE_MGMT: 2,
  SALES_MGMT: 3,
  SUPPLIER_MGMT: 4,
  FINANCE_ACCT: 5,
  RECEIVABLES: 6
}

const mockRelationships = [
  { sourceBoId: 1, targetBoId: 2, sourceCode: 'BO01', targetCode: 'BO02', relationCode: 'REL01' },
  { sourceBoId: 1, targetBoId: 3, sourceCode: 'BO01', targetCode: 'BO03', relationCode: 'REL02' },
  { sourceBoId: 2, targetBoId: 4, sourceCode: 'BO02', targetCode: 'BO04', relationCode: 'REL03' },
  { sourceBoId: 3, targetBoId: 5, sourceCode: 'BO03', targetCode: 'BO05', relationCode: 'REL04' },
  { sourceBoId: 1, targetBoId: 4, sourceCode: 'BO01', targetCode: 'BO04', relationCode: 'REL05' },
  { sourceBoId: 5, targetBoId: 6, sourceCode: 'BO05', targetCode: 'BO06', relationCode: 'REL06' }
]

function createComposable(domainIds, subDomainIds, serviceModuleIds, businessObjectIds, relationships, businessObjects) {
  const domainIdsRef = ref(domainIds || [])
  const subDomainIdsRef = ref(subDomainIds || [])
  const serviceModuleIdsRef = ref(serviceModuleIds || [])
  const businessObjectIdsRef = ref(businessObjectIds || [])
  const relRef = ref(relationships)
  const boRef = ref(businessObjects)
  return useRelationClassifier(domainIdsRef, subDomainIdsRef, serviceModuleIdsRef, businessObjectIdsRef, relRef, boRef)
}

describe('useRelationClassifier', () => {

  describe('basic tree structure', () => {
    it('should return tree with all relations when no domains selected', () => {
      const { treeData } = createComposable([], [], [], [], mockRelationships, mockBusinessObjects)
      expect(treeData.value.length).toBeGreaterThan(0)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)
      expect(totalCount).toBe(mockRelationships.length)
    })

    it('should return empty tree when no relationships', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], [], mockBusinessObjects)
      expect(treeData.value).toEqual([])
    })

    it('should have internal scope node for internal relations', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      expect(internalNode).toBeDefined()
      expect(internalNode.name).toBe('范围内')
    })

    it('should have cross-boundary scope node when there are cross-boundary relations', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)
      expect(crossBoundaryNode).toBeDefined()
      expect(crossBoundaryNode.name).toBe('范围内与外部')
    })

    it('should not have cross-boundary node when all related BOs are in selected domains', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)
      expect(crossBoundaryNode).toBeUndefined()
    })
  })

  describe('classification categories', () => {
    it('should have correct category types in internal scope', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      expect(internalNode).toBeDefined()

      const categoryIds = internalNode.children.map(c => c.id)
      expect(categoryIds).toContain(`${ScopeType.INTERNAL}-${CategoryType.CROSS_DOMAIN}`)
      expect(categoryIds).toContain(`${ScopeType.INTERNAL}-${CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN}`)
      expect(categoryIds).toContain(`${ScopeType.INTERNAL}-${CategoryType.SAME_SUBDOMAIN_CROSS_MODULE}`)
    })

    it('should have correct category names', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const categoryNames = internalNode.children.map(c => c.name)

      expect(categoryNames).toContain('跨领域')
      expect(categoryNames).toContain('同领域跨子领域')
      expect(categoryNames).toContain('同子领域跨服务模块')
    })

    it('should only show categories with count > 0', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)

      internalNode.children.forEach(child => {
        expect(child.count).toBeGreaterThan(0)
      })
    })
  })

  describe('cross-domain relations', () => {
    it('should classify relations across different domains as cross-domain', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const crossDomainNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.CROSS_DOMAIN}`)

      expect(crossDomainNode).toBeDefined()
      expect(crossDomainNode.count).toBeGreaterThan(0)
    })

    it('should build domain pair level under cross-domain', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const crossDomainNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.CROSS_DOMAIN}`)

      expect(crossDomainNode.children.length).toBeGreaterThan(0)
      crossDomainNode.children.forEach(domainPair => {
        expect(domainPair.level).toBe('domain')
        expect(domainPair.name).toContain('-')
      })
    })

    it('should build subdomain level under domain pair', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const crossDomainNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.CROSS_DOMAIN}`)

      if (crossDomainNode.children.length > 0) {
        const domainPair = crossDomainNode.children[0]
        expect(domainPair.children.length).toBeGreaterThan(0)
        domainPair.children.forEach(subDomainPair => {
          expect(subDomainPair.level).toBe('subDomain')
        })
      }
    })

    it('should build module level under subdomain pair', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const crossDomainNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.CROSS_DOMAIN}`)

      if (crossDomainNode.children.length > 0) {
        const domainPair = crossDomainNode.children[0]
        if (domainPair.children.length > 0) {
          const subDomainPair = domainPair.children[0]
          expect(subDomainPair.children.length).toBeGreaterThan(0)
          subDomainPair.children.forEach(modulePair => {
            expect(modulePair.level).toBe('module')
            expect(modulePair.relationCodes.length).toBeGreaterThan(0)
          })
        }
      }
    })
  })

  describe('same-domain relations', () => {
    it('should classify relations within same subdomain but different modules', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const sameSubdomainCrossModuleNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.SAME_SUBDOMAIN_CROSS_MODULE}`)

      expect(sameSubdomainCrossModuleNode).toBeDefined()
      expect(sameSubdomainCrossModuleNode.count).toBeGreaterThan(0)
    })

    it('should classify relations within same domain but different subdomains', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const sameDomainNode = internalNode.children.find(c => c.id === `${ScopeType.INTERNAL}-${CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN}`)

      expect(sameDomainNode).toBeDefined()
    })
  })

  describe('cross-boundary scope relations', () => {
    it('should have cross-boundary scope when relations involve objects outside selected domains', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)

      expect(crossBoundaryNode).toBeDefined()
      expect(crossBoundaryNode.count).toBeGreaterThan(0)
    })

    it('should classify cross-boundary relations correctly', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)

      const categoryIds = crossBoundaryNode.children.map(c => c.id)
      expect(categoryIds).toContain(`${ScopeType.CROSS_BOUNDARY}-${CategoryType.CROSS_DOMAIN}`)
    })

    it('should group cross-boundary relations by external domain', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)
      const crossDomainNode = crossBoundaryNode.children.find(c => c.id === `${ScopeType.CROSS_BOUNDARY}-${CategoryType.CROSS_DOMAIN}`)

      expect(crossDomainNode.children.length).toBeGreaterThan(0)
      const externalDomainNames = crossDomainNode.children.map(d => d.name)
      expect(externalDomainNames.some(name => name.includes('采购云') || name.includes('财务云'))).toBe(true)
    })
  })

  describe('data validation and filtering', () => {
    it('should filter out business objects with null or unknown domain', () => {
      const bosWithNullDomain = [
        ...mockBusinessObjects,
        { id: 100, code: 'BO100', name: '未知对象', domain: null, domainId: null, subDomain: '未知', subDomainId: null, serviceModule: '未知模块', serviceModuleId: null, serviceModuleName: '未知模块' },
        { id: 101, code: 'BO101', name: '未知对象2', domain: '未知领域', domainId: 999, subDomain: '未知', subDomainId: null, serviceModule: '未知模块', serviceModuleId: null, serviceModuleName: '未知模块' }
      ]

      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, bosWithNullDomain)
      expect(treeData.value.length).toBeGreaterThan(0)
    })

    it('should filter out duplicate relations by relationCode', () => {
      const duplicateRels = [
        { sourceBoId: 1, targetBoId: 2, sourceCode: 'BO01', targetCode: 'BO02', relationCode: 'REL_DUP' },
        { sourceBoId: 1, targetBoId: 2, sourceCode: 'BO01', targetCode: 'BO02', relationCode: 'REL_DUP' },
        { sourceBoId: 1, targetBoId: 3, sourceCode: 'BO01', targetCode: 'BO03', relationCode: 'REL_DIFF' }
      ]

      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], duplicateRels, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      const totalCount = internalNode.count

      expect(totalCount).toBe(2)
    })

    it('should filter out self-loop relations', () => {
      const relsWithSelfLoop = [
        { sourceBoId: 1, targetBoId: 1, sourceCode: 'BO01', targetCode: 'BO01', relationCode: 'REL_SELF' },
        { sourceBoId: 1, targetBoId: 2, sourceCode: 'BO01', targetCode: 'BO02', relationCode: 'REL_NORMAL' }
      ]

      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], relsWithSelfLoop, mockBusinessObjects)
      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)

      const allRelationCodes = []
      function collectCodes(nodes) {
        nodes.forEach(node => {
          if (node.relationCodes) allRelationCodes.push(...node.relationCodes)
          if (node.children) collectCodes(node.children)
        })
      }
      collectCodes(internalNode.children || [])

      expect(allRelationCodes).not.toContain('REL_SELF')
    })

    it('should handle empty businessObjects array', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, [])
      expect(treeData.value).toEqual([])
    })
  })

  describe('selection management', () => {
    it('should toggle node selection on', () => {
      const { selectedScopeIds, toggleNodeSelection } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      toggleNodeSelection('test-node-id')
      expect(selectedScopeIds.value).toContain('test-node-id')
    })

    it('should toggle node selection off', () => {
      const { selectedScopeIds, toggleNodeSelection } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      toggleNodeSelection('test-node-id')
      toggleNodeSelection('test-node-id')
      expect(selectedScopeIds.value).not.toContain('test-node-id')
    })

    it('should use array for selectedScopeIds', () => {
      const { selectedScopeIds } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      expect(Array.isArray(selectedScopeIds.value)).toBe(true)
    })
  })

  describe('expand/collapse', () => {
    it('should toggle node expand on', () => {
      const { expandedNodeIds, toggleNodeExpand } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      toggleNodeExpand('test-node-id')
      expect(expandedNodeIds.value).toContain('test-node-id')
    })

    it('should toggle node expand off', () => {
      const { expandedNodeIds, toggleNodeExpand } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      toggleNodeExpand('test-node-id')
      toggleNodeExpand('test-node-id')
      expect(expandedNodeIds.value).not.toContain('test-node-id')
    })

    it('should expand all nodes with children', () => {
      const { treeData, expandedNodeIds, expandAll } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      expandAll()

      function countNodesWithChildren(nodes) {
        let count = 0
        nodes.forEach(node => {
          if (node.children && node.children.length > 0) {
            count++
            count += countNodesWithChildren(node.children)
          }
        })
        return count
      }

      const expectedCount = countNodesWithChildren(treeData.value)
      expect(expandedNodeIds.value.length).toBe(expectedCount)
    })

    it('should collapse all nodes', () => {
      const { expandedNodeIds, expandAll, collapseAll } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      expandAll()
      expect(expandedNodeIds.value.length).toBeGreaterThan(0)

      collapseAll()
      expect(expandedNodeIds.value.length).toBe(0)
    })

    it('should handle expandAll with empty tree', () => {
      const { expandedNodeIds, expandAll } = createComposable([], [], [], [], mockRelationships, mockBusinessObjects)
      expect(() => expandAll()).not.toThrow()
    })

    it('should handle collapseAll with empty tree', () => {
      const { expandedNodeIds, collapseAll } = createComposable([], [], [], [], mockRelationships, mockBusinessObjects)
      expect(() => collapseAll()).not.toThrow()
    })
  })

  describe('getSelectedRelationCodes', () => {
    it('should return empty array when nothing selected', () => {
      const { getSelectedRelationCodes } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      expect(getSelectedRelationCodes()).toEqual([])
    })

    it('should return relation codes for selected leaf node', () => {
      const { treeData, selectedScopeIds, getSelectedRelationCodes } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      function findLeafNode(nodes) {
        for (const node of nodes) {
          if (node.relationCodes && node.relationCodes.length > 0) {
            return node
          }
          if (node.children) {
            const found = findLeafNode(node.children)
            if (found) return found
          }
        }
        return null
      }

      const leafNode = findLeafNode(treeData.value)
      if (leafNode) {
        selectedScopeIds.value = [leafNode.id]
        const codes = getSelectedRelationCodes()
        expect(codes.length).toBe(leafNode.relationCodes.length)
      }
    })

    it('should collect all relation codes from descendants when parent selected', () => {
      const { treeData, selectedScopeIds, getSelectedRelationCodes } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      const internalNode = treeData.value.find(n => n.id === ScopeType.INTERNAL)
      if (internalNode) {
        selectedScopeIds.value = [internalNode.id]
        const codes = getSelectedRelationCodes()
        expect(codes.length).toBe(internalNode.count)
      }
    })
  })

  describe('count accuracy', () => {
    it('should have accurate count at each level', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      function verifyCounts(node) {
        if (node.children && node.children.length > 0) {
          const childrenSum = node.children.reduce((sum, child) => {
            return sum + verifyCounts(child)
          }, 0)
          expect(node.count).toBe(childrenSum)
          return node.count
        }
        return node.count || 0
      }

      treeData.value.forEach(rootNode => {
        verifyCounts(rootNode)
      })
    })

    it('should have correct relationCodes at leaf nodes', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)

      function checkLeafNodes(node) {
        if (node.children && node.children.length > 0) {
          node.children.forEach(checkLeafNodes)
        } else {
          if (node.relationCodes) {
            expect(node.relationCodes.length).toBe(node.count)
          }
        }
      }

      treeData.value.forEach(rootNode => {
        checkLeafNodes(rootNode)
      })
    })
  })

  describe('multi-granularity filtering', () => {
    it('should filter by domain when only domainIds provided', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)
      expect(totalCount).toBeGreaterThan(0)
    })

    it('should filter by subDomain when subDomainIds provided', () => {
      const { treeData } = createComposable([], [SUB_DOMAIN_IDS.PROCUREMENT_SUPPLY], [], [], mockRelationships, mockBusinessObjects)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)
      expect(totalCount).toBeGreaterThan(0)
    })

    it('should filter by serviceModule when serviceModuleIds provided', () => {
      const { treeData } = createComposable([], [], [SERVICE_MODULE_IDS.INVENTORY, SERVICE_MODULE_IDS.PURCHASING], [], mockRelationships, mockBusinessObjects)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)
      expect(totalCount).toBeGreaterThan(0)
    })

    it('should filter by businessObject when businessObjectIds provided', () => {
      const { treeData } = createComposable([], [], [], [BUSINESS_OBJECT_IDS.INVENTORY_MGMT, BUSINESS_OBJECT_IDS.PURCHASE_MGMT], mockRelationships, mockBusinessObjects)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)
      expect(totalCount).toBeGreaterThan(0)
    })

    it('should prioritize businessObject over serviceModule, subDomain and domain', () => {
      const { treeData: treeWithDomain } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], mockRelationships, mockBusinessObjects)
      const { treeData: treeWithBo } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [SUB_DOMAIN_IDS.PROCUREMENT_SUPPLY], [SERVICE_MODULE_IDS.INVENTORY], [BUSINESS_OBJECT_IDS.INVENTORY_MGMT], mockRelationships, mockBusinessObjects)

      const countWithDomain = treeWithDomain.value.reduce((sum, n) => sum + n.count, 0)
      const countWithBo = treeWithBo.value.reduce((sum, n) => sum + n.count, 0)

      expect(countWithBo).toBeLessThanOrEqual(countWithDomain)
    })

    it('should show all relations categorized by scope (internal, cross-boundary, external)', () => {
      const { treeData } = createComposable([], [], [], [BUSINESS_OBJECT_IDS.INVENTORY_MGMT], mockRelationships, mockBusinessObjects)
      const totalCount = treeData.value.reduce((sum, n) => sum + n.count, 0)

      expect(totalCount).toBe(mockRelationships.length)
    })
  })

  describe('fallback BO info from relation record fields', () => {
    it('should use relation record fields when BO not in businessObjects array', () => {
      const relationWithExternalBO = [
        {
          sourceBoId: 1,
          targetBoId: 999,
          sourceCode: 'BO01',
          targetCode: 'BO_EXTERNAL',
          relationCode: 'REL_EXTERNAL',
          source_domain_id: 1,
          source_domain_name: '供应链云',
          source_sub_domain_id: 11,
          source_sub_domain_name: '采购供应',
          source_service_module_id: 111,
          source_service_module_name: '库存管理模块',
          source_bo_name: '库存管理',
          target_domain_id: 999,
          target_domain_name: '外部领域',
          target_sub_domain_id: 998,
          target_sub_domain_name: '外部子领域',
          target_service_module_id: 997,
          target_service_module_name: '外部模块',
          target_bo_name: '外部对象'
        }
      ]

      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], relationWithExternalBO, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)

      expect(crossBoundaryNode).toBeDefined()
      expect(crossBoundaryNode.count).toBe(1)
    })

    it('should display actual domain name instead of "未知领域" for external BO', () => {
      const relationWithExternalBO = [
        {
          sourceBoId: 1,
          targetBoId: 999,
          sourceCode: 'BO01',
          targetCode: 'BO_EXTERNAL',
          relationCode: 'REL_EXTERNAL',
          source_domain_id: 1,
          source_domain_name: '供应链云',
          source_sub_domain_id: 11,
          source_sub_domain_name: '采购供应',
          source_service_module_id: 111,
          source_service_module_name: '库存管理模块',
          source_bo_name: '库存管理',
          target_domain_id: 888,
          target_domain_name: '财务云',
          target_sub_domain_id: 887,
          target_sub_domain_name: '财务子域',
          target_service_module_id: 886,
          target_service_module_name: '财务模块',
          target_bo_name: '财务对象'
        }
      ]

      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], relationWithExternalBO, mockBusinessObjects)
      const crossBoundaryNode = treeData.value.find(n => n.id === ScopeType.CROSS_BOUNDARY)
      const crossDomainNode = crossBoundaryNode.children.find(c => c.id === `${ScopeType.CROSS_BOUNDARY}-${CategoryType.CROSS_DOMAIN}`)

      expect(crossDomainNode).toBeDefined()
      expect(crossDomainNode.children.length).toBeGreaterThan(0)

      const domainPairNode = crossDomainNode.children[0]
      expect(domainPairNode.name).toContain('供应链云')
      expect(domainPairNode.name).toContain('财务云')

      expect(domainPairNode.name).not.toContain('未知领域')
    })
  })

  describe('_relationScopes on leaf nodes (M5)', () => {
    function findLeafNodes(nodes, result = []) {
      nodes.forEach(node => {
        if (node.relationCodes && node.relationCodes.length > 0) {
          result.push(node)
        }
        if (node.children) {
          findLeafNodes(node.children, result)
        }
      })
      return result
    }

    it('should have _relationScopes on every leaf module node', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const leaves = findLeafNodes(treeData.value)
      expect(leaves.length).toBeGreaterThan(0)
      leaves.forEach(leaf => {
        expect(leaf._relationScopes).toBeDefined()
        expect(Array.isArray(leaf._relationScopes)).toBe(true)
        expect(leaf._relationScopes.length).toBeGreaterThan(0)
      })
    })

    it('should have _relationScopes length match relationCodes length', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const leaves = findLeafNodes(treeData.value)
      leaves.forEach(leaf => {
        expect(leaf._relationScopes.length).toBe(leaf.relationCodes.length)
      })
    })

    it('should include valid boId and domainId in _relationScopes entries', () => {
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN, DOMAIN_IDS.PROCUREMENT, DOMAIN_IDS.FINANCE], [], [], [], mockRelationships, mockBusinessObjects)
      const leaves = findLeafNodes(treeData.value)
      leaves.forEach(leaf => {
        leaf._relationScopes.forEach(rs => {
          expect(rs.src).toBeDefined()
          expect(rs.tgt).toBeDefined()
          expect(typeof rs.src.boId).toBe('number')
          expect(typeof rs.tgt.boId).toBe('number')
          expect(typeof rs.src.domainId).toBe('number')
          expect(typeof rs.tgt.domainId).toBe('number')
        })
      })
    })

    it('should have _relationScopes using optional chaining for external BOs', () => {
      const relationWithExternalBO = [
        {
          sourceBoId: 1,
          targetBoId: 999,
          sourceCode: 'BO01',
          targetCode: 'BO_EXTERNAL',
          relationCode: 'REL_EXTERNAL',
          source_domain_id: 1, source_domain_name: '供应链云',
          source_sub_domain_id: 11, source_sub_domain_name: '采购供应',
          source_service_module_id: 111, source_service_module_name: '库存管理模块',
          source_bo_name: '库存管理',
          target_domain_id: 888, target_domain_name: '财务云',
          target_sub_domain_id: 887, target_sub_domain_name: '财务子域',
          target_service_module_id: 886, target_service_module_name: '财务模块',
          target_bo_name: '财务对象'
        }
      ]
      const { treeData } = createComposable([DOMAIN_IDS.SUPPLY_CHAIN], [], [], [], relationWithExternalBO, mockBusinessObjects)
      const leaves = findLeafNodes(treeData.value)
      expect(leaves.length).toBeGreaterThan(0)
      leaves.forEach(leaf => {
        leaf._relationScopes.forEach(rs => {
          expect(rs.src.boId).toBeDefined()
          expect(rs.src.domainId).toBeDefined()
        })
      })
    })
  })
})
