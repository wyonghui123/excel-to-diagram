import { ref, computed } from 'vue'
import { buildRelationScopeTree } from '@/services/relationClassifier'

export { buildRelationScopeTree }

export function useRelationClassifier(domainIdsSource, subDomainIdsSource, serviceModuleIdsSource, businessObjectIdsSource, allRelationships, businessObjects) {
  const selectedScopeIds = ref([])
  const expandedNodeIds = ref([])

  const treeData = computed(() => {
    const filterParams = {
      domainIds: domainIdsSource.value ?? domainIdsSource ?? [],
      subDomainIds: subDomainIdsSource.value ?? subDomainIdsSource ?? [],
      serviceModuleIds: serviceModuleIdsSource.value ?? serviceModuleIdsSource ?? [],
      businessObjectIds: businessObjectIdsSource.value ?? businessObjectIdsSource ?? []
    }
    return buildRelationScopeTree(
      filterParams,
      allRelationships.value ?? allRelationships,
      businessObjects.value ?? businessObjects
    )
  })

  function collectRelationCodesFromNode(node) {
    const codes = []
    if (node.relationCodes && node.relationCodes.length > 0) {
      codes.push(...node.relationCodes)
    }
    if (node.children) {
      node.children.forEach(child => {
        codes.push(...collectRelationCodesFromNode(child))
      })
    }
    return codes
  }

  function getSelectedRelationCodes() {
    const result = new Set()
    const selectedIds = selectedScopeIds.value

    function traverse(nodes) {
      for (const node of nodes) {
        if (selectedIds.includes(node.id)) {
          collectRelationCodesFromNode(node).forEach(code => result.add(code))
        }
        if (node.children && node.children.length > 0) {
          traverse(node.children)
        }
      }
    }

    traverse(treeData.value)
    return Array.from(result)
  }

  function toggleNodeSelection(nodeId) {
    const idx = selectedScopeIds.value.indexOf(nodeId)
    if (idx >= 0) {
      selectedScopeIds.value.splice(idx, 1)
    } else {
      selectedScopeIds.value.push(nodeId)
    }
  }

  function toggleNodeExpand(nodeId) {
    const idx = expandedNodeIds.value.indexOf(nodeId)
    if (idx >= 0) {
      expandedNodeIds.value.splice(idx, 1)
    } else {
      expandedNodeIds.value.push(nodeId)
    }
  }

  function expandAll(nodes) {
    const nodesToExpand = (nodes && Array.isArray(nodes)) ? nodes : (treeData.value || [])
    if (!nodesToExpand || !Array.isArray(nodesToExpand) || nodesToExpand.length === 0) {
      return
    }
    nodesToExpand.forEach(node => {
      if (node.children && node.children.length > 0) {
        if (!expandedNodeIds.value.includes(node.id)) {
          expandedNodeIds.value.push(node.id)
        }
        expandAll(node.children)
      }
    })
  }

  function collapseAll(nodes) {
    const nodesToCollapse = (nodes && Array.isArray(nodes)) ? nodes : (treeData.value || [])
    if (!nodesToCollapse || !Array.isArray(nodesToCollapse) || nodesToCollapse.length === 0) {
      return
    }
    nodesToCollapse.forEach(node => {
      const idx = expandedNodeIds.value.indexOf(node.id)
      if (idx >= 0) {
        expandedNodeIds.value.splice(idx, 1)
      }
      if (node.children && node.children.length > 0) {
        collapseAll(node.children)
      }
    })
  }

  return {
    treeData,
    selectedScopeIds,
    expandedNodeIds,
    toggleNodeSelection,
    toggleNodeExpand,
    expandAll,
    collapseAll,
    getSelectedRelationCodes
  }
}
