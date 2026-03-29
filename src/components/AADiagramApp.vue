<template>
  <div class="aa-diagram-app">
    <!-- 顶部标题栏 -->
    <header class="app-header">
      <div class="header-left">
        <button class="back-btn" @click="$emit('back-to-landing')">
          <span>←</span> 返回
        </button>
        <h1>AA图</h1>
      </div>
      <div class="header-stats" v-if="previewData">
        <div class="stat-item">
          <span class="stat-value">{{ selectedStats.domains }}/{{ stats.domains }}</span>
          <span class="stat-label">领域</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ selectedStats.subDomains }}/{{ stats.subDomains }}</span>
          <span class="stat-label">子领域</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ selectedStats.serviceModules }}/{{ stats.serviceModules }}</span>
          <span class="stat-label">服务模块</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ selectedStats.businessObjects }}/{{ stats.businessObjects }}</span>
          <span class="stat-label">业务对象</span>
        </div>
      </div>
    </header>

    <!-- 顶部步骤导航 -->
    <nav class="step-navigator">
      <div 
        v-for="(step, index) in steps" 
        :key="index"
        :class="['step-item', { 
          'active': currentStep === index, 
          'completed': currentStep > index,
          'disabled': !canAccessStep(index)
        }]"
        @click="goToStep(index)"
      >
        <div class="step-number">{{ index + 1 }}</div>
        <div class="step-content">
          <div class="step-title">{{ step.title }}</div>
        </div>
        <div v-if="index < steps.length - 1" class="step-arrow"></div>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 步骤 1: 数据来源 -->
      <div v-if="currentStep === 0" class="content-panel">
        <div class="panel-header">
          <h2>数据来源</h2>
          <p class="panel-desc">请选择包含业务对象和关系的Excel文件</p>
        </div>
        <div class="panel-body">
          <FileUploader
            :loading="loading"
            :error="error"
            button-text="选择Excel文件"
            @file-selected="handleFileSelected"
          />
        </div>
      </div>

      <!-- 步骤 2: 数据范围 -->
      <div v-if="currentStep === 1" class="content-panel">
        <div class="panel-header-simple">
          <button @click="nextStep" class="btn-primary">下一步 →</button>
        </div>
        <div class="panel-body no-padding-top">
          <DataPreview
            v-if="previewData"
            :preview-data="previewData"
            :raw-data="rawData"
            v-model="selectedScope"
            @update:selectedStats="updateSelectedStats"
          />
        </div>
      </div>

      <!-- 步骤 3: 展示配置 -->
      <div v-if="currentStep === 2" class="content-panel">
        <div class="panel-header-simple">
          <button @click="generateDiagram" class="btn-primary btn-large">
            下一步 →
          </button>
        </div>
        <div class="panel-body no-padding-top">
          <CenterDomainSelect
            v-if="previewData"
            v-model="selectedCenterDomain"
            v-model:colorGroupBy="colorGroupBy"
            v-model:centerDomainColor="centerDomainColor"
            v-model:colorScheme="colorScheme"
            v-model:textColor="textColor"
            :sub-domains="availableSubDomains"
            :domains="availableDomains"
          />
        </div>
      </div>

      <!-- 步骤 4: 展示 -->
      <div v-if="currentStep === 3" class="content-panel diagram-only-panel">
        <div class="panel-body diagram-panel">
          <div v-if="diagramData" class="diagram-container">
            <MermaidComponent
              :diagram-data="diagramData"
            />
          </div>
          <div v-else class="empty-state">
            <div class="empty-icon">📊</div>
            <p>图表尚未生成</p>
            <button @click="goToStep(2)" class="btn-primary">去配置参数</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
import { useExcelParser } from '../composables/useExcelParser.js';
import { extractSubDomains } from '../services/dataTransformer.js';
import { buildDiagramData } from '../services/diagramDataBuilder.js';
import FileUploader from './FileUploader.vue';
import DataPreview from './DataPreview.vue';
import CenterDomainSelect from './CenterDomainSelect.vue';
import MermaidComponent from './MermaidComponent.vue';

export default {
  name: 'AADiagramApp',
  components: {
    FileUploader,
    DataPreview,
    CenterDomainSelect,
    MermaidComponent
  },
  emits: ['back-to-landing'],
  setup() {
    const {
      loading,
      error,
      previewData,
      rawData,
      handleFileUpload,
      clearData
    } = useExcelParser();

    return {
      loading,
      error,
      previewData,
      rawData,
      handleFileUpload,
      clearData
    };
  },
  data() {
    return {
      currentStep: 0,
      steps: [
        { title: '导入', desc: '上传Excel文件' },
        { title: '范围', desc: '选择数据范围' },
        { title: '配置', desc: '设置图表参数' },
        { title: '展示', desc: '查看关系图' }
      ],
      selectedCenterDomain: '',
      colorGroupBy: 'subDomain',
      centerDomainColor: '#D9D9D9',
      colorScheme: 'default',
      textColor: 'black',
      selectedScope: [],
      diagramData: null,
      selectedStats: {
        domains: 0,
        subDomains: 0,
        serviceModules: 0,
        businessObjects: 0
      }
    };
  },
  computed: {
    availableSubDomains() {
      return extractSubDomains(this.previewData?.domainProducts);
    },
    availableDomains() {
      if (!this.previewData?.domainProducts) return [];
      return this.previewData.domainProducts.map(domain => domain.name);
    },
    stats() {
      if (!this.previewData) {
        return { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0 };
      }

      const domains = this.previewData.domainProducts?.length || 0;
      let subDomains = 0;
      let serviceModules = 0;

      this.previewData.domainProducts?.forEach(domain => {
        domain.modules?.forEach(module => {
          subDomains++;
          serviceModules += module.submodules?.length || 0;
        });
      });

      const businessObjects = this.previewData.businessObjects?.length || 0;

      return { domains, subDomains, serviceModules, businessObjects };
    }
  },
  methods: {
    canAccessStep(stepIndex) {
      if (stepIndex === 0) return true;
      if (stepIndex === 1) return !!this.previewData;
      if (stepIndex === 2) return !!this.previewData;
      if (stepIndex === 3) return !!this.diagramData;
      return false;
    },
    goToStep(index) {
      if (!this.canAccessStep(index)) return;
      this.currentStep = index;
    },
    nextStep() {
      if (this.currentStep < this.steps.length - 1) {
        this.currentStep++;
      }
    },
    async handleFileSelected(file) {
      await this.handleFileUpload(file);
      if (this.previewData && !this.error) {
        this.nextStep();
      }
    },
    updateSelectedStats(stats) {
      this.selectedStats = stats;
    },
    generateDiagram() {
      if (!this.previewData) return;

      this.diagramData = buildDiagramData({
        businessObjects: this.previewData.businessObjects,
        relationships: this.previewData.relationships,
        domainProducts: this.previewData.domainProducts,
        centerDomain: this.selectedCenterDomain,
        colorGroupBy: this.colorGroupBy,
        centerDomainColor: this.centerDomainColor,
        colorScheme: this.colorScheme,
        textColor: this.textColor
      });
      
      this.currentStep = 3;
    },
    resetAll() {
      this.currentStep = 0;
      this.selectedCenterDomain = '';
      this.colorGroupBy = 'domain';
      this.centerDomainColor = '#D9D9D9';
      this.colorScheme = 'default';
      this.textColor = 'black';
      this.selectedScope = [];
      this.diagramData = null;
      this.selectedStats = {
        domains: 0,
        subDomains: 0,
        serviceModules: 0,
        businessObjects: 0
      };
      this.clearData();
    }
  }
}
</script>

<style scoped>
.aa-diagram-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

/* 顶部标题栏 */
.app-header {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #f5f5f5;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  transition: all 0.2s;
}

.back-btn:hover {
  background: #e8e8e8;
  color: #333;
}

.app-header h1 {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.header-stats {
  display: flex;
  gap: 24px;
  flex: 1;
  justify-content: center;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.stat-label {
  font-size: 12px;
  color: #999;
}

/* 步骤导航 */
.step-navigator {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  background: white;
  border-bottom: 1px solid #e8e8e8;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 8px;
}

.step-item:hover:not(.disabled) {
  background: #f5f5f5;
}

.step-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.step-item.active {
  background: #e6f7ff;
}

.step-item.completed .step-number {
  background: #52c41a;
  color: white;
}

.step-number {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f0f0;
  border-radius: 50%;
  font-weight: 600;
  color: #666;
}

.step-item.active .step-number {
  background: #1890ff;
  color: white;
}

.step-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.step-arrow {
  width: 40px;
  height: 2px;
  background: #e0e0e0;
  margin: 0 8px;
}

/* 主内容区 */
.main-content {
  flex: 1;
  padding: 24px;
  overflow: auto;
}

.content-panel {
  max-width: 1200px;
  margin: 0 auto;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.panel-header {
  padding: 24px;
  border-bottom: 1px solid #f0f0f0;
}

.panel-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.panel-desc {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.panel-header-simple {
  padding: 16px 24px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: flex-end;
}

.panel-body {
  padding: 24px;
}

.panel-body.no-padding-top {
  padding-top: 0;
}

/* 按钮样式 */
.btn-primary {
  padding: 10px 24px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-primary.btn-large {
  padding: 12px 32px;
  font-size: 16px;
}

/* 图表展示 */
.diagram-only-panel {
  height: calc(100vh - 200px);
}

.diagram-panel {
  height: 100%;
  padding: 0;
}

.diagram-container {
  height: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
}

.empty-icon {
  font-size: 64px;
}

.empty-state p {
  font-size: 16px;
  color: #999;
}

/* ==================== 响应式设计 ==================== */

/* 平板设备 (768px - 1024px) */
@media screen and (max-width: 1024px) {
  .app-header {
    padding: 10px 20px;
  }

  .header-left h1 {
    font-size: 18px;
  }

  .header-stats {
    gap: 16px;
  }

  .stat-value {
    font-size: 18px;
  }

  .step-navigator {
    padding: 16px 20px;
    gap: 8px;
  }

  .step-title {
    font-size: 13px;
  }
}

/* 手机设备 (< 768px) */
@media screen and (max-width: 768px) {
  .app-header {
    padding: 10px 16px;
    grid-template-columns: auto 1fr;
    gap: 10px;
  }

  .header-left {
    gap: 10px;
  }

  .back-btn {
    padding: 6px 12px;
    font-size: 13px;
  }

  .header-left h1 {
    font-size: 16px;
  }

  .header-stats {
    width: 100%;
    justify-content: space-around;
    gap: 12px;
    padding-top: 8px;
    border-top: 1px solid #e8e8e8;
  }

  .stat-item {
    gap: 2px;
  }

  .stat-value {
    font-size: 16px;
  }

  .stat-label {
    font-size: 11px;
  }

  /* 步骤导航 - 简化显示 */
  .step-navigator {
    padding: 12px 16px;
    gap: 4px;
  }

  .step-item {
    flex: 1;
    min-width: 0;
  }

  .step-number {
    width: 28px;
    height: 28px;
    font-size: 13px;
  }

  .step-content {
    display: none; /* 手机隐藏步骤文字 */
  }

  .step-arrow {
    width: 16px;
    height: 16px;
  }

  /* 主内容区 */
  .main-content {
    padding: 16px;
  }

  .content-panel {
    border-radius: 8px;
  }

  .panel-header {
    padding: 20px;
  }

  .panel-header h2 {
    font-size: 18px;
  }

  .panel-header-simple {
    padding: 12px 16px;
  }

  .panel-body {
    padding: 16px;
  }

  .btn-primary {
    padding: 10px 20px;
    font-size: 14px;
  }

  .btn-large {
    padding: 12px 28px;
    font-size: 15px;
  }
}

/* 小屏手机 (< 480px) */
@media screen and (max-width: 480px) {
  .app-header {
    padding: 8px 12px;
  }

  .header-left h1 {
    font-size: 14px;
  }

  .back-btn span {
    font-size: 16px;
  }

  .header-stats {
    gap: 8px;
  }

  .stat-value {
    font-size: 14px;
  }

  .stat-label {
    font-size: 10px;
  }

  .step-navigator {
    padding: 10px 12px;
  }

  .step-number {
    width: 24px;
    height: 24px;
    font-size: 12px;
  }

  .main-content {
    padding: 12px;
  }

  .panel-header {
    padding: 16px;
  }

  .panel-header h2 {
    font-size: 16px;
  }

  .panel-desc {
    font-size: 13px;
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  .back-btn:hover {
    border-color: #d9d9d9;
    color: #666;
  }

  .back-btn:active {
    background: #f0f0f0;
  }

  .step-item:not(.disabled):hover {
    background: transparent;
  }

  .step-item:not(.disabled):active {
    background: rgba(24, 144, 255, 0.1);
  }

  .btn-primary:hover {
    background: #1890ff;
  }

  .btn-primary:active {
    background: #096dd9;
  }
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .aa-diagram-app {
    background: #1a1a1a;
  }

  .app-header {
    background: #2a2a2a;
    border-bottom-color: #3a3a3a;
  }

  .header-left h1 {
    color: #fff;
  }

  .back-btn {
    background: #3a3a3a;
    border-color: #4a4a4a;
    color: #ccc;
  }

  .back-btn:hover {
    border-color: #1890ff;
    color: #1890ff;
  }

  .stat-label {
    color: #999;
  }

  .step-navigator {
    background: #2a2a2a;
    border-bottom-color: #3a3a3a;
  }

  .step-item .step-number {
    background: #3a3a3a;
    color: #999;
  }

  .step-item.active .step-number {
    background: #1890ff;
    color: #fff;
  }

  .step-item.completed .step-number {
    background: #52c41a;
    color: #fff;
  }

  .step-title {
    color: #999;
  }

  .step-item.active .step-title {
    color: #1890ff;
  }

  .main-content {
    background: #1a1a1a;
  }

  .content-panel {
    background: #2a2a2a;
  }

  .panel-header h2 {
    color: #fff;
  }

  .panel-desc {
    color: #999;
  }

  .empty-state p {
    color: #666;
  }
}
</style>