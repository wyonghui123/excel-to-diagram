<template>
  <div class="center-domain-select">
    <!-- 第一行：中心子领域 + 颜色 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">{{ label }}</label>
        <div class="expandable-select">
          <div 
            class="select-trigger"
            :class="{ 'is-open': isDropdownOpen }"
            @click="toggleDropdown"
          >
            <span class="selected-text">{{ selectedText }}</span>
            <span class="arrow-icon">▼</span>
          </div>
          <div v-if="isDropdownOpen" class="select-dropdown">
            <div 
              class="dropdown-item"
              :class="{ 'is-selected': modelValue === '' }"
              @click="selectItem('')"
            >
              {{ placeholder }}
            </div>
            <div 
              v-for="subDomain in subDomains" 
              :key="subDomain"
              class="dropdown-item"
              :class="{ 'is-selected': modelValue === subDomain }"
              @click="selectItem(subDomain)"
            >
              {{ subDomain }}
            </div>
          </div>
        </div>
      </div>
      <div class="form-item">
        <label class="form-label">中心子领域颜色</label>
        <div class="color-picker-wrapper">
          <input
            type="color"
            :value="centerDomainColor"
            @change="onCenterColorChange"
            class="color-picker"
          />
          <span class="color-value">{{ centerDomainColor }}</span>
          <button @click="resetCenterColor" class="reset-btn" title="重置为默认">↺</button>
        </div>
      </div>
    </div>

    <!-- 第二行：颜色分组方式 + 颜色组合 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">颜色分组维度</label>
        <select :value="colorGroupBy" @change="onColorGroupChange" class="form-select">
          <option value="domain">按领域区分颜色</option>
          <option value="subDomain">按子领域区分颜色</option>
        </select>
      </div>
      <div class="form-item">
        <label class="form-label">颜色组合</label>
        <select :value="colorScheme" @change="onColorSchemeChange" class="form-select">
          <option v-for="scheme in colorSchemes" :key="scheme.value" :value="scheme.value">
            {{ scheme.label }}
          </option>
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

    <!-- 第四行：文字颜色 -->
    <div class="form-row">
      <div class="form-item full-width">
        <label class="form-label">业务对象标题文字颜色</label>
        <div class="text-color-options">
          <label 
            v-for="color in textColors" 
            :key="color.value"
            class="color-option"
            :class="{ 'is-selected': textColor === color.value }"
            @click="selectTextColor(color.value)"
          >
            <input
              type="radio"
              :value="color.value"
              :checked="textColor === color.value"
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
// 颜色组合配置（排除浅灰色）
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

// 默认中心子领域颜色（浅灰色）
const DEFAULT_CENTER_COLOR = '#D9D9D9';

export default {
  name: 'CenterDomainSelect',
  props: {
    modelValue: {
      type: String,
      default: ''
    },
    colorGroupBy: {
      type: String,
      default: 'domain'
    },
    centerDomainColor: {
      type: String,
      default: DEFAULT_CENTER_COLOR
    },
    colorScheme: {
      type: String,
      default: 'default'
    },
    textColor: {
      type: String,
      default: 'black'
    },
    subDomains: {
      type: Array,
      default: () => []
    },
    domains: {
      type: Array,
      default: () => []
    },
    label: {
      type: String,
      default: '中心子领域：'
    },
    placeholder: {
      type: String,
      default: '无中心子领域'
    }
  },
  emits: ['update:modelValue', 'update:colorGroupBy', 'update:centerDomainColor', 'update:colorScheme', 'update:textColor'],
  data() {
    return {
      colorSchemes: COLOR_SCHEMES,
      defaultCenterColor: DEFAULT_CENTER_COLOR,
      isDropdownOpen: false,
      textColors: [
        { value: 'black', label: '黑色', preview: '#000000' },
        { value: 'gray', label: '灰色', preview: '#666666' },
        { value: 'white', label: '白色', preview: '#FFFFFF' }
      ]
    };
  },
  computed: {
    selectedText() {
      if (!this.modelValue) return this.placeholder;
      return this.modelValue;
    },
    // 根据颜色分组方式和颜色组合计算建议的颜色分配（剔除中心子领域）
    groupedItems() {
      const items = [];
      const scheme = COLOR_SCHEMES.find(s => s.value === this.colorScheme) || COLOR_SCHEMES[0];
      const colors = scheme.colors;

      // 获取要分组的项目列表
      let groupItems = [];
      if (this.colorGroupBy === 'subDomain') {
        groupItems = this.subDomains || [];
      } else {
        groupItems = this.domains || [];
      }

      if (groupItems.length === 0) return [];

      // 剔除中心子领域，只为其他项目分配颜色
      const otherItems = groupItems.filter(item => item !== this.modelValue);
      
      otherItems.forEach((item, index) => {
        items.push({
          name: item,
          color: colors[index % colors.length]
        });
      });

      return items;
    }
  },
  methods: {
    toggleDropdown() {
      this.isDropdownOpen = !this.isDropdownOpen;
    },
    selectItem(value) {
      this.$emit('update:modelValue', value);
      this.isDropdownOpen = false;
    },
    onColorGroupChange(event) {
      this.$emit('update:colorGroupBy', event.target.value);
    },
    onCenterColorChange(event) {
      this.$emit('update:centerDomainColor', event.target.value);
    },
    onColorSchemeChange(event) {
      this.$emit('update:colorScheme', event.target.value);
    },
    selectTextColor(value) {
      this.$emit('update:textColor', value);
    },
    resetCenterColor() {
      this.$emit('update:centerDomainColor', this.defaultCenterColor);
    }
  },
  mounted() {
    // 点击外部关闭下拉框
    document.addEventListener('click', (e) => {
      if (!this.$el.contains(e.target)) {
        this.isDropdownOpen = false;
      }
    });
  }
};
</script>

<style scoped>
.center-domain-select {
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

/* 展开选择器样式 */
.expandable-select {
  position: relative;
  min-width: 200px;
}

.select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.select-trigger:hover {
  border-color: #1890ff;
}

.select-trigger.is-open {
  border-color: #1890ff;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.selected-text {
  font-size: 14px;
  color: #333;
}

.arrow-icon {
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
}

.select-trigger.is-open .arrow-icon {
  transform: rotate(180deg);
}

.select-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #1890ff;
  border-top: none;
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.dropdown-item {
  padding: 10px 12px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s;
}

.dropdown-item:hover {
  background: #e6f7ff;
}

.dropdown-item.is-selected {
  background: #1890ff;
  color: white;
}

/* 颜色选择器样式 */
.color-picker-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.color-picker {
  width: 50px;
  height: 32px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  padding: 2px;
  background: white;
}

.color-picker:focus {
  outline: none;
  border-color: #1890ff;
}

.color-value {
  font-family: monospace;
  font-size: 13px;
  color: #666;
  min-width: 70px;
}

.reset-btn {
  padding: 4px 8px;
  background: #f0f0f0;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.reset-btn:hover {
  background: #e0e0e0;
  border-color: #1890ff;
}

/* 颜色建议样式 */
.color-suggestions {
  margin-top: 12px;
  padding: 12px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.suggestion-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
  font-size: 13px;
}

.suggestion-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}

.color-dot {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
}

.item-name {
  font-size: 12px;
  color: #555;
  white-space: nowrap;
}

/* 文字颜色选择样式 */
.text-color-options {
  display: flex;
  gap: 16px;
}

.color-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: white;
  border: 2px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.color-option:hover {
  border-color: #1890ff;
}

.color-option.is-selected {
  border-color: #1890ff;
  background: #e6f7ff;
}

.color-option input {
  display: none;
}

.color-preview {
  width: 20px;
  height: 20px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.2);
  flex-shrink: 0;
}

.color-label {
  font-size: 14px;
  color: #333;
}
</style>
