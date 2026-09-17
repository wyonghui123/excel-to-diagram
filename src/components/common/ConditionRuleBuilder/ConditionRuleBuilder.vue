<!--
  ConditionRuleBuilder.vue
  通用条件规则配置组件 (递归版 v2, 支持嵌套 AND/OR 子组)

  [v27 2026-08-26] Phase 4 嵌套支持
    - 设计依据: docs/specs/spec-condition-rule-builder.md §5.2/5.3
    - 模板只负责顶层: 接收 tree → 递归调用 <RuleBuilderGroup>
    - 嵌套深度由 RuleBuilderGroup 通过 maxNestingLevel 控制 (默认 3)
    - 序列化器 (serializers.ts) v26 阶段已支持嵌套, 本次无需改动

  API:
    tree             条件树 (GroupNode)
    fieldMetadata    字段元数据 (用于字段下拉)
    resourceType     资源类型 (picker 显示用)
    maxNestingLevel  嵌套深度上限 (默认 3)
    disabled         是否禁用全部控件
    showPreview      是否显示「生成表达式」预览框
    pickerCtx        传给 picker 的上下文 { form }
    permService      注入 picker fetcher 依赖 (可选)

  ================= 排查备注 (2026-08-26 复盘沉淀) =================
  组件拆分: ConditionRuleBuilder(顶层) → RuleBuilderGroup(递归组)
            → ConditionRuleRow(单行) | 逻辑辅助 operators.ts/rule-init.ts
            /rule-helpers.ts / serializers.ts

  一、布局坐标系 (排查对齐问题必读)
  1) 列宽来源: .rule-row{display:grid; width:100%; grid-template-columns:
     70px 1.4fr 1fr 1.4fr 24px}。fr 列依据行宽分配,
     故【所有规则行必须等宽】→ 由 .rule-row{width:100%} 保证
     (父级 .rule-builder-row-wrapper 是 flex+align-items:center,
      flex item 默认 shrink-to-fit, 不加 width:100% 会导致选中短文本行比
      placeholder 长文本行窄、三列错位)。
  2) 子组层级: --nested 自身【不加缩进】(保证 tag-row 与外部规则行左对齐 x=40);
     进深 16px + 左侧竖线放在 .rule-builder-group--nested .rule-builder-group-children,
     竖线用 ::before 绝对定位(占缩进区左侧 4px)。
  3) add-row 必须放在 children【内部末尾】, 否则子组内「添加条件」不进深、跑出竖线。
  4) 统一规格: 控件高 28px、文字起点 padding 12px (el-select wrapper 与 picker trigger
     对齐)。EP el-select wrapper 是 inline-block, 需 width:100% + min-width:0。

  二、已知坑 (element-plus ≥2.14)
  - 单选中选中 label 渲染在 .el-select__placeholder 元素内(复用 placeholder)。
    切勿给它设 width/flex(width 会把 label 裁成 0 → 视觉看不到选中项)。
  - EP el-select 是 inline-block, 作为 grid item 需要 width:100% 才填满列。

  三、字段预填逻辑 (首行默认 ID + 在列表中)
  - ConditionRuleDialog.loadFieldMetadata() 新增时调
    initRuleForField(customRules[0], getBusinessKeyField()) 预填首行。
  - getBusinessKeyField: 优先 db_column==='id', 兜底 'code'。
  - initRuleForField: field=db_column、fieldType、operator 保留 IN(integer 合法)、
    isBusinessKey=true(触发 self-reference picker)。

  四、验证 (端口: 前端 dev=3006, 后端=3011; 用 VITE_PORT/BACKEND_PORT 启动)
  - 脚本: test_helpers/scripts/debug_*.py (playwright 直连 dev-login@3011 → router.push
    到 role-detail 12666 → 点 .ram-scope-condition-btn 打开 dialog 后测量 DOM)。
    debug_sel_trigger / debug_subgroup_layout / debug_left_align / debug_chip_pos /
    debug_row_widths: 分别验证选中展示、子组布局、左对齐、chip 位置、行宽一致。
-->
<template>
  <div class="condition-rule-builder">
    <RuleBuilderGroup
      :node="tree"
      :level="0"
      :max-nesting-level="maxNestingLevel"
      :field-metadata="fieldMetadata"
      :resource-type="resourceType"
      :picker-ctx="pickerCtx"
      :rule-value-fetcher="ruleValueFetcher"
      :is-top-level="true"
      :disabled="disabled"
      @update:node="onTreeUpdate"
      @change="syncAndEmit"
    />

    <!-- 表达式预览 -->
    <div v-if="showPreview" class="rule-preview">
      <label class="preview-label">生成的条件表达式</label>
      <code class="preview-code">{{ serializedText || '（空）' }}</code>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import RuleBuilderGroup from './RuleBuilderGroup.vue'
import { serialize } from './serializers.ts'
import { createRuleValueFetcher } from './rule-helpers.ts'

const props = defineProps({
  tree: { type: Object, required: true },  // GroupNode
  fieldMetadata: { type: Array, default: () => [] },
  resourceType: { type: String, default: '' },
  maxNestingLevel: { type: Number, default: 3 },
  disabled: { type: Boolean, default: false },
  showPreview: { type: Boolean, default: true },
  pickerCtx: { type: Object, default: () => ({}) },
  permService: { type: Object, default: null },
})

const emit = defineEmits(['update:tree', 'change'])

// picker fetcher (可注入 permService 用于测试)
const ruleValueFetcher = computed(() => {
  return props.permService ? createRuleValueFetcher(props.permService) : createRuleValueFetcher()
})

// 序列化文本 (递归遍历 tree)
const serializedText = computed(() => serialize(props.tree))

// 序列化变化时通知父组件 (用于高级模式 textarea 同步)
watch(serializedText, (val) => {
  emit('change', val)
})

/**
 * RuleBuilderGroup 内部递归 emit('update:node', newNode) 时回写顶层 tree
 */
function onTreeUpdate(newTree) {
  emit('update:tree', newTree)
}

function syncAndEmit() {
  // watch(serializedText) 会 emit('change'), 这里显式调用确保 addRow/removeRow 等即时同步
  emit('change', serializedText.value)
}

defineExpose({
  serialize: () => serializedText.value,
})
</script>

<style scoped>
.condition-rule-builder {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rule-preview {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--color-bg-tertiary, #fafafa);
  border-radius: var(--radius-sm, 4px);
}
.preview-label {
  display: block;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
  margin-bottom: 4px;
}
.preview-code {
  display: block;
  font-family: monospace;
  font-size: 12px;
  color: var(--color-text-primary, #333);
  word-break: break-all;
}
</style>