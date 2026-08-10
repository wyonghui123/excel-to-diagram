<!--
  ChartMiniToolbar - 图表顶部高频配置工具栏

  所属模块：嵌入式图表视图（Phase 2）
  主要功能：
    - 图表类型切换（业务对象图 / 服务模块图）
    - 颜色方案选择
    - 颜色分组维度选择（领域 / 子领域 / 服务模块）
    - 备注类型过滤多选
    - 布局设置按钮（侧边抽屉打开布局控制面板）

  契约：见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ③

  [FIX 2026-07-31] 移除全屏按钮，改为布局设置按钮：
    - 全屏跳转功能已废弃（嵌入式图表就地展示，不再跳 /archdata-chart）
    - 新增"布局设置"按钮，点击后侧边打开 LayoutControlPanel 抽屉
    - 回溯修复：LayoutControlPanel 之前在 EmbeddedChartView 内有引用但抽屉未渲染（功能丢失）
-->

<template>
  <div class="chart-mini-toolbar">
    <!-- [CTX-GLOBAL 2026-08-10] 展开层级下拉已移除:
         改用图表空白区域右键菜单 (展开到领域/子领域/服务模块/业务对象), 见 MermaidComponent.handleContextMenu.
         原展开层级逻辑仍由 LayoutControlPanel(图表设置抽屉) 与 store.setExpandLevel 承载,
         展开层级状态同步不变 (diagramConfigStore.expandLevel). -->

    <!-- 颜色分组维度 -->
    <el-select
      :model-value="colorGroupBy"
      size="small"
      class="cmt-select"
      @update:model-value="(v) => emit('update:colorGroupBy', v)"
    >
      <template #prefix>
        <span class="cmt-label">颜色分组</span>
      </template>
      <!-- [FIX 2026-07-27] colorGroupBy 值必须与老图表 (StepConfig.vue line 258-261 / CenterDomainSelect.vue / ServiceModuleConfig.vue) 一致
           老图表使用驼峰命名 'subDomain' / 'serviceModule'，下划线写法 ('sub_domain' / 'service_module')
           会让 colorMapping 的 if 分支全部 miss，落到 else 当作 'domain' 处理 → 颜色分组切换无效 -->
      <el-option label="按领域" value="domain" />
      <el-option label="按子领域" value="subDomain" />
      <el-option label="按服务模块" value="serviceModule" />
    </el-select>

    <!-- 颜色方案 -->
    <el-select
      :model-value="colorScheme"
      size="small"
      class="cmt-select cmt-select--short"
      @update:model-value="(v) => emit('update:colorScheme', v)"
    >
      <template #prefix>
        <span class="cmt-label">配色</span>
      </template>
      <!-- [FIX 2026-07-27] colorScheme 值必须与老图表一致
           老图表 StepConfig.vue line 245-253 的 COLOR_SCHEMES 表里使用 'vibrant' / 'pastel'
           之前用 'high-contrast' / 'soft' 会触发 fallback 到 'default' → 用户看不到配色变化 -->
      <el-option label="默认" value="default" />
      <el-option label="鲜艳" value="vibrant" />
      <el-option label="柔和" value="pastel" />
    </el-select>

    <!-- [NEW 2026-07-31] 区分中心范围下拉 (centerScopeHighlight 切换)
         用户需求: 在 toolbar 增加"区分中心范围"下拉, 默认 true (区分)
         - true (区分): centerScope 内的 BOs 会被高亮 (但当 colorGroupBy 活跃时不覆盖分组色)
         - false (不区分): 所有节点按分组色渲染, 不做 centerScope 高亮 -->
    <el-select
      :model-value="centerScopeHighlight ? 'yes' : 'no'"
      size="small"
      class="cmt-select cmt-select--short"
      @update:model-value="(v) => emit('update:centerScopeHighlight', v === 'yes')"
    >
      <template #prefix>
        <span class="cmt-label">对象范围</span>
      </template>
      <el-option label="区分" value="yes" />
      <el-option label="不区分" value="no" />
    </el-select>

    <!-- [FIX 2026-07-31] 备注类型多选下拉 (与老版本 CenterDomainSelect/StepConfig 一致)
         - 选项从 enum_types.annotation_category 加载 (与 CenterDomainSelect 同样入口 EnumService)
         - 默认空 = 不过滤 (向后兼容, 显示全部备注)
         - 与老的"显示备注图标"按钮合并: 移除按钮 (v-model 改为 icon switch)
         - 设计意图: 用户期望 toolbar 直接控制"展示哪些类型的备注", 与配置阶段的"备注类型过滤"对等 -->
    <el-select
      :model-value="annotationCategoryFilter"
      multiple
      collapse-tags
      collapse-tags-tooltip
      :max-collapse-tags="2"
      filterable
      clearable
      placeholder="备注类型 (全选=全部)"
      size="small"
      class="cmt-select cmt-select--annotation"
      :empty-values="false"
      @update:model-value="(v) => emit('update:annotationCategoryFilter', v)"
    >
      <template #prefix>
        <span class="cmt-label">备注类型</span>
      </template>
      <el-option
        v-for="opt in annotationOptions"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
      <div v-if="annotationOptions.length === 0" class="cmt-empty">
        暂无配置
      </div>
    </el-select>

    <!-- [2026-08-02] "显示备注图标"按钮已移除:
         该开关写入 annotationConfig.showIcons 但从未被读取 (overlayNumberMarkers 返回 null, 图标绘制是死代码),
         无视觉效果。备注展示由"备注类型"过滤 + 底部备注面板 + 悬停 tooltip 承担, 不再需要中间开关。 -->

    <div class="cmt-divider"></div>

    <!-- [MOVE 2026-08-04] 布局方向: 从 LayoutControlPanel 移到 toolbar, 用 icon 表示
         TB = 垂直 (top-to-bottom, Bottom icon), LR = 水平 (left-to-right, Right icon) -->
    <el-tooltip content="布局方向" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
      <div class="cmt-direction-group">
        <el-button
          :type="overallDirection === 'TB' ? 'primary' : 'default'"
          size="small"
          class="cmt-dir-btn"
          @click="emit('update:overall-direction', 'TB')"
        >
          <el-icon><Bottom /></el-icon>
        </el-button>
        <el-button
          :type="overallDirection === 'LR' ? 'primary' : 'default'"
          size="small"
          class="cmt-dir-btn"
          @click="emit('update:overall-direction', 'LR')"
        >
          <el-icon><Right /></el-icon>
        </el-button>
      </div>
    </el-tooltip>

    <!-- [MOVE 2026-08-04] 高级选项: 从 LayoutControlPanel 移到 toolbar, 用 popover 展开/收起
         当前仅含布局引擎 (elk/dagre) 切换 -->
    <el-popover trigger="click" placement="bottom" :width="260" popper-class="cmt-advanced-popper">
      <template #reference>
        <el-button
          size="small"
          :type="engine !== 'elk' ? 'primary' : 'default'"
          class="cmt-advanced-btn"
        >
          <el-icon><Setting /></el-icon>
          <span class="cmt-adv-label">高级</span>
        </el-button>
      </template>
      <div class="cmt-advanced-panel">
        <div class="cmt-advanced-row">
          <label class="cmt-advanced-label">布局引擎</label>
          <el-radio-group
            :model-value="engine"
            size="small"
            @update:model-value="(v) => emit('update:engine', v)"
          >
            <el-radio value="elk">
              直线/ELK
              <span class="cmt-radio-desc">更好的屏幕适配能力</span>
            </el-radio>
            <el-radio value="dagre">
              曲线/Dagre
              <span class="cmt-radio-desc">稳定可靠，自动布局</span>
            </el-radio>
          </el-radio-group>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup>
/**
 * ChartMiniToolbar - 高频配置工具栏
 *
 * 设计原则（v2.3 §5.0.2 ③ 状态分层）：
 *   - 本组件不持有 chartConfig 状态
 *   - 通过 v-model 与父组件 EmbeddedChartView 双向绑定
 *   - 仅作为 UI 层，触发 update 事件
 */
import { ref, onMounted } from 'vue'
import { Bottom, Right, Setting } from '@element-plus/icons-vue'
import EnumService from '@/services/enumService'

const props = defineProps({
  chartType: { type: String, required: true },
  colorScheme: { type: String, required: true },
  colorGroupBy: { type: String, required: true },
  centerScopeHighlight: { type: Boolean, default: true },
  // [FIX 2026-07-31] 备注类型多选 (来自 chartConfig.annotationCategoryFilter)
  annotationCategoryFilter: { type: Array, default: () => [] },
  // [FIX 2026-07-31] 版本号 - 切换版本时重新加载 enum
  versionId: { type: [Number, String], default: null },
  // [MOVE 2026-08-04] 布局方向 (TB/LR) - 从 LayoutControlPanel 移到 toolbar
  overallDirection: { type: String, default: 'TB' },
  // [MOVE 2026-08-04] 布局引擎 (elk/dagre) - 从 LayoutControlPanel 移到 toolbar 高级选项
  engine: { type: String, default: 'elk' }
})

const emit = defineEmits([
  'update:chart-type',
  'update:color-scheme',
  'update:color-group-by',
  'update:center-scope-highlight',
  'update:annotation-category-filter',
  'update:overall-direction',
  'update:engine'
])

// [FIX 2026-07-31] 加载 enum_types.annotation_category 选项
//   与 CenterDomainSelect/StepConfig 一致入口 (EnumService.loadOptions)
const annotationOptions = ref([])
const loadingAnnotations = ref(false)

async function loadAnnotationOptions() {
  if (loadingAnnotations.value) return
  loadingAnnotations.value = true
  try {
    const result = await EnumService.loadOptions('annotation_category', { cache: true, throwError: false })
    annotationOptions.value = (result || []).map(item => ({
      value: item.value || item.code,
      label: item.label || item.name || item.code,
      count: item.count
    }))
  } catch (e) {
    console.warn('[ChartMiniToolbar] 加载 annotation_category enum 失败:', e)
    annotationOptions.value = []
  } finally {
    loadingAnnotations.value = false
  }
}

onMounted(() => {
  loadAnnotationOptions()
})
</script>

<style lang="scss" scoped>
.chart-mini-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  padding: 8px 16px;
  background: var(--color-bg-container, #fff);
  border-bottom: 1px solid var(--color-border, #e4e7ed);
  flex-shrink: 0;
  min-height: 48px;  // [FIX 2026-07-31] 固定 toolbar 高度, 多选下拉不允许撑开
  max-height: 48px;
  height: 48px;
  overflow: hidden;
}

.cmt-select {
  width: 180px;
  flex-shrink: 0;
}

.cmt-select--short {
  width: 120px;
}

// [FIX 2026-07-31] 备注类型多选下拉: 限制宽度, 不撑高 toolbar
.cmt-select--annotation {
  width: 200px;
  max-width: 200px;

  :deep(.el-select__wrapper) {
    min-height: 28px;
    max-height: 28px;
    padding: 2px 8px;
  }
  // 让 el-select__selection (内部 tag 容器) 不撑高
  :deep(.el-select__selection) {
    max-height: 24px;
    overflow: hidden;
    flex-wrap: nowrap;
  }
  :deep(.el-select__selected-item) {
    max-height: 22px;
    line-height: 20px;
  }
  :deep(.el-select__placeholder) {
    line-height: 24px;
  }
}

.cmt-label {
  font-size: 12px;
  color: var(--color-text-tertiary, #909399);
  white-space: nowrap;
  padding-right: 4px;
  border-right: 1px solid var(--color-border, #dcdfe6);
  margin-right: 4px;
}

.cmt-prefix-icon {
  font-size: 14px;
  color: var(--color-text-secondary, #606266);
  margin-right: 2px;
}

.cmt-spacer {
  flex: 1;
}

.cmt-empty {
  padding: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary, #909399);
  text-align: center;
}

// [MOVE 2026-08-04] 方向切换 + 高级选项 popover 样式
.cmt-divider {
  width: 1px;
  height: 20px;
  background: var(--color-border, #dcdfe6);
  flex-shrink: 0;
  margin: 0 4px;
}

.cmt-direction-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.cmt-dir-btn {
  width: 32px;
  height: 28px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.cmt-advanced-btn {
  width: auto;
  height: 28px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;

  .el-icon {
    font-size: 14px;
  }
}

.cmt-adv-label {
  font-size: 12px;
  line-height: 1;
}
</style>

// [MOVE 2026-08-04] 高级选项 popover 内容样式 (非 scoped, popper 渲染在 body)
<style lang="scss">
.cmt-advanced-popper {
  .cmt-advanced-panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 4px 0;
  }

  .cmt-advanced-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .cmt-advanced-label {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
  }

  .el-radio-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .el-radio {
    margin-right: 0;
    height: auto;
    display: flex;
    align-items: flex-start;
    white-space: normal;
  }

  .cmt-radio-desc {
    display: block;
    margin-left: 22px;
    margin-top: 2px;
    font-size: 11px;
    color: var(--color-text-tertiary, #909399);
    line-height: 1.4;
  }
}
</style>
