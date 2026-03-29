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
        <span class="loading-icon">🤖</span>
        <span class="loading-text">智谱AI正在检查关系说明的可读性...</span>
      </div>

      <!-- AI校验触发按钮 -->
      <div v-else-if="!aiValidationDone && rawData?.relationshipData?.length > 0" class="ai-validation-trigger">
        <div class="ai-trigger-info">
          <span class="ai-icon">🤖</span>
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
        <span class="ai-icon">✅</span>
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
          :model-value="selectedScope"
          :auto-select-all="true"
          @update:model-value="handleScopeChange"
        />
      </div>

      <!-- 业务对象表格 -->
      <div v-if="activeTab === 'businessObject'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>业务对象名称</th>
              <th>业务对象编码</th>
              <th>所属服务模块</th>
              <th>所属子领域</th>
              <th>所属领域</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in previewData.businessObjects" :key="idx">
              <td>{{ item.name }}</td>
              <td>{{ item.code || '-' }}</td>
              <td>{{ item.serviceModuleName || item.serviceModule || '-' }}</td>
              <td>{{ item.subDomain || '-' }}</td>
              <td>{{ item.domain || '-' }}</td>
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

      <!-- 服务模块表格 -->
      <div v-if="activeTab === 'serviceModule'" class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>服务模块名称</th>
              <th>服务模块编码</th>
              <th>所属子领域</th>
              <th>所属领域</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in previewData.serviceModules" :key="idx">
              <td>{{ item.name }}</td>
              <td>{{ item.code || '-' }}</td>
              <td>{{ item.subDomain || '-' }}</td>
              <td>{{ item.domain || '-' }}</td>
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

    <!-- 业务对象关系 - 双页签 -->
    <div class="preview-block">
      <h3>业务对象关系</h3>
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
              <th>源业务对象名称</th>
              <th>目标业务对象名称</th>
              <th>关系编码</th>
              <th>关系说明</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in previewData.relationships" :key="idx">
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
            <tr v-for="(item, idx) in serviceModuleRelations" :key="idx">
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
import { validateData } from '../services/dataValidator.js';
import { validateRelationshipDescriptions as deepseekValidate, mockValidateDescriptions as deepseekMock } from '../services/deepseekValidator.js';
import { validateRelationshipDescriptions as zhipuValidate, mockValidateDescriptions as zhipuMock } from '../services/zhipuValidator.js';

export default {
  name: 'DataPreview',
  components: {
    ScopeSelector,
    ValidationPanel
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
    }
  },
  emits: ['update:modelValue', 'update:selectedStats'],
  data() {
    return {
      activeTab: 'scopeSelector',
      activeRelationTab: 'objectRelation',
      selectedScope: this.modelValue,
      validationResult: null,
      isAIValidating: false,
      aiValidationDone: false,
      aiValidationItems: []
    };
  },
  computed: {
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

        // 获取源和目标业务对象所属的服务模块
        const sourceModule = boToModuleMap.get(rel.sourceCode);
        const targetModule = boToModuleMap.get(rel.targetCode);

        if (!sourceModule?.moduleCode || !targetModule?.moduleCode) return;

        // 服务模块关系编码
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
            annotationCategory: rel.annotationCategory || 'info'
          });
        }

        // 添加业务对象关系编码
        const relation = moduleRelationMap.get(moduleRelationCode);
        if (rel.relationCode && !relation.objectRelationCodes.includes(rel.relationCode)) {
          relation.objectRelationCodes.push(rel.relationCode);
        }
      });

      return Array.from(moduleRelationMap.values());
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
      },
      immediate: true
    },
    rawData: {
      handler() {
        this.runValidation();
      },
      immediate: true
    }
  },
  mounted() {
    this.calculateSelectedStats();
    this.runValidation();
  },
  methods: {
    handleScopeChange(newVal) {
      this.selectedScope = newVal;
      this.$emit('update:modelValue', newVal);
      this.calculateSelectedStats();
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
        businessObjects: 0
      };

      if (!this.selectedScope || this.selectedScope.length === 0 || !this.previewData) {
        this.$emit('update:selectedStats', stats);
        return;
      }

      const selectedDomainNames = new Set();
      const selectedSubDomainNames = new Set();
      const selectedServiceModuleNames = new Set();

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

      this.$emit('update:selectedStats', stats);
    },
    getAnnotationIcon(category) {
      const icons = {
        important: '⚠️',
        warning: '🚨',
        info: 'ℹ️',
        tip: '💡'
      };
      return icons[category] || icons.info;
    },
    truncateText(text, maxLength) {
      if (!text || text.length <= maxLength) return text || '';
      return text.substring(0, maxLength) + '...';
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
  color: #1890ff;
  border-bottom: 2px solid #1890ff;
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
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 8px;
  color: #096dd9;
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
  background: #f0f9ff;
  border: 1px solid #bae0ff;
  border-radius: 8px;
  color: #096dd9;
  font-size: 14px;
  margin-bottom: 20px;
}

.ai-retry-btn {
  margin-left: auto;
  padding: 4px 12px;
  background: #fff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #096dd9;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-retry-btn:hover {
  background: #e6f7ff;
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
</style>
