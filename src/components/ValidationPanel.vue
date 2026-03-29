<template>
  <div class="validation-panel" v-if="validationResult && validationResult.items.length > 0">
    <!-- 汇总信息栏 -->
    <div class="validation-summary" @click="toggleExpand">
      <div class="summary-left">
        <span class="summary-icon">⚠️</span>
        <span class="summary-title">数据校验结果</span>
        <span class="summary-count error" v-if="summary.error > 0">
          {{ summary.error }} 个错误
        </span>
        <span class="summary-count warning" v-if="summary.warning > 0">
          {{ summary.warning }} 个警告
        </span>
        <span class="summary-count info" v-if="summary.info > 0">
          {{ summary.info }} 个提示
        </span>
      </div>
      <div class="summary-right">
        <span class="expand-icon">{{ isExpanded ? '▼' : '▶' }}</span>
      </div>
    </div>

    <!-- 详细列表 -->
    <div class="validation-details" v-show="isExpanded">
      <div class="details-header">
        <div class="filter-tabs">
          <button 
            :class="['filter-tab', { active: activeFilter === 'all' }]"
            @click.stop="activeFilter = 'all'"
          >
            全部 ({{ summary.total }})
          </button>
          <button 
            :class="['filter-tab', { active: activeFilter === 'error' }]"
            @click.stop="activeFilter = 'error'"
            v-if="summary.error > 0"
          >
            错误 ({{ summary.error }})
          </button>
          <button 
            :class="['filter-tab', { active: activeFilter === 'warning' }]"
            @click.stop="activeFilter = 'warning'"
            v-if="summary.warning > 0"
          >
            警告 ({{ summary.warning }})
          </button>
          <button 
            :class="['filter-tab', { active: activeFilter === 'info' }]"
            @click.stop="activeFilter = 'info'"
            v-if="summary.info > 0"
          >
            提示 ({{ summary.info }})
          </button>
        </div>
      </div>

      <div class="details-list">
        <div
          v-for="(item, index) in filteredItems"
          :key="index"
          :class="['validation-item', item.level]"
        >
          <div class="item-row">
            <span class="level-badge" :class="item.level">
              {{ levelShortText(item.level) }}
            </span>
            <span v-if="item.type === 'ai_check'" class="ai-badge" :title="aiProviderText(item.aiProvider)">
              {{ aiProviderLabel(item.aiProvider) }}
            </span>
            <span class="item-location">{{ item.sheet }}·{{ item.row }}行</span>
            <span class="item-field-name" v-if="item.field">·{{ item.field }}</span>
          </div>

          <!-- 编码信息 -->
          <div v-if="item.entityCode || item.relationCode" class="entity-code-info">
            <span class="code-label">{{ getEntityTypeLabel(item.sheet) }}:</span>
            <span class="code-value">{{ item.entityCode || item.relationCode }}</span>
          </div>

          <!-- AI校验额外信息 -->
          <div v-if="item.type === 'ai_check'" class="ai-extra-info">
            <div class="ai-info-row" v-if="item.relationCode && !item.entityCode">
              <span class="ai-info-label">关系编码:</span>
              <span class="ai-info-value code">{{ item.relationCode }}</span>
            </div>
            <div class="ai-info-row" v-if="item.checkedText">
              <span class="ai-info-label">检查内容:</span>
              <span class="ai-info-value text">{{ item.checkedText }}</span>
            </div>
          </div>

          <div class="item-message">{{ item.message }}</div>
          <div class="item-suggestion" v-if="item.suggestion">
            💡 {{ item.suggestion }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ValidationPanel',
  props: {
    validationResult: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      isExpanded: false,
      activeFilter: 'all'
    };
  },
  computed: {
    summary() {
      return this.validationResult?.summary || { total: 0, error: 0, warning: 0, info: 0 };
    },
    filteredItems() {
      if (!this.validationResult?.items) return [];
      if (this.activeFilter === 'all') return this.validationResult.items;
      return this.validationResult.items.filter(item => item.level === this.activeFilter);
    }
  },
  methods: {
    toggleExpand() {
      this.isExpanded = !this.isExpanded;
    },
    levelText(level) {
      const map = {
        error: '错误',
        warning: '警告',
        info: '提示'
      };
      return map[level] || level;
    },
    levelShortText(level) {
      const map = {
        error: '错',
        warning: '警',
        info: '提'
      };
      return map[level] || level;
    },
    aiProviderLabel(provider) {
      const map = {
        zhipu: '智谱',
        deepseek: 'DS',
        mock: 'AI'
      };
      return map[provider] || 'AI';
    },
    aiProviderText(provider) {
      const map = {
        zhipu: '智谱AI (GLM-4)',
        deepseek: 'DeepSeek AI',
        mock: '模拟AI校验'
      };
      return map[provider] || 'AI校验';
    },
    getEntityTypeLabel(sheet) {
      const map = {
        '业务对象': '业务对象编码',
        '服务模块': '服务模块编码',
        '业务对象关系': '关系编码'
      };
      return map[sheet] || '编码';
    }
  }
};
</script>

<style scoped>
.validation-panel {
  margin-bottom: 16px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
  font-size: 12px;
}

/* 汇总信息栏 */
.validation-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #fafafa;
  cursor: pointer;
  transition: background 0.2s;
}

.validation-summary:hover {
  background: #f0f0f0;
}

.summary-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-icon {
  font-size: 16px;
}

.summary-title {
  font-weight: 600;
  font-size: 13px;
  color: #333;
}

.summary-count {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}

.summary-count.error {
  background: #fff1f0;
  color: #cf1322;
  border: 1px solid #ffa39e;
}

.summary-count.warning {
  background: #fffbe6;
  color: #d48806;
  border: 1px solid #ffd666;
}

.summary-count.info {
  background: #e6f7ff;
  color: #096dd9;
  border: 1px solid #91d5ff;
}

.summary-right {
  display: flex;
  align-items: center;
}

.expand-icon {
  font-size: 11px;
  color: #999;
}

/* 详细列表 */
.validation-details {
  border-top: 1px solid #e8e8e8;
}

.details-header {
  padding: 8px 12px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
}

.filter-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-tab {
  padding: 3px 8px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
  color: #666;
  transition: all 0.2s;
}

.filter-tab:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.filter-tab.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}

/* 校验项列表 */
.details-list {
  max-height: 300px;
  overflow-y: auto;
  padding: 6px;
}

.validation-item {
  padding: 8px 10px;
  margin-bottom: 4px;
  border-radius: 4px;
  border-left: 3px solid;
  background: #fafafa;
  font-size: 11px;
  line-height: 1.4;
}

.validation-item:last-child {
  margin-bottom: 0;
}

.validation-item.error {
  border-left-color: #ff4d4f;
  background: #fff1f0;
}

.validation-item.warning {
  border-left-color: #faad14;
  background: #fffbe6;
}

.validation-item.info {
  border-left-color: #1890ff;
  background: #e6f7ff;
}

.item-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.level-badge {
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 600;
}

.level-badge.error {
  background: #ff4d4f;
  color: #fff;
}

.level-badge.warning {
  background: #faad14;
  color: #fff;
}

.level-badge.info {
  background: #1890ff;
  color: #fff;
}

.item-location {
  font-size: 10px;
  color: #999;
}

.item-field-name {
  font-size: 10px;
  color: #666;
}

.item-message {
  font-size: 11px;
  color: #333;
  margin-bottom: 3px;
}

.item-suggestion {
  font-size: 10px;
  color: #666;
  padding: 4px 6px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 3px;
  margin-top: 4px;
}

/* AI校验标识 */
.ai-badge {
  padding: 1px 4px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 2px;
  font-size: 9px;
  font-weight: 600;
}

/* AI校验额外信息 */
.ai-extra-info {
  margin: 4px 0;
  padding: 4px 6px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 3px;
  font-size: 10px;
}

.ai-info-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-bottom: 2px;
}

.ai-info-row:last-child {
  margin-bottom: 0;
}

.ai-info-label {
  color: #999;
  flex-shrink: 0;
}

.ai-info-value {
  color: #333;
}

.ai-info-value.code {
  font-family: monospace;
  background: rgba(102, 126, 234, 0.1);
  padding: 1px 4px;
  border-radius: 2px;
  color: #667eea;
  font-weight: 500;
}

.ai-info-value.text {
  color: #666;
  font-style: italic;
  word-break: break-all;
}

/* 实体编码信息 */
.entity-code-info {
  margin: 4px 0;
  padding: 3px 6px;
  background: rgba(24, 144, 255, 0.08);
  border-radius: 3px;
  font-size: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.code-label {
  color: #999;
  flex-shrink: 0;
}

.code-value {
  font-family: monospace;
  background: rgba(24, 144, 255, 0.15);
  padding: 1px 4px;
  border-radius: 2px;
  color: #1890ff;
  font-weight: 500;
}
</style>
