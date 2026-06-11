<template>
  <div class="service-module-config">
    <!-- 第一行：区分中心范围开关 + 中心范围服务模块背景颜色 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label checkbox-label">
          <input
            type="checkbox"
            :checked="centerScopeHighlight"
            @change="$emit('update:centerScopeHighlight', $event.target.checked)"
          />
          <span>区分中心范围</span>
        </label>
      </div>
      <div class="form-item color-picker-wrapper" v-if="centerScopeHighlight">
        <label class="form-label">中心范围服务模块背景颜色</label>
        <input
          type="color"
          :value="centerScopeColor"
          @input="$emit('update:centerScopeColor', $event.target.value)"
          class="form-color-picker"
        />
      </div>
    </div>

    <!-- 第二行：颜色分组维度 + 颜色组合 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">颜色分组维度</label>
        <select :value="colorGroupBy" @change="$emit('update:colorGroupBy', $event.target.value)" class="form-select">
          <option value="domain">按领域区分颜色</option>
          <option value="subDomain">按子领域区分颜色</option>
          <option value="serviceModule">按服务模块区分颜色</option>
        </select>
      </div>
      <div class="form-item">
        <label class="form-label">颜色组合</label>
        <select :value="colorScheme" @change="$emit('update:colorScheme', $event.target.value)" class="form-select">
          <option v-for="scheme in colorSchemes" :key="scheme.value" :value="scheme.value">
            {{ scheme.label }}
          </option>
        </select>
      </div>
    </div>

    <!-- 颜色分配 -->
    <div class="form-row" v-if="groupedItems.length > 0">
      <div class="form-item full-width">
        <label class="form-label">颜色分配</label>
        <div class="suggestion-list">
          <div v-for="(item, index) in groupedItems" :key="item.name" class="suggestion-item">
            <span class="color-dot" :style="{ backgroundColor: item.color }" @click="openColorPicker(item.name, item.color)"></span>
            <span class="item-name" :class="{ 'is-center': item.isCenter }">{{ item.name }}</span>
            <span v-if="item.isCenter" class="center-badge">含中心</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 服务模块标题文字颜色 -->
    <div class="form-row">
      <div class="form-item">
        <label class="form-label">服务模块标题文字颜色</label>
        <div class="text-color-options">
          <label
            v-for="color in textColors"
            :key="color.value"
            class="color-option"
            :class="{ 'is-selected': nodeTextColor === color.value }"
            @click="$emit('update:nodeTextColor', color.value)"
          >
            <input
              type="radio"
              :value="color.value"
              :checked="nodeTextColor === color.value"
            />
            <span class="color-preview" :style="{ backgroundColor: color.preview }"></span>
            <span class="color-label">{{ color.label }}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- 隐藏的颜色选择器（用于颜色分配） -->
    <input
      type="color"
      ref="colorPicker"
      :value="currentEditingColor"
      @change="onColorPickerChange"
      class="hidden-color-picker"
    />
  </div>
</template>

<script>
const COLOR_SCHEMES = [
  {
    value: 'default',
    label: '默认组合',
    colors: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788', '#FF9F43', '#10AC84', '#EE5A6F', '#C44569', '#F8B500', '#6C5CE7']
  },
  {
    value: 'vibrant',
    label: '鲜艳组合',
    colors: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788', '#FF9F43', '#10AC84', '#EE5A6F', '#C44569', '#F8B500', '#6C5CE7', '#00D2D3', '#FF6348', '#2ED573', '#1E90FF', '#FF4757', '#FFA502', '#7BED9F', '#70A1FF', '#5352ED', '#FF3838', '#2F3542', '#57606F']
  },
  {
    value: 'pastel',
    label: '柔和组合',
    colors: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6', '#FFD3B6', '#DCEDC1', '#F0F4C3', '#E1BEE7', '#C5CAE9', '#B3E5FC', '#B2DFDB', '#D7CCC8', '#F8BBD0', '#FFCCBC', '#FFE0B2', '#FFF9C4', '#CFD8DC', '#E6EE9C', '#C8E6C9', '#B2EBF2', '#FFCDD2', '#F5F5F5']
  },
  {
    value: 'warm',
    label: '暖色组合',
    colors: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF', '#FF7675', '#FAB1A0', '#FFEAA7', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#E74C3C', '#C0392B', '#A0522D', '#CD853F', '#DEB887', '#F4A460', '#D2691E', '#8B4513', '#A0522D', '#BC8F8F', '#F08080']
  },
  {
    value: 'cool',
    label: '冷色组合',
    colors: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF', '#00D2D3', '#54A0FF', '#5F27CD', '#48DBFB', '#0ABDE3', '#10AC84', '#009432', '#0652DD', '#9980FA', '#D980FA', '#FDA7DF', '#BADC58', '#F9CA24', '#F0932B', '#EB4D4B', '#6AB04C', '#C7ECEE', '#22A6B3']
  },
  {
    value: 'business',
    label: '商务组合',
    colors: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B', '#5D6D7E', '#85929E', '#AEB6BF', '#1F618D', '#2874A6', '#2E86AB', '#A569BD', '#8E44AD', '#7D3C98', '#6C3483', '#5B2C6F', '#4A235A', '#922B21', '#B03A2E', '#CB4335', '#E74C3C', '#EC7063', '#F1948A']
  },
  {
    value: 'nature',
    label: '自然组合',
    colors: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000', '#145A32', '#196F3D', '#1E8449', '#239B56', '#28B463', '#2ECC71', '#58D68D', '#82E0AA', '#ABEBC6', '#8B4513', '#A0522D', '#CD853F', '#DEB887', '#F5DEB3', '#556B2F', '#6B8E23', '#808000', '#9ACD32']
  }
];

export default {
  name: 'ServiceModuleConfig',
  props: {
    colorGroupBy: String,
    colorScheme: {
      type: String,
      default: 'default'
    },
    customColors: {
      type: Object,
      default: () => ({})
    },
    nodeTextColor: {
      type: String,
      default: 'black'
    },
    centerScopeColor: {
      type: String,
      default: '#EDEDED'
    },
    subDomains: Array,
    domains: Array,
    serviceModules: Array,
    centerScope: {
      type: Array,
      default: () => []
    },
    centerScopeHighlight: {
      type: Boolean,
      default: true
    },
    businessObjects: {
      type: Array,
      default: () => []
    }
  },
  emits: [
    'update:colorGroupBy',
    'update:colorScheme',
    'update:nodeTextColor',
    'update:centerScopeColor',
    'update:customColors',
    'update:centerScopeHighlight'
  ],
  data() {
    return {
      colorSchemes: COLOR_SCHEMES,
      textColors: [
        { value: 'black', label: '黑色', preview: '#000000' },
        { value: 'white', label: '白色', preview: '#FFFFFF' }
      ],
      currentEditingItem: null,
      currentEditingColor: '#000000'
    }
  },
  computed: {
    currentColorScheme() {
      return COLOR_SCHEMES.find(scheme => scheme.value === this.colorScheme) || COLOR_SCHEMES[0];
    },
    groupedItems() {
      const items = [];
      const colors = this.currentColorScheme.colors;
      const centerBoCodes = new Set(this.centerScope || []);
      const allBusinessObjects = this.businessObjects || [];

      let groupItems = [];
      if (this.colorGroupBy === 'subDomain') {
        groupItems = (this.subDomains || []).map(name => ({ name, code: name }));
      } else if (this.colorGroupBy === 'serviceModule') {
        groupItems = (this.serviceModules || []).map(sm => ({
          name: sm.name || sm,
          code: sm.code || sm.name || sm
        }));
      } else {
        groupItems = (this.domains || []).map(name => ({ name, code: name }));
      }

      if (groupItems.length === 0) return [];

      // v29: 对齐 CenterDomainSelect — BO 级检查
      //   收集每个分组下的所有 BO code, 判断是否全部在 centerBoCodes 中
      const isFullyInCenterScope = (groupName, groupCode) => {
        const groupBoCodes = new Set();
        allBusinessObjects.forEach(bo => {
          const matchesGroup =
            bo.serviceModuleName === groupName ||
            bo.serviceModule === groupName ||
            bo.serviceModule === groupCode ||
            bo.serviceModuleName === groupCode;
          if (matchesGroup) {
            groupBoCodes.add(bo.code || bo.name);
          }
        });
        if (groupBoCodes.size === 0) return false;
        for (const code of groupBoCodes) {
          if (!centerBoCodes.has(code)) {
            return false;
          }
        }
        return true;
      };

      // 检查分组是否部分包含中心范围对象
      const hasCenterScopeItems = (groupName, groupCode) => {
        return allBusinessObjects.some(bo => {
          const matchesGroup =
            bo.serviceModuleName === groupName ||
            bo.serviceModule === groupName ||
            bo.serviceModule === groupCode ||
            bo.serviceModuleName === groupCode;
          return matchesGroup && centerBoCodes.has(bo.code || bo.name);
        });
      };

      let colorIndex = 0;
      groupItems.forEach((item) => {
        const groupName = item.name;
        const groupCode = item.code;

        const fullyIn = this.centerScopeHighlight && isFullyInCenterScope(groupName, groupCode)
        const hasCenter = this.centerScopeHighlight && hasCenterScopeItems(groupName, groupCode)
        console.log('[SMC] item:', groupName, 'fullyInCenter:', fullyIn, 'hasCenter:', hasCenter)

        // 当区分中心范围时，过滤掉完全在中心范围内的分组
        if (fullyIn) {
          return;
        }

        // 检查是否部分包含中心范围对象（仅在区分中心范围时生效）
        const isCenter = this.centerScopeHighlight && hasCenterScopeItems(groupName, groupCode);

        items.push({
          name: groupName,
          color: this.customColors[groupName] || colors[colorIndex % colors.length],
          isCenter
        });
        colorIndex++;
      });

      return items;
    }
  },
  methods: {
    openColorPicker(itemName, currentColor) {
      this.currentEditingItem = itemName;
      this.currentEditingColor = currentColor;
      this.$nextTick(() => {
        const picker = this.$refs.colorPicker;
        if (picker) {
          picker.click();
        }
      });
    },
    onColorPickerChange(event) {
      const newColor = event.target.value;
      if (this.currentEditingItem) {
        const newColors = { ...this.customColors, [this.currentEditingItem]: newColor };
        this.$emit('update:customColors', newColors);
      }
    }
  }
}
</script>

<style scoped>
.service-module-config {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  align-items: flex-start;
}

.form-row:last-of-type {
  margin-bottom: 0;
}

.form-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-item.full-width {
  flex: 2;
}

.form-item.color-picker-wrapper {
  position: relative;
}

.form-color-picker {
  width: 60px;
  height: 32px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
}

.form-label {
  font-weight: 600;
  color: #333;
  font-size: 12px;
  white-space: nowrap;
}

.form-label.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.form-label.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.form-select {
  padding: 6px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  width: 100%;
  box-sizing: border-box;
}

.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.text-color-options {
  display: flex;
  gap: 8px;
}

.color-option {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.color-option:hover {
  border-color: #999;
}

.color-option.is-selected {
  border-color: #666;
  background: #f5f5f5;
}

.color-option input[type="radio"] {
  display: none;
}

.color-preview {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  border: 1px solid rgba(0, 0, 0, 0.15);
  flex-shrink: 0;
}

.color-label {
  font-size: 11px;
  color: #555;
}

/* 内联颜色选择器样式 */
.inline-color-picker {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  min-width: 200px;
}

.color-picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #999;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #333;
}

.color-palette {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}

.palette-color {
  width: 24px;
  height: 24px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: transform 0.2s;
}

.palette-color:hover {
  transform: scale(1.1);
  border-color: #666;
}

.color-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.native-color-input {
  width: 40px;
  height: 28px;
  padding: 0;
  border: 1px solid #d9d9d9;
  border-radius: 3px;
  cursor: pointer;
}

.color-text-input {
  flex: 1;
  height: 28px;
  padding: 0 8px;
  border: 1px solid #d9d9d9;
  border-radius: 3px;
  font-size: 12px;
  text-transform: uppercase;
}

.color-text-input:focus {
  outline: none;
  border-color: #1890ff;
}

.suggestion-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: #f9f9f9;
  border-radius: 3px;
  border: 1px solid #e8e8e8;
}

.center-badge {
  font-size: 10px;
  color: #888;
  background: #e8e8e8;
  padding: 0 4px;
  border-radius: 2px;
  line-height: 1.4;
}

.color-dot {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
  cursor: pointer;
  transition: transform 0.2s;
}

.color-dot:hover {
  transform: scale(1.2);
}

.item-name {
  font-size: 12px;
  color: #555;
  white-space: nowrap;
}

.item-name.is-center {
  font-weight: bold;
  font-style: italic;
  text-decoration: underline;
}

.hidden-color-picker {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
</style>
