<template>
  <div class="step-scope">
    <div class="scope-panel">
      <div class="panel-header--compact">
        <span class="panel-title">{{ stepMode === 'center' ? '选择中心范围' : '选择关系范围' }}</span>
      </div>
      <div class="panel-body no-padding-top">
        <!-- 数据校验结果面板 -->
        <ValidationPanel
          v-if="validationResult && validationResult.items.length > 0"
          :validation-result="validationResult"
          :filtered-stats="filteredStats"
        />
        <!-- 中心范围选择 -->
        <div v-if="stepMode === 'center'" class="center-scope-step">
          <div v-if="previewData && previewData.domainProducts" class="selector-section">
            <CenterScopeSelector
              :model-value="centerScope || []"
              :domain-products="previewData.domainProducts"
              :business-objects="previewData.businessObjects"
              :presets="centerScopePresets || []"
              @update:model-value="updateCenterScope"
              @save-preset="handleSavePreset"
              @load-preset="handleLoadPreset"
              @delete-preset="handleDeletePreset"
            />
          </div>
          <div v-else class="loading-placeholder">
            正在加载数据...
          </div>
          
          <!-- 中心范围内的业务对象和服务模块列表 -->
          <div v-if="centerScope.length > 0" class="scope-summary">
            <!-- 业务对象表格 -->
            <div class="summary-section">
              <h4>中心范围业务对象 ({{ centerBusinessObjects.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>业务对象编码</th>
                      <th>业务对象名称</th>
                      <th>所属服务模块</th>
                      <th>所属子领域</th>
                      <th>所属领域</th>
                      <th>备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="bo in centerBusinessObjects" :key="bo.code">
                      <td>{{ bo.code || '-' }}</td>
                      <td>{{ bo.name }}</td>
                      <td>{{ bo.serviceModuleName || bo.serviceModule || '-' }}</td>
                      <td>{{ bo.subDomain || '-' }}</td>
                      <td>{{ bo.domain || '-' }}</td>
                      <td>{{ bo.annotationContent || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 服务模块表格 -->
            <div class="summary-section">
              <h4>中心范围服务模块 ({{ centerServiceModules.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>服务模块编码</th>
                      <th>服务模块名称</th>
                      <th>所属子领域</th>
                      <th>所属领域</th>
                      <th>备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="sm in centerServiceModules" :key="sm.code">
                      <td>{{ sm.code }}</td>
                      <td>{{ sm.name }}</td>
                      <td>{{ sm.subDomain || '-' }}</td>
                      <td>{{ sm.domain || '-' }}</td>
                      <td>{{ sm.annotationContent || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 关系范围选择 -->
        <div v-if="stepMode === 'relation'" class="relation-scope-step">
          <div v-if="relationCategoryTreeData && relationCategoryTreeData.length > 0" class="selector-section">
            <RelationCategoryTree
              :tree-data="relationCategoryTreeData"
              :selected-node-ids="selectedRelationNodeIds || []"
              @update:selected-node-ids="updateSelectedRelationNodeIds"
              @node-toggle="handleNodeToggle"
            />
          </div>
          <div v-else class="loading-placeholder">
            正在加载关系数据...
          </div>
          
          <!-- 选中关系范围内的详情列表 -->
          <div v-if="selectedRelationNodeIds.length > 0" class="scope-summary">
            <!-- 子页签导航 -->
            <div class="relation-tabs">
              <button 
                :class="['tab-btn', { active: activeRelationTab === 'boRelations' }]"
                @click="activeRelationTab = 'boRelations'"
              >
                业务对象关系 ({{ selectedRelations.length }})
              </button>
              <button 
                :class="['tab-btn', { active: activeRelationTab === 'smRelations' }]"
                @click="activeRelationTab = 'smRelations'"
              >
                服务模块关系 ({{ selectedServiceModuleRelations.length }})
              </button>
              <button 
                :class="['tab-btn', { active: activeRelationTab === 'newBOs' }]"
                @click="activeRelationTab = 'newBOs'"
              >
                新增业务对象 ({{ newBusinessObjects.length }})
              </button>
              <button 
                :class="['tab-btn', { active: activeRelationTab === 'newSMs' }]"
                @click="activeRelationTab = 'newSMs'"
              >
                新增服务模块 ({{ newServiceModules.length }})
              </button>
            </div>

            <!-- 业务对象关系表格 -->
            <div v-if="activeRelationTab === 'boRelations'" class="summary-section">
              <h4>业务对象关系 ({{ selectedRelations.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>关系编码</th>
                      <th>源对象编码</th>
                      <th>源对象名称</th>
                      <th>目标对象编码</th>
                      <th>目标对象名称</th>
                      <th>关系说明</th>
                      <th>备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="rel in selectedRelations" :key="rel.relationCode">
                      <td>{{ rel.relationCode || '-' }}</td>
                      <td>{{ rel.sourceCode || '-' }}</td>
                      <td>{{ rel.sourceName || '-' }}</td>
                      <td>{{ rel.targetCode || '-' }}</td>
                      <td>{{ rel.targetName || '-' }}</td>
                      <td>{{ rel.relationDesc || '-' }}</td>
                      <td>{{ rel.annotationContent || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 服务模块关系表格 -->
            <div v-if="activeRelationTab === 'smRelations'" class="summary-section">
              <h4>服务模块关系 ({{ selectedServiceModuleRelations.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>服务模块关系编码</th>
                      <th>源服务模块编码</th>
                      <th>源服务模块名称</th>
                      <th>目标服务模块编码</th>
                      <th>目标服务模块名称</th>
                      <th>关系数</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="rel in selectedServiceModuleRelations" :key="rel.moduleRelationCode">
                      <td>{{ rel.moduleRelationCode || '-' }}</td>
                      <td>{{ rel.sourceModuleCode || '-' }}</td>
                      <td>{{ rel.sourceModuleName || '-' }}</td>
                      <td>{{ rel.targetModuleCode || '-' }}</td>
                      <td>{{ rel.targetModuleName || '-' }}</td>
                      <td>{{ rel.objectRelationCount }}条</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 新增业务对象表格 -->
            <div v-if="activeRelationTab === 'newBOs'" class="summary-section">
              <h4>新增业务对象 ({{ newBusinessObjects.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>业务对象编码</th>
                      <th>业务对象名称</th>
                      <th>所属服务模块</th>
                      <th>所属子领域</th>
                      <th>所属领域</th>
                      <th>来源关系</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="bo in newBusinessObjects" :key="bo.code">
                      <td>{{ bo.code || '-' }}</td>
                      <td>{{ bo.name || '-' }}</td>
                      <td>{{ bo.serviceModuleName || bo.serviceModule || '-' }}</td>
                      <td>{{ bo.subDomain || '-' }}</td>
                      <td>{{ bo.domain || '-' }}</td>
                      <td>{{ bo.sourceRelation || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 新增服务模块表格 -->
            <div v-if="activeRelationTab === 'newSMs'" class="summary-section">
              <h4>新增服务模块 ({{ newServiceModules.length }})</h4>
              <div class="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>服务模块编码</th>
                      <th>服务模块名称</th>
                      <th>所属子领域</th>
                      <th>所属领域</th>
                      <th>来源关系</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="sm in newServiceModules" :key="sm.code">
                      <td>{{ sm.code || '-' }}</td>
                      <td>{{ sm.name || '-' }}</td>
                      <td>{{ sm.subDomain || '-' }}</td>
                      <td>{{ sm.domain || '-' }}</td>
                      <td>{{ sm.sourceRelation || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch } from 'vue'
import { AppButton } from '../../../../components/common'
import { AppIcon } from '../../../../components/common/AppIcon'
import CenterScopeSelector from '../../../../components/CenterScopeSelector.vue'
import RelationCategoryTree from '../../../../components/RelationCategoryTree.vue'
import ValidationPanel from '../../../../components/ValidationPanel.vue'
import { validateData } from '../../../../services/dataValidator.js'

export default {
  name: 'StepScope',
  components: { AppButton, AppIcon, CenterScopeSelector, RelationCategoryTree, ValidationPanel },
  props: {
    stepMode: {
      type: String,
      default: 'center' // 'center' 或 'relation'
    },
    previewData: Object,
    rawData: Object,
    modelValue: Array,
    centerScope: Array,
    centerScopePresets: Array,
    selectedRelationNodeIds: Array,
    relationCategoryTree: Array
  },
  emits: [
    'update:modelValue',
    'next',
    'prev',
    'filter-by-relation',
    'internal-relation-filter',
    'update:centerScope',
    'update:selectedRelationNodeIds',
    'save-center-scope-preset',
    'load-center-scope-preset',
    'delete-center-scope-preset',
    'toggle-relation-node',
    'apply-relation-filter'
  ],
  setup(props, { emit }) {
    const currentSubStep = ref(props.stepMode || 'center')
    const validationResult = ref(null)
    const activeRelationTab = ref('boRelations') // 默认显示业务对象关系

    // 运行数据校验
    const runValidation = () => {
      if (props.rawData && props.previewData) {
        const result = validateData(props.rawData, props.previewData)
        validationResult.value = result
      } else {
        validationResult.value = null
      }
    }

    // 监听数据变化，自动运行校验
    watch(() => props.previewData, () => {
      runValidation()
    }, { immediate: true })

    watch(() => props.rawData, () => {
      runValidation()
    }, { immediate: true })

    // 将关系分类树转换为 RelationCategoryTree 组件需要的格式
    const relationCategoryTreeData = computed(() => {
      const tree = props.relationCategoryTree
      if (!tree || !Array.isArray(tree)) return []
      return tree
    })

    // 中心范围内的业务对象列表
    const centerBusinessObjects = computed(() => {
      if (!props.centerScope || !props.previewData?.businessObjects) return []
      const centerSet = new Set(props.centerScope)
      return props.previewData.businessObjects.filter(bo => centerSet.has(bo.code))
    })
    
    // 中心范围内的服务模块列表（去重）
    const centerServiceModules = computed(() => {
      if (!props.centerScope || !props.previewData?.businessObjects) return []
      const centerSet = new Set(props.centerScope)
      const moduleMap = new Map()

      props.previewData.businessObjects.forEach(bo => {
        if (centerSet.has(bo.code) && bo.serviceModule) {
          if (!moduleMap.has(bo.serviceModule)) {
            moduleMap.set(bo.serviceModule, {
              code: bo.serviceModule,
              name: bo.serviceModuleName || bo.serviceModule,
              subDomain: bo.subDomain,
              domain: bo.domain,
              annotationContent: bo.serviceModuleAnnotationContent || ''
            })
          }
        }
      })

      // 如果有服务模块详情，补充备注信息
      if (props.previewData?.serviceModules) {
        props.previewData.serviceModules.forEach(sm => {
          if (moduleMap.has(sm.code) && sm.annotationContent) {
            const existing = moduleMap.get(sm.code)
            existing.annotationContent = sm.annotationContent
            moduleMap.set(sm.code, existing)
          }
        })
      }

      return Array.from(moduleMap.values())
    })

    // 基于中心范围和选中关系的业务对象编码（用于配置步骤过滤）
    const relationFilteredBoCodes = computed(() => {
      if (!props.previewData?.businessObjects) return []

      // 如果没有中心范围，返回空（表示显示所有）
      if (!props.centerScope || props.centerScope.length === 0) {
        return []
      }

      const filteredCodes = new Set(props.centerScope)

      // 如果有选中关系节点，进一步过滤
      if (props.selectedRelationNodeIds && props.selectedRelationNodeIds.length > 0) {
        const relationCodes = new Set()

        function traverseNode(node) {
          if (props.selectedRelationNodeIds.includes(node.id)) {
            if (node.relationCodes && node.relationCodes.length > 0) {
              node.relationCodes.forEach(code => relationCodes.add(code))
            }
          }
          if (node.children && node.children.length > 0) {
            node.children.forEach(child => traverseNode(child))
          }
        }

        if (props.relationCategoryTree) {
          props.relationCategoryTree.forEach(rootNode => traverseNode(rootNode))
        }

        // 获取选中关系涉及的业务对象编码
        if (!props.previewData?.relationships) return []
        
        // 先过滤无效关系（与 relationCategoryTree 保持一致）
        const validRelationships = props.previewData.relationships.filter(rel => {
          if (!rel.relationCode) return false
          if (rel.sourceCode === rel.targetCode) return false
          return true
        })
        
        validRelationships.forEach(rel => {
          if (relationCodes.has(rel.relationCode)) {
            filteredCodes.add(rel.sourceCode)
            filteredCodes.add(rel.targetCode)
          }
        })
      }

      return Array.from(filteredCodes)
    })

    // 选中的关系列表
    const selectedRelations = computed(() => {
      if (!props.selectedRelationNodeIds || props.selectedRelationNodeIds.length === 0) return []
      if (!props.relationCategoryTree || !Array.isArray(props.relationCategoryTree)) return []

      // 从关系分类树中收集所有选中的关系编码
      const relationCodes = new Set()

      function traverseNode(node) {
        if (props.selectedRelationNodeIds.includes(node.id)) {
          if (node.relationCodes && node.relationCodes.length > 0) {
            node.relationCodes.forEach(code => relationCodes.add(code))
          }
        }
        if (node.children && node.children.length > 0) {
          node.children.forEach(child => traverseNode(child))
        }
      }

      props.relationCategoryTree.forEach(rootNode => traverseNode(rootNode))

      // 根据关系编码过滤关系列表，并去重
      if (!props.previewData?.relationships) return []

      // 先过滤无效关系（与 relationCategoryTree 保持一致）
      let validRelationships = props.previewData.relationships.filter(rel => {
        if (!rel.relationCode) return false
        if (rel.sourceCode === rel.targetCode) return false  // 排除自环
        return true
      })

      // 过滤掉数据校验中发现的问题关系
      if (validationResult.value && validationResult.value.items.length > 0) {
        const invalidRelationCodes = new Set()
        validationResult.value.items.forEach(item => {
          if (item.sheet === '业务对象关系' && item.entityCode) {
            invalidRelationCodes.add(item.entityCode)
          }
        })
        validRelationships = validRelationships.filter(rel => !invalidRelationCodes.has(rel.relationCode))
      }

      const filteredRels = validRelationships.filter(rel => relationCodes.has(rel.relationCode))
      // 使用 Map 去重，基于 relationCode
      const uniqueMap = new Map()
      filteredRels.forEach(rel => {
        if (!uniqueMap.has(rel.relationCode)) {
          uniqueMap.set(rel.relationCode, rel)
        }
      })
      return Array.from(uniqueMap.values())
    })

    // 统计因错误被过滤的业务对象和关系数量
    const filteredStats = computed(() => {
      if (!validationResult.value || validationResult.value.items.length === 0) {
        return { businessObjects: 0, relations: 0 }
      }

      const invalidBoCodes = new Set()
      const invalidRelationRows = new Set()

      validationResult.value.items.forEach(item => {
        if (item.level === 'error') {
          if (item.sheet === '业务对象' && item.entityCode) {
            invalidBoCodes.add(item.entityCode)
          } else if (item.sheet === '业务对象关系') {
            // 使用行号来统计关系记录数（即使没有关系编码）
            invalidRelationRows.add(item.row)
          }
        }
      })

      return {
        businessObjects: invalidBoCodes.size,
        relations: invalidRelationRows.size
      }
    })

    // 选中的服务模块关系列表
    const selectedServiceModuleRelations = computed(() => {
      // 如果没有选中任何节点，不显示服务模块关系
      if (!props.selectedRelationNodeIds || props.selectedRelationNodeIds.length === 0) return []
      if (!props.previewData?.relationships || !props.previewData?.businessObjects) return []

      // 获取选中的关系编码
      const relationCodes = new Set()

      function traverseNode(node) {
        if (props.selectedRelationNodeIds.includes(node.id)) {
          if (node.relationCodes && node.relationCodes.length > 0) {
            node.relationCodes.forEach(code => relationCodes.add(code))
          }
        }
        if (node.children && node.children.length > 0) {
          node.children.forEach(child => traverseNode(child))
        }
      }

      props.relationCategoryTree.forEach(rootNode => traverseNode(rootNode))

      // 创建业务对象编码到服务模块的映射
      const boToModuleMap = new Map()
      props.previewData.businessObjects.forEach(bo => {
        if (bo.code) {
          boToModuleMap.set(bo.code, {
            moduleCode: bo.serviceModule,
            moduleName: bo.serviceModuleName || bo.serviceModule
          })
        }
      })

      // 先过滤无效关系（与 relationCategoryTree 保持一致）
      const validRelationships = props.previewData.relationships.filter(rel => {
        if (!rel.relationCode) return false
        if (rel.sourceCode === rel.targetCode) return false
        return true
      })

      // 按服务模块关系分组，只统计选中的关系
      const moduleRelationMap = new Map()

      validRelationships.forEach(rel => {
        if (!rel.sourceCode || !rel.targetCode) return
        if (!relationCodes.has(rel.relationCode)) return // 只统计选中的关系

        const sourceBo = boToModuleMap.get(rel.sourceCode)
        const targetBo = boToModuleMap.get(rel.targetCode)

        if (sourceBo && targetBo) {
          // 跳过同一服务模块内的关系（自环）
          if (sourceBo.moduleCode === targetBo.moduleCode) return

          // 不考虑方向，使用排序后的 key
          const pair = [sourceBo.moduleCode, targetBo.moduleCode].sort()
          const key = `${pair[0]}-${pair[1]}`

          if (!moduleRelationMap.has(key)) {
            moduleRelationMap.set(key, {
              moduleRelationCode: key,
              sourceModuleCode: pair[0],
              sourceModuleName: sourceBo.moduleName,
              targetModuleCode: pair[1],
              targetModuleName: targetBo.moduleName,
              objectRelationCodes: [],
              objectRelationCount: 0
            })
          }
          moduleRelationMap.get(key).objectRelationCodes.push(rel.relationCode)
          moduleRelationMap.get(key).objectRelationCount++
        }
      })

      return Array.from(moduleRelationMap.values())
    })

    // 新增业务对象（关系选择带来的，不在中心范围内）
    const newBusinessObjects = computed(() => {
      if (!props.previewData?.businessObjects || !props.centerScope) return []
      
      const centerSet = new Set(props.centerScope)
      const relationBoCodes = relationFilteredBoCodes.value
      
      if (!relationBoCodes || relationBoCodes.length === 0) return []
      
      // 找出在关系范围内但不在中心范围内的业务对象
      return props.previewData.businessObjects.filter(bo => {
        if (!bo.code) return false
        return relationBoCodes.includes(bo.code) && !centerSet.has(bo.code)
      }).map(bo => ({
        ...bo,
        sourceRelation: '关系选择引入'
      }))
    })

    // 新增服务模块（关系选择带来的，不在中心范围内）
    const newServiceModules = computed(() => {
      if (!props.previewData?.businessObjects || !props.centerScope) return []
      
      const centerSet = new Set(props.centerScope)
      const relationBoCodes = relationFilteredBoCodes.value
      
      if (!relationBoCodes || relationBoCodes.length === 0) return []
      
      // 获取中心范围的服务模块
      const centerModuleCodes = new Set()
      props.previewData.businessObjects.forEach(bo => {
        if (centerSet.has(bo.code) && bo.serviceModule) {
          centerModuleCodes.add(bo.serviceModule)
        }
      })
      
      // 获取关系范围新增的服务模块
      const newModuleMap = new Map()
      props.previewData.businessObjects.forEach(bo => {
        if (relationBoCodes.includes(bo.code) && 
            bo.serviceModule && 
            !centerModuleCodes.has(bo.serviceModule)) {
          if (!newModuleMap.has(bo.serviceModule)) {
            newModuleMap.set(bo.serviceModule, {
              code: bo.serviceModule,
              name: bo.serviceModuleName || bo.serviceModule,
              subDomain: bo.subDomain,
              domain: bo.domain,
              sourceRelation: '关系选择引入'
            })
          }
        }
      })
      
      return Array.from(newModuleMap.values())
    })

    // 切换到指定子步骤
    const goToSubStep = (step) => {
      currentSubStep.value = step
    }
    
    // 下一步
    const nextSubStep = () => {
      if (currentSubStep.value === 'center') {
        currentSubStep.value = 'relation'
      }
    }
    
    // 上一步
    const prevSubStep = () => {
      if (currentSubStep.value === 'relation') {
        currentSubStep.value = 'center'
      }
    }
    
    // 保存预设
    const handleSavePreset = (presetData) => {
      emit('save-center-scope-preset', presetData.name)
    }
    
    // 加载预设
    const handleLoadPreset = (preset) => {
      emit('load-center-scope-preset', preset.id)
    }
    
    // 删除预设
    const handleDeletePreset = (presetId) => {
      emit('delete-center-scope-preset', presetId)
    }
    
    // 处理节点切换
    const handleNodeToggle = ({ node, selected }) => {
      emit('toggle-relation-node', node.id)
    }
    
    // 更新中心范围
    const updateCenterScope = (val) => {
      console.log('[StepScope] updateCenterScope CALLED')
      console.log('[StepScope] val:', val)
      console.log('[StepScope] val type:', typeof val)
      console.log('[StepScope] val length:', val?.length)
      console.log('[StepScope] val isArray:', Array.isArray(val))
      console.log('[StepScope] val first 5:', val?.slice?.(0, 5))
      emit('update:modelValue', val)
      emit('update:centerScope', val)
    }
    
    // 更新选中的关系节点
    const updateSelectedRelationNodeIds = (val) => {
      emit('update:selectedRelationNodeIds', val)
    }

    // 应用关系过滤到配置步骤
    const handleApplyRelationFilter = () => {
      const codes = relationFilteredBoCodes.value
      emit('apply-relation-filter', codes)
    }

    // 下一步（带过滤应用）
    const nextSubStepWithFilter = () => {
      // 在切换到 relation tab 之前，先应用关系过滤
      if (currentSubStep.value === 'center') {
        handleApplyRelationFilter()
        currentSubStep.value = 'relation'
      }
    }

    // 下一步到配置步骤（应用过滤）
    const handleNextToConfig = () => {
      // 应用过滤
      handleApplyRelationFilter()
      // 触发下一步
      emit('next')
    }

    // 从中心步骤跳转到关系步骤
    const handleNextToRelation = () => {
      // 应用过滤
      handleApplyRelationFilter()
      // 触发下一步
      emit('next')
    }

    return {
      currentSubStep,
      validationResult,
      filteredStats,
      activeRelationTab,
      relationCategoryTreeData,
      centerBusinessObjects,
      centerServiceModules,
      selectedRelations,
      selectedServiceModuleRelations,
      newBusinessObjects,
      newServiceModules,
      relationFilteredBoCodes,
      goToSubStep,
      nextSubStep: nextSubStepWithFilter,
      prevSubStep,
      handleSavePreset,
      handleLoadPreset,
      handleDeletePreset,
      handleNodeToggle,
      updateCenterScope,
      updateSelectedRelationNodeIds,
      handleApplyRelationFilter,
      handleNextToConfig,
      handleNextToRelation
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-scope {
  height: 100%;
}

.scope-panel {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 紧凑面板标题 */
.panel-header--compact {
  padding: 8px var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
}

.panel-header {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.panel-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.loading-placeholder {
  padding: var(--spacing-xl);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 14px;
}

.panel-body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow: auto;

  &.no-padding-top {
    padding-top: 0;
  }
}

.center-scope-step,
.relation-scope-step {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.selector-section {
  flex-shrink: 0;
}

.scope-summary {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.relation-tabs {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--spacing-sm);

  .tab-btn {
    padding: 6px 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg-primary);
    color: var(--color-text-secondary);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      border-color: var(--color-primary);
      color: var(--color-primary);
    }

    &.active {
      background: var(--color-primary);
      color: white;
      border-color: var(--color-primary);
    }
  }
}

.summary-section {
  h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin: 0 0 var(--spacing-sm) 0;
  }
}

.table-wrapper {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;

    th,
    td {
      padding: var(--spacing-xs) var(--spacing-sm);
      text-align: left;
      border-bottom: 1px solid var(--color-border);
    }

    th {
      background: var(--color-bg-secondary);
      font-weight: 600;
      color: var(--color-text-secondary);
      position: sticky;
      top: 0;
    }

    td {
      color: var(--color-text-primary);
    }

    tr:last-child td {
      border-bottom: none;
    }

    tbody tr:hover {
      background: var(--color-bg-secondary);
    }
  }
}

@include respond-to('sm') {
  .panel-header {
    padding: var(--spacing-sm) var(--spacing-md);
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .sub-step-indicator {
    font-size: 13px;
  }

  .panel-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .panel-body {
    padding: var(--spacing-md);
  }
}
</style>
