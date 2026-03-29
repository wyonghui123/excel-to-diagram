<template>
  <div class="service-module-config">
    <!-- 第一行：中心子领域 + 中心子领域颜色 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">中心子领域</label>
        <select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)" class="form-select">
          <option value="">无中心子领域</option>
          <option v-for="subDomain in subDomains" :key="subDomain" :value="subDomain">
            {{ subDomain }}
          </option>
        </select>
      </div>
      <div class="form-item">
        <label class="form-label">中心子领域颜色</label>
        <div class="color-picker-wrapper">
          <input
            type="color"
            :value="centerDomainColor"
            @change="$emit('update:centerDomainColor', $event.target.value)"
            class="color-picker"
          />
          <span class="color-value">{{ centerDomainColor }}</span>
          <button @click="$emit('update:centerDomainColor', '#D9D9D9')" class="reset-btn" title="重置为默认">↺</button>
        </div>
      </div>
    </div>

    <!-- 第二行：颜色分组方式 + 颜色组合 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">颜色分组方式</label>
        <select :value="colorGroupBy" @change="$emit('update:colorGroupBy', $event.target.value)" class="form-select">
          <option value="domain">按领域区分颜色</option>
          <option value="subDomain">按子领域区分颜色</option>
        </select>
      </div>
      <div class="form-item">
        <label class="form-label">颜色组合</label>
        <select :value="colorScheme" @change="$emit('update:colorScheme', $event.target.value)" class="form-select">
          <option value="default">默认组合</option>
          <option value="vibrant">鲜艳组合</option>
          <option value="pastel">柔和组合</option>
          <option value="warm">暖色组合</option>
          <option value="cool">冷色组合</option>
          <option value="business">商务组合</option>
          <option value="nature">自然组合</option>
        </select>
      </div>
    </div>

    <!-- 第三行：建议颜色分配 -->
    <div class="form-row" v-if="groupedItems.length > 0">
      <div class="form-item full-width">
        <label class="form-label">建议颜色分配（不含中心子领域）</label>
        <div class="suggestion-list">
          <div v-for="(item, index) in groupedItems" :key="item.name" class="suggestion-item">
            <span class="color-dot" :style="{ backgroundColor: item.color }"></span>
            <span class="item-name">{{ item.name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 第四行：服务模块标题文字颜色 -->
    <div class="form-row">
      <div class="form-item full-width">
        <label class="form-label">服务模块标题文字颜色</label>
        <div class="text-color-options">
          <label 
            v-for="color in textColors" 
            :key="color.value"
            class="color-option"
            :class="{ 'is-selected': serviceModuleTextColor === color.value }"
            @click="$emit('update:serviceModuleTextColor', color.value)"
          >
            <input
              type="radio"
              :value="color.value"
              :checked="serviceModuleTextColor === color.value"
            />
            <span class="color-preview" :style="{ backgroundColor: color.preview }"></span>
            <span class="color-label">{{ color.label }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 颜色组合配置
const COLOR_SCHEMES = [
  {
    value: 'default',
    label: '默认组合',
    colors: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB']
  },
  {
    value: 'vibrant',
    label: '鲜艳组合',
    colors: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788']
  },
  {
    value: 'pastel',
    label: '柔和组合',
    colors: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6']
  },
  {
    value: 'warm',
    label: '暖色组合',
    colors: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF']
  },
  {
    value: 'cool',
    label: '冷色组合',
    colors: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF']
  },
  {
    value: 'business',
    label: '商务组合',
    colors: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B']
  },
  {
    value: 'nature',
    label: '自然组合',
    colors: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
  }
];

export default {
  name: 'ServiceModuleConfig',
  props: {
    modelValue: String,
    colorGroupBy: String,
    centerDomainColor: String,
    colorScheme: {
      type: String,
      default: 'default'
    },
    serviceModuleTextColor: {
      type: String,
      default: 'black'
    },
    subDomains: Array,
    domains: Array
  },
  emits: [
    'update:modelValue',
    'update:colorGroupBy',
    'update:centerDomainColor',
    'update:colorScheme',
    'update:serviceModuleTextColor'
  ],
  data() {
    return {
      textColors: [
        { value: 'black', label: '黑色', preview: '#000000' },
        { value: 'gray', label: '灰色', preview: '#808080' },
        { value: 'white', label: '白色', preview: '#FFFFFF' }
      ]
    }
  },
  computed: {
    // 获取当前颜色方案
    currentColorScheme() {
      return COLOR_SCHEMES.find(scheme => scheme.value === this.colorScheme) || COLOR_SCHEMES[0];
    },
    // 获取实际的中心子领域（如果未选择则默认为第一个）
    actualCenterSubDomain() {
      return this.modelValue || (this.subDomains && this.subDomains[0]) || '';
    },
    // 根据分组方式获取分组项目
    groupedItems() {
      const items = [];
      const colors = this.currentColorScheme.colors;
      const centerValue = this.actualCenterSubDomain;
      
      if (this.colorGroupBy === 'domain') {
        // 按领域分组
        (this.domains || []).forEach((domain, index) => {
          if (domain !== centerValue) { // 排除中心领域
            items.push({
              name: domain,
              color: colors[index % colors.length]
            });
          }
        });
      } else {
        // 按子领域分组
        (this.subDomains || []).forEach((subDomain, index) => {
          if (subDomain !== centerValue) { // 排除中心子领域
            items.push({
              name: subDomain,
              color: colors[index % colors.length]
            });
          }
        });
      }
      
      return items;
    }
  }
}
</script>

<style scoped>
.service-module-config {
  padding: 20px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

/* 表单行布局 */
.form-row {
  display: flex;
  gap: 30px;
  margin-bottom: 20px;
  align-items: flex-start;
}

.form-row:last-of-type {
  margin-bottom: 0;
}

/* 表单项 */
.form-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-item.full-width {
  flex: 2;
}

/* 表单标签 */
.form-label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
  white-space: nowrap;
}

/* 下拉选择框 */
.form-select {
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  background: white;
  width: 100%;
  box-sizing: border-box;
}

.form-select:focus {
  outline: none;
  border-color: #1890ff;
}

/* 颜色选择器 */
.color-picker-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.color-picker {
  width: 50px;
  height: 36px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  padding: 2px;
}

.color-value {
  font-size: 14px;
  color: #666;
  font-family: monospace;
}

.reset-btn {
  padding: 6px 10px;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
}

.reset-btn:hover {
  background: #e8e8e8;
  border-color: #1890ff;
  color: #1890ff;
}

/* 文字颜色选项 */
.text-color-options {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.color-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 2px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.color-option:hover {
  border-color: #1890ff;
}

.color-option.is-selected {
  border-color: #1890ff;
  background: #e6f7ff;
}

.color-option input[type="radio"] {
  display: none;
}

.color-preview {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid #d9d9d9;
}

.color-label {
  font-size: 14px;
  color: #333;
}

/* 建议颜色分配 */
.suggestion-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
}

.color-dot {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.item-name {
  color: #333;
}
</style>
