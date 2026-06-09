<!--
  @deprecated 2026-06-10
  旧版数据预览组件，仅被已废弃的 components/AADiagramApp.vue 引用。
  数据校验功能迁移到 views/AADiagramApp/components/steps/StepScope.vue（ValidationPanel）。
  数据预览功能迁移到 views/AADiagramApp/components/steps/StepDisplay.vue。
  无生产代码引用（grep 验证通过），保留仅为历史记录。
  建议下一轮清理时删除。
  替代: views/AADiagramApp/components/steps/{StepScope,StepDisplay}.vue
-->
<template>
  <div class="data-preview">
    <!-- 数据校验预警区域 -->
    <ValidationPanel
      v-if="validationResult && validationResult.items.length > 0"
      :validation-result="validationResult"
    />

    <!-- AI校验区域 -->
    <div class="ai-validation-section">
      <!-- AI校验加载状态 -->
      <div v-if="isAIValidating" class="ai-validating">
        <span class="loading-icon"><AppIcon name="lightning" size="md" /></span>
        <span class="loading-text">智谱AI正在检查关系说明的可读性...</span>
      </div>

      <!-- AI校验触发按钮 -->
      <div v-else-if="!aiValidationDone && rawData?.relationshipData?.length > 0" class="ai-validation-trigger">
        <div class="ai-trigger-info">
          <span class="ai-icon"><AppIcon name="lightning" size="md" /></span>
          <div class="ai-trigger-text">
            <div class="ai-trigger-title">AI智能校验</div>
            <div class="ai-trigger-desc">使用智谱AI检查{{ rawData.relationshipData.length }}条关系说明的可读性</div>
          </div>
        </div>
        <button @click="runAIValidation" class="ai-trigger-btn">
          开始AI校验
        </button>
      </div>

      <!-- AI校验完成提示 -->
      <div v-else-if="aiValidationDone" class="ai-validation-done">
        <AppIcon name="check-circle" :size="16" class="ai-icon" />
        <span>AI校验已完成</span>
        <button @click="runAIValidation" class="ai-retry-btn">
          重新校验
        </button>
      </div>
    </div>

    <!-- 对象列表 - 三页签 -->
    <div class="preview-block">
      <h3>对象列表</h3>
      <div class="tabs">
        <button
          :class="['tab-btn', { active: activeTab === 'scopeSelector' }]"
          @click="activeTab = 'scopeSelector'"
        >
          范围选择
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'relationScope' }]"
          @click="activeTab = 'relationScope'"
        >
          关系范围
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'businessObject' }]"
          @click="activeTab = 'businessObject'"
        >
          业务对象 ({{ previewData.businessObjects?.length || 0 }})
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'serviceModule' }]"
          @click="activeTab = 'serviceModule'"
        >
          服务模块 ({{ previewData.serviceModules?.length || 0 }})
        </button>
      </div>

      <!-- 范围选择 - 默认页签 -->
      <div v-if="activeTab === 'scopeSelector'">
        <ScopeSelector
          :domain-products="previewData.domainProducts"
          :business-objects="previewData.businessObjects"
          :model-value="selectedScope"
          :auto-select-all="true"
          @update:model-value="handleScopeChange"
        />
      </div>

      <!-- 关系范围选择 -->
      <div v-if="activeTab === 'relationScope'" class="relation-scope-tab">
        <RelationCategoryTree
          :tree-data="relationCategoryTree"
          v-model:selected-node-ids="selectedRelationNodeIds"
          @node-toggle="handleNodeToggle"
        />
      </div>

      <!-- 业务对象表格 -->
      <div v-if="activeTab === 'businessObject'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>选中</th>
              <th>业务对象名称</th>
              <th>业务对象编码</th>
              <th>所属服务模块</th>
              <th>所属子领域</th>
              <th>所属领域</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in selectedBusinessObjects" :key="idx">
              <td>
                <span :class="['status-badge', item.isSelected ? 'selected' : 'not-selected']">
                  {{ item.isSelected ? 'Y' : 'N' }}
                </span>
              </td>
              <td>{{ item.name }}</td>
              <td>{{ item.code || '-' }}</td>
              <td>{{ item.serviceModuleName || item.serviceModule || '-' }}</td>
              <td>{{ item.subDomain || '-' }}</td>
              <td>{{ item.domain || '-' }}</td>
              <td>
                <span v-if="item.annotationContent" :class="['annotation-tag', 'tag-' + (item.annotationCategory || 'info')]">
                  <AppIcon :name="getAnnotationIcon(item.annotationCategory)" :size="12" />
                </span>
                <span v-if="item.annotationContent" class="annotation-preview" :title="item.annotationContent">
                  {{ truncateText(item.annotationContent, 20) }}
                </span>
                <span v-else class="no-annotation">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 服务模块表格 -->
      <div v-if="activeTab === 'serviceModule'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>选中</th>
              <th>服务模块名称</th>
              <th>服务模块编码</th>
              <th>所属子领域</th>
              <th>所属领域</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in selectedServiceModules" :key="idx">
              <td>
                <span :class="['status-badge', item.isSelected ? 'selected' : 'not-selected']">
                  {{ item.isSelected ? 'Y' : 'N' }}
                </span>
              </td>
              <td>{{ item.name }}</td>
              <td>{{ item.code || '-' }}</td>
              <td>{{ item.subDomain || '-' }}</td>
              <td>{{ item.domain || '-' }}</td>
              <td>
                <span v-if="item.annotationContent" :class="['annotation-tag', 'tag-' + (item.annotationCategory || 'info')]">
                  <AppIcon :name="getAnnotationIcon(item.annotationCategory)" :size="12" />
                </span>
              <span v-if="item.annotationContent" class="annotation-preview" :title="item.annotationContent">
                  {{ truncateText(item.annotationContent, 20) }}
                </span>
                <span v-else class="no-annotation">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 业务对象关系 - 双页签 -->
    <div class="preview-block">
      <div class="relation-header">
        <h3>业务对象关系</h3>
        <div class="filter-switches">
          <label class="filter-switch">
            <input
              type="checkbox"
              v-model="filterByRelationEnabled"
              @change="handleFilterToggle"
              :disabled="!previewData.relationships || previewData.relationships.length === 0"
            />
            <span class="switch-slider"></span>
            <span class="filter-label">只包含有关系对象</span>
          </label>
          <label class="filter-select">
            <span class="filter-label">过滤内部关系:</span>
            <select
              v-model="internalRelationFilter"
              @change="handleInternalRelationFilterChange"
              :disabled="!filterByRelationEnabled || !previewData.relationships || previewData.relationships.length === 0"
            >
              <option value="off">关闭</option>
              <option value="serviceModule">服务模块</option>
              <option value="subDomain">子领域</option>
              <option value="domain">领域</option>
            </select>
          </label>
        </div>
      </div>
      <div class="tabs">
        <button
          :class="['tab-btn', { active: activeRelationTab === 'objectRelation' }]"
          @click="activeRelationTab = 'objectRelation'"
        >
          业务对象关系 ({{ previewData.relationships?.length || 0 }})
        </button>
        <button
          :class="['tab-btn', { active: activeRelationTab === 'moduleRelation' }]"
          @click="activeRelationTab = 'moduleRelation'"
        >
          服务模块关系 ({{ serviceModuleRelations?.length || 0 }})
        </button>
      </div>

      <!-- 业务对象关系表格 -->
      <div v-if="activeRelationTab === 'objectRelation'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>选中</th>
              <th>源业务对象名称</th>
              <th>目标业务对象名称</th>
              <th>关系编码</th>
              <th>关系说明</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in filteredBusinessObjectRelations" :key="idx" :class="{ 'relation-scope-selected': item.isRelationScopeSelected }">
              <td>
                <span :class="['status-badge', isRelationSelected(item) ? 'selected' : 'not-selected']">
                  {{ isRelationSelected(item) ? 'Y' : 'N' }}
                </span>
              </td>
              <td>{{ item.sourceName }}</td>
              <td>{{ item.targetName }}</td>
              <td>{{ item.relationCode }}</td>
              <td>{{ item.relationDesc || '-' }}</td>
              <td>
                <span v-if="item.annotationContent" :class="['annotation-tag', 'tag-' + (item.annotationCategory || 'info')]">
                  {{ getAnnotationIcon(item.annotationCategory) }}
                </span>
                <span v-if="item.annotationContent" class="annotation-preview" :title="item.annotationContent">
                  {{ truncateText(item.annotationContent, 20) }}
                </span>
                <span v-else class="no-annotation">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 服务模块关系表格 -->
      <div v-if="activeRelationTab === 'moduleRelation'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>选中</th>
              <th>源服务模块名称</th>
              <th>源服务模块编码</th>
              <th>目标服务模块名称</th>
              <th>目标服务模块编码</th>
              <th>服务关系编码</th>
              <th>业务对象关系编码</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in serviceModuleRelations" :key="idx" :class="{ 'internal-relation': item.isInternal }">
              <td>
                <span :class="['status-badge', item.isSelected ? 'selected' : 'not-selected']">
                  {{ item.isSelected ? 'Y' : 'N' }}
                </span>
              </td>
              <td>{{ item.sourceModuleName }}</td>
              <td>{{ item.sourceModuleCode }}</td>
              <td>{{ item.targetModuleName }}</td>
              <td>{{ item.targetModuleCode }}</td>
              <td>{{ item.moduleRelationCode }}</td>
              <td>{{ item.objectRelationCodes.join(', ') }}</td>
              <td>
                <span v-if="item.annotationContent" :class="['annotation-tag', 'tag-' + (item.annotationCategory || 'info')]">
                  {{ getAnnotationIcon(item.annotationCategory) }}
                </span>
                <span v-if="item.annotationContent" class="annotation-preview" :title="item.annotationContent">
                  {{ truncateText(item.annotationContent, 20) }}
                </span>
                <span v-else class="no-annotation">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import ScopeSelector from './ScopeSelector.vue';
import ValidationPanel from './ValidationPanel.vue';
import RelationCategoryTree from './RelationCategoryTree.vue';
import { AppIcon } from './common/AppIcon';
import { validateData } from '../services/dataValidator.js';
import { validateRelationshipDescriptions as deepseekValidate, mockValidateDescriptions as deepseekMock } from '../services/deepseekValidator.js';
import { validateRelationshipDescriptions as zhipuValidate, mockValidateDescriptions as zhipuMock } from '../services/zhipuValidator.js';
import { buildRelationCategoryTree, getSelectedRelationCodes } from '../services/relationClassifier.js';

export default {
  name: 'DataPreview',
  components: {
    AppIcon,
    ScopeSelector,
    ValidationPanel,
    RelationCategoryTree
  },
  props: {
    previewData: {
      type: Object,
      required: true
    },
    rawData: {
      type: Object,
      default: null
    },
    modelValue: {
      type: Array,
      default: () => []
    },
    centerScope: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:modelValue', 'update:selectedStats', 'filter-by-relation', 'internal-relation-filter'],
  data() {
    return {
      activeTab: 'scopeSelector',
      activeRelationTab: 'objectRelation',
      selectedScope: this.modelValue,
      validationResult: null,
      isAIValidating: false,
      aiValidationDone: false,
      aiValidationItems: [],
      filterByRelationEnabled: true,
      internalRelationFilter: 'off',
      selectedRelationNodeIds: []
    };
  },
  computed: {
    // 计算带有选中状态的业务对象列表
    selectedBusinessObjects() {
      if (!this.previewData?.businessObjects) {
        return [];
      }
      const scopeSet = new Set(this.selectedScope);
      return this.previewData.businessObjects.map(bo => ({
        ...bo,
        isSelected: scopeSet.has(bo.code)
      }));
    },
    // 计算带有选中状态的服务模块列表
    selectedServiceModules() {
      if (!this.previewData?.serviceModules) {
        return [];
      }
      const scopeSet = new Set(this.selectedScope);
      return this.previewData.serviceModules.map(sm => {
        const relatedBoCodes = this.previewData.businessObjects
          ?.filter(bo => bo.serviceModule === sm.code)
          .map(bo => bo.code) || [];
        const hasSelectedBo = relatedBoCodes.some(code => scopeSet.has(code));
        return {
          ...sm,
          isSelected: hasSelectedBo
        };
      });
    },
    // 关系分类树
    relationCategoryTree() {
      if (!this.previewData?.relationships || !this.previewData?.businessObjects) {
        return [];
      }
      
      // 使用 centerScope（如果提供），否则使用 selectedScope
      const scope = this.centerScope && this.centerScope.length > 0 
        ? this.centerScope 
        : this.selectedScope;
      
      return buildRelationCategoryTree(
        this.previewData.relationships,
        scope,
        this.previewData.businessObjects
      );
    },
    // 过滤后的业务对象关系
    filteredBusinessObjectRelations() {
      if (!this.previewData?.relationships) {
        return [];
      }
      
      // 如果没有选中任何节点，显示所有关系
      if (!this.selectedRelationNodeIds || this.selectedRelationNodeIds.length === 0) {
        return this.previewData.relationships;
      }
      
      // 获取选中的关系编码
      const selectedRelationCodes = getSelectedRelationCodes(
        this.relationCategoryTree,
        this.selectedRelationNodeIds
      );
      
      const selectedCodesSet = new Set(selectedRelationCodes);
      
      // 分离选中和未选中的关系
      const selectedRelations = [];
      const unselectedRelations = [];
      
      this.previewData.relationships.forEach(relation => {
        if (selectedCodesSet.has(relation.relationCode)) {
          selectedRelations.push({ ...relation, isRelationScopeSelected: true });
        } else {
          unselectedRelations.push({ ...relation, isRelationScopeSelected: false });
        }
      });
      
      // 选中的关系排在前面
      return [...selectedRelations, ...unselectedRelations];
    },
    // 计算服务模块关系
    serviceModuleRelations() {
      if (!this.previewData?.relationships || !this.previewData?.businessObjects) {
        return [];
      }

      // 创建业务对象编码到服务模块的映射
      const boToModuleMap = new Map();
      this.previewData.businessObjects.forEach(bo => {
        if (bo.code) {
          boToModuleMap.set(bo.code, {
            moduleCode: bo.serviceModule,
            moduleName: bo.serviceModuleName || bo.serviceModule
          });
        }
      });

      // 创建服务模块编码到名称的映射
      const moduleCodeToNameMap = new Map();
      this.previewData.serviceModules?.forEach(sm => {
        if (sm.code) {
          moduleCodeToNameMap.set(sm.code, sm.name);
        }
      });

      // 按服务模块关系分组
      const moduleRelationMap = new Map();

      this.previewData.relationships.forEach(rel => {
        if (!rel.sourceCode || !rel.targetCode) return;

        const sourceBo = this.previewData.businessObjects?.find(bo => bo.code === rel.sourceCode);
        const targetBo = this.previewData.businessObjects?.find(bo => bo.code === rel.targetCode);

        if (!sourceBo || !targetBo) return;

        // 根据过滤级别判断是否是内部关系
        if (this.internalRelationFilter !== 'off') {
          let isInternal = false;
          if (this.internalRelationFilter === 'serviceModule') {
            isInternal = sourceBo.serviceModule === targetBo.serviceModule;
          } else if (this.internalRelationFilter === 'subDomain') {
            isInternal = sourceBo.subDomain === targetBo.subDomain;
          } else if (this.internalRelationFilter === 'domain') {
            isInternal = sourceBo.domain === targetBo.domain;
          }

          if (isInternal) {
            console.log(`[serviceModuleRelations] Skipping internal relation: ${rel.relationCode}, source=${rel.sourceCode}(${sourceBo.serviceModule}), target=${rel.targetCode}(${targetBo.serviceModule}), filter=${this.internalRelationFilter}`);
            return;
          }
        }

        const sourceModule = boToModuleMap.get(rel.sourceCode);
        const targetModule = boToModuleMap.get(rel.targetCode);

        if (!sourceModule?.moduleCode || !targetModule?.moduleCode) {
          console.log('[serviceModuleRelations] Skipping - missing module code');
          return;
        }

        const moduleRelationCode = `${sourceModule.moduleCode}-${targetModule.moduleCode}`;

        if (!moduleRelationMap.has(moduleRelationCode)) {
          moduleRelationMap.set(moduleRelationCode, {
            sourceModuleCode: sourceModule.moduleCode,
            sourceModuleName: moduleCodeToNameMap.get(sourceModule.moduleCode) || sourceModule.moduleCode,
            targetModuleCode: targetModule.moduleCode,
            targetModuleName: moduleCodeToNameMap.get(targetModule.moduleCode) || targetModule.moduleCode,
            moduleRelationCode: moduleRelationCode,
            objectRelationCodes: [],
            annotationContent: rel.annotationContent || '',
            annotationCategory: rel.annotationCategory || 'info',
            sourceBoCodes: [rel.sourceCode],
            targetBoCodes: [rel.targetCode],
            isInternal: sourceModule.moduleCode === targetModule.moduleCode
          });
        } else {
          const relation = moduleRelationMap.get(moduleRelationCode);
          if (!relation.sourceBoCodes.includes(rel.sourceCode)) {
            relation.sourceBoCodes.push(rel.sourceCode);
          }
          if (!relation.targetBoCodes.includes(rel.targetCode)) {
            relation.targetBoCodes.push(rel.targetCode);
          }
        }

        const relation = moduleRelationMap.get(moduleRelationCode);
        if (rel.relationCode && !relation.objectRelationCodes.includes(rel.relationCode)) {
          relation.objectRelationCodes.push(rel.relationCode);
        }
      });

      // 计算是否选中
      return Array.from(moduleRelationMap.values()).map(rel => {
        const allBoCodes = [...rel.sourceBoCodes, ...rel.targetBoCodes];
        const isSelected = allBoCodes.every(code => this.selectedScope.includes(code));
        return { ...rel, isSelected };
      });
    }
  },
  watch: {
    modelValue: {
      handler(newVal) {
        if (JSON.stringify(newVal) !== JSON.stringify(this.selectedScope)) {
          this.selectedScope = newVal;
        }
      },
      deep: true
    },
    selectedScope: {
      handler() {
        this.calculateSelectedStats();
      },
      deep: true
    },
    previewData: {
      handler() {
        this.runValidation();
        if (this.filterByRelationEnabled && this.previewData?.relationships?.length > 0) {
          this.$nextTick(() => {
            this.filterByRelations();
          });
        }
      },
      immediate: true
    },
    rawData: {
      handler() {
        this.runValidation();
      },
      immediate: true
    },
    internalRelationFilter: {
      handler() {
        console.log('[Watch] internalRelationFilter changed to:', this.internalRelationFilter);
      }
    }
  },
  mounted() {
    this.calculateSelectedStats();
    this.runValidation();
  },
  methods: {
    handleScopeChange(newVal) {
      console.log('[handleScopeChange] newVal includes PLD00604:', newVal.includes('PLD00604'));
      console.log('[handleScopeChange] newVal length:', newVal.length);
      this.selectedScope = newVal;
      this.$emit('update:modelValue', newVal);
      this.calculateSelectedStats();
      if (this.filterByRelationEnabled) {
        this.filterByRelations();
      }
    },
    handleFilterToggle() {
      console.log('[handleFilterToggle] filterByRelationEnabled:', this.filterByRelationEnabled);
      if (this.filterByRelationEnabled) {
        this.filterByRelations();
      } else {
        this.$emit('filter-by-relation', null);
        this.calculateSelectedStats();
      }
    },
    handleInternalRelationFilterChange() {
      this.$emit('internal-relation-filter', this.internalRelationFilter);
      if (this.filterByRelationEnabled) {
        this.filterByRelations();
      }
    },
    filterByRelations() {
      console.log('[Debug] filterByRelations called');
      console.log('[Debug] internalRelationFilter:', this.internalRelationFilter);
      console.log('[Debug] selectedScope:', this.selectedScope);
      
      if (!this.previewData?.relationships || this.previewData.relationships.length === 0) {
        console.log('[Debug] No relationships to filter');
        return;
      }

      const relationBoCodes = new Set();
      let skippedInternal = 0;
      let skippedNoCodes = 0;
      let processedCount = 0;

      this.previewData.relationships.forEach((rel, idx) => {
        console.log(`[Debug] Processing relationship ${idx}:`, rel);

        if (!rel.sourceCode || !rel.targetCode) {
          console.log(`[Debug] Skipping relationship ${idx} - missing sourceCode or targetCode`);
          skippedNoCodes++;
          return;
        }

        if (this.internalRelationFilter !== 'off') {
          const sourceBo = this.previewData.businessObjects?.find(bo => bo.code === rel.sourceCode);
          const targetBo = this.previewData.businessObjects?.find(bo => bo.code === rel.targetCode);

          if (sourceBo && targetBo) {
            let isInternal = false;
            if (this.internalRelationFilter === 'serviceModule') {
              isInternal = sourceBo.serviceModule === targetBo.serviceModule;
            } else if (this.internalRelationFilter === 'subDomain') {
              isInternal = sourceBo.subDomain === targetBo.subDomain;
            } else if (this.internalRelationFilter === 'domain') {
              isInternal = sourceBo.domain === targetBo.domain;
            }

            if (isInternal) {
              console.log(`[Debug] Skipping internal relation ${idx}: ${rel.relationCode}, source=${rel.sourceCode}(${sourceBo.serviceModule}), target=${rel.targetCode}(${targetBo.serviceModule}), filter=${this.internalRelationFilter}`);
              skippedInternal++;
              return;
            }
          }
        }

        relationBoCodes.add(rel.sourceCode);
        relationBoCodes.add(rel.targetCode);
        processedCount++;
      });

      console.log(`[Debug] Filter complete: processed=${processedCount}, skippedNoCodes=${skippedNoCodes}, skippedInternal=${skippedInternal}`);
      console.log('[Debug] relationBoCodes:', Array.from(relationBoCodes));

      if (this.selectedScope && this.selectedScope.length > 0) {
        const scopeSet = new Set(this.selectedScope);
        const intersection = Array.from(relationBoCodes).filter(code => scopeSet.has(code));
        console.log('[Debug] Emitting filtered intersection:', intersection);
        this.$emit('filter-by-relation', intersection);
      } else {
        console.log('[Debug] Emitting all relation codes (no scope selected):', Array.from(relationBoCodes));
        this.$emit('filter-by-relation', null);
      }
    },
    async runValidation() {
      if (this.rawData && this.previewData) {
        // 基础校验
        const baseResult = validateData(this.rawData, this.previewData);

        // 合并之前的AI校验结果（如果有）
        if (this.aiValidationItems.length > 0) {
          this.validationResult = {
            items: [...baseResult.items, ...this.aiValidationItems],
            summary: {
              total: baseResult.summary.total + this.aiValidationItems.length,
              error: baseResult.summary.error,
              warning: baseResult.summary.warning + this.aiValidationItems.filter(i => i.level === 'warning').length,
              info: baseResult.summary.info + this.aiValidationItems.filter(i => i.level === 'info').length
            }
          };
        } else {
          this.validationResult = baseResult;
        }
      } else {
        this.validationResult = null;
        this.aiValidationItems = [];
        this.aiValidationDone = false;
      }
    },

    async runAIValidation() {
      if (!this.rawData?.relationshipData || this.rawData.relationshipData.length === 0) {
        return;
      }

      this.isAIValidating = true;
      this.aiValidationDone = false;

      try {
        // 优先使用智谱AI（免费额度更多）
        let aiItems = [];
        let aiProvider = 'zhipu';

        try {
          console.log('尝试调用智谱AI API...');
          aiItems = await zhipuValidate(this.rawData.relationshipData);
          console.log('智谱AI校验完成');
        } catch (zhipuError) {
          console.log('智谱AI API调用失败:', zhipuError);

          // 智谱失败，尝试DeepSeek
          try {
            console.log('尝试调用DeepSeek API...');
            aiItems = await deepseekValidate(this.rawData.relationshipData);
            aiProvider = 'deepseek';
            console.log('DeepSeek校验完成');
          } catch (deepseekError) {
            console.log('DeepSeek API也调用失败，使用模拟校验');
            // 都失败时使用模拟校验
            aiItems = zhipuMock(this.rawData.relationshipData);
            aiProvider = 'mock';
          }
        }

        // 标记AI提供商
        aiItems.forEach(item => {
          item.aiProvider = aiProvider;
        });

        // 保存AI校验结果
        this.aiValidationItems = aiItems;
        this.aiValidationDone = true;

        // 重新运行基础校验以合并结果
        await this.runValidation();

      } catch (error) {
        console.error('AI校验失败:', error);
      } finally {
        this.isAIValidating = false;
      }
    },

    calculateSelectedStats() {
      const stats = {
        domains: 0,
        subDomains: 0,
        serviceModules: 0,
        businessObjects: 0,
        objectRelations: 0,
        serviceModuleRelations: 0
      };

      if (!this.selectedScope || this.selectedScope.length === 0 || !this.previewData) {
        this.$emit('update:selectedStats', stats);
        return;
      }

      const selectedDomainNames = new Set();
      const selectedSubDomainNames = new Set();
      const selectedServiceModuleNames = new Set();
      const scopeSet = new Set(this.selectedScope);

      this.previewData.domainProducts?.forEach(domain => {
        let domainHasSelected = false;
        
        domain.modules?.forEach(module => {
          let moduleHasSelected = false;
          
          module.submodules?.forEach(submodule => {
            let submoduleHasSelected = false;
            
            submodule.businessObjects?.forEach(bo => {
              const boId = typeof bo === 'string' ? bo : (bo.code || bo.name);
              if (this.selectedScope.includes(boId)) {
                submoduleHasSelected = true;
                moduleHasSelected = true;
                domainHasSelected = true;
                stats.businessObjects++;
              }
            });
            
            if (submoduleHasSelected) {
              selectedServiceModuleNames.add(`${domain.name}/${module.name}/${submodule.name}`);
            }
          });
          
          if (moduleHasSelected) {
            selectedSubDomainNames.add(`${domain.name}/${module.name}`);
          }
        });
        
        if (domainHasSelected) {
          selectedDomainNames.add(domain.name);
        }
      });

      stats.domains = selectedDomainNames.size;
      stats.subDomains = selectedSubDomainNames.size;
      stats.serviceModules = selectedServiceModuleNames.size;

      // 计算选中的业务对象关系数量
      if (this.previewData.relationships) {
        stats.objectRelations = this.previewData.relationships.filter(rel => 
          scopeSet.has(rel.sourceCode) && scopeSet.has(rel.targetCode)
        ).length;
      }

      // 计算选中的服务模块关系数量
      stats.serviceModuleRelations = this.serviceModuleRelations.filter(rel => rel.isSelected).length;

      this.$emit('update:selectedStats', stats);
    },
    getAnnotationIcon(category) {
      const icons = {
        important: 'important',
        warning: 'warning',
        info: 'info',
        tip: 'tip'
      };
      return icons[category] || icons.info;
    },
    truncateText(text, maxLength) {
      if (!text || text.length <= maxLength) return text || '';
      return text.substring(0, maxLength) + '...';
    },
    isRelationSelected(relation) {
      if (!this.selectedScope || this.selectedScope.length === 0) {
        return false;
      }
      const scopeSet = new Set(this.selectedScope);
      return scopeSet.has(relation.sourceCode) && scopeSet.has(relation.targetCode);
    },
    handleNodeToggle({ node, selected }) {
      console.log('[DataPreview] Node toggled:', node.id, 'selected:', selected);
      // 这里可以添加额外的逻辑，比如更新统计信息等
    }
  }
};
</script>

<style scoped>
.data-preview {
  margin-top: 0;
}

.preview-block {
  margin-bottom: 30px;
  padding: 20px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
}

.preview-block h3 {
  margin-top: 0;
  margin-bottom: 15px;
  color: #333;
}

.relation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.relation-header h3 {
  margin: 0;
}

.filter-by-relation-btn {
  padding: 6px 16px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-by-relation-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.filter-by-relation-btn:disabled {
  background: #d9d9d9;
  color: #999;
  cursor: not-allowed;
}

.filter-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.filter-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.filter-label {
  font-size: 14px;
  color: #333;
}

.filter-switch input[type="checkbox"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.switch-slider {
  position: relative;
  width: 40px;
  height: 22px;
  background-color: #ccc;
  transition: 0.3s;
  border-radius: 22px;
}

.switch-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.filter-switch input:checked + .switch-slider {
  background-color: var(--color-primary);
}

.filter-switch input:checked + .switch-slider:before {
  transform: translateX(18px);
}

.filter-switch input:disabled + .switch-slider {
  background-color: #e8e8e8;
  cursor: not-allowed;
}

.filter-switch input:disabled ~ .filter-label {
  color: #999;
}

.filter-select {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.filter-select select {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
  background-color: #fff;
  cursor: pointer;
}

.filter-select select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.filter-select select:disabled {
  background-color: #f5f5f5;
  cursor: not-allowed;
  color: #999;
}

.filter-select select:disabled + span {
  color: #999;
}

/* 页签样式 */
.tabs {
  display: flex;
  border-bottom: 1px solid #e8e8e8;
  margin-bottom: 15px;
}

.tab-btn {
  padding: 10px 20px;
  background: none;
  border: none;
  cursor: pointer;
  color: #666;
  font-size: 14px;
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom: 2px solid var(--color-primary);
}

/* 表格样式 */
.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e8e8e8;
}

th {
  background: #f5f7fa;
  font-weight: 600;
  color: #333;
}

tbody tr:hover {
  background: #f5f7fa;
}

/* AI校验区域 */
.ai-validation-section {
  margin-bottom: 20px;
}

/* AI校验加载状态 */
.ai-validating {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  color: var(--color-info-active);
  font-size: 14px;
}

.loading-icon {
  font-size: 18px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.loading-text {
  font-weight: 500;
}

/* AI校验触发按钮区域 */
.ai-validation-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  margin-bottom: 20px;
}

.ai-trigger-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-icon {
  font-size: 24px;
}

.ai-trigger-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ai-trigger-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.ai-trigger-desc {
  font-size: 13px;
  color: #606266;
}

.ai-trigger-btn {
  padding: 8px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
}

.ai-trigger-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.ai-trigger-btn:active {
  transform: translateY(0);
}

/* AI校验完成状态 */
.ai-validation-done {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  color: var(--color-info-active);
  font-size: 14px;
  margin-bottom: 20px;
}

.ai-retry-btn {
  margin-left: auto;
  padding: 4px 12px;
  background: #fff;
  border: 1px solid var(--color-info-border);
  border-radius: 4px;
  color: var(--color-info-active);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-retry-btn:hover {
  background: var(--color-info-bg);
}

/* 备注相关样式 */
.annotation-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  margin-right: 4px;
}

.annotation-preview {
  color: #666;
  font-size: 13px;
}

.no-annotation {
  color: #999;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.selected {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-badge.not-selected {
  background: #f5f5f5;
  color: #999;
}

.tag-important {
  color: #856404;
}

.tag-warning {
  color: #721c24;
}

.tag-info {
  color: #0066cc;
}

.tag-tip {
  color: #155724;
}

.internal-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: #fff7e6;
  color: #fa8c16;
  border: 1px solid #ffd591;
}

.external-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-disabled);
}

.internal-relation {
  background-color: #fffbf0;
}

.relation-scope-selected {
  background-color: var(--color-primary-bg);
}

.relation-scope-tab {
  padding: 15px 0;
}
</style>
