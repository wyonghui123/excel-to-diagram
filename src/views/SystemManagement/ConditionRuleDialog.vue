<template>
  <AppModal
    :model-value="true"
    :title="dialogTitleComputed"
    width="720"
    :show-default-footer="false"
    @close="$emit('close')"
  >
    <div class="dialog-body" :class="{ 'crd--readonly': props.readonly }">
      <!-- [2026-08-27] 删除顶部 AppAlert 说明文案
           - 原因: 内容是「条件型权限」概念定义, 与 dialog 标题「添加条件 / 编辑条件」重复
           - 价值: 用户从具体资源行入口打开 dialog, 已知道是「条件型」, 顶部文案属于概念层解释
           - 空间: 让 dialog 起始即进入「资源类型 + 条件定义」操作区, 减少视线跳跃 -->

      <!-- [Phase 3.13 + 3.14 2026-08-25] v13/v14 简化：
           v13 去掉「权限级别」(read/write/admin) 字段 — 与数据权限范围无关
           v13 去掉「禁止权限」复选框 — 与 picker「排除」重复
           v14 去掉「资源类型 *」下拉选择 — dialog 从具体资源行入口，资源类型已由父组件 props.editingRule.resource_type 提供
                改成「资源类型: <名称>」只读标识 + overlap warning 紧跟其后 -->

      <div v-if="form.resource_type" class="form-group">
        <!-- [Phase 3.14] v14 资源类型只读标识 — 替代原 select -->
        <div class="resource-type-readonly">
          <AppIcon name="link" :size="12" />
          <span class="resource-type-label">资源类型：</span>
          <span class="resource-type-value">{{ form.resource_type }}</span>
          <span v-if="form.rowLabel && form.rowLabel !== form.resource_type" class="resource-type-display">
            （{{ form.rowLabel }}）
          </span>
        </div>
        <!-- FR-005 重复配置警告 — 保留（仍生效） -->
        <div v-if="overlapWarnings.length > 0" class="overlap-warning">
          <AppIcon name="alert-triangle" :size="12" />
          <span>Section 1「权限维度」与本规则存在字段重复配置（共 {{ overlapWarnings.length }} 项），将以本规则（Section 3）为准（spec FR-005）</span>
        </div>

        <label class="form-label">条件定义 <span class="required">*</span></label>

        <!-- [Phase 3.13 2026-08-25] v13 简化：
             去掉「权限维度 / 自定义条件」 tab 切换。
             资源行已有「包含 (picker 多选) / 自定义 (表达式)」二选一 = 数据权限范围的统定义。
             此 dialog 专注于「条件表达式」本身（即 v12 Rule Builder），不再有 tab 切换。
             「权限维度」已被 picker/expression 入口替代（详见 ResourceActionMatrix.vue 的 picker 按钮）。
             -->
        <div class="custom-mode">
            <!-- [v26 2026-08-26] 委托给通用 ConditionRuleBuilder 组件
                 - 设计依据: docs/specs/spec-condition-rule-builder.md
                 - 取代 v12-v25 的 200+ 行手写模板（rule-row + 5 个值控件分支）
                 - 数据流: tree (ref) ↔ ConditionRuleBuilder
                       :tree 传入 treeRef
                       @update:tree → onTreeUpdate 同步 children 回 customRules
                 - 序列化: ConditionRuleBuilder @change → 触发父组件 syncCustomRules() -->
            <ConditionRuleBuilder
              :tree="treeRef"
              :field-metadata="fieldMetadata"
              :resource-type="form.resource_type"
              :picker-ctx="{ form }"
              :perm-service="permService"
              :show-preview="false"
              @update:tree="onTreeUpdate"
              @change="syncCustomRules"
            />

            <!-- 高级模式切换（兼容 v11 旧版 textarea）-->
            <div class="advanced-toggle">
              <button
                type="button"
                class="advanced-toggle-btn"
                @click="showAdvanced = !showAdvanced"
              >
                <AppIcon :name="showAdvanced ? 'chevron-down' : 'chevron-right'" :size="11" />
                <span>{{ showAdvanced ? '收起' : '展开' }}高级模式（直接编辑表达式）</span>
              </button>
              <div v-if="showAdvanced" class="advanced-section">
                <div class="field-help-section">
                  <div class="field-help-header" @click="showFieldHelp = !showFieldHelp">
                    <span><AppIcon name="clipboard" :size="14" /> 可用字段参考（点击展开）</span>
                    <span class="toggle-icon">{{ showFieldHelp ? '▼' : '▶' }}</span>
                  </div>
                  <div v-if="showFieldHelp" class="field-help-content">
                    <div v-if="fieldMetadata.length === 0" class="field-help-empty">加载中...</div>
                    <div v-for="field in fieldMetadata" :key="field.id" class="field-help-item" @click="insertField(field)">
                      <span class="field-help-name">{{ field.name }}</span>
                      <span class="field-help-column">{{ field.db_column }}</span>
                      <span class="field-help-type">{{ field.field_type }}</span>
                      <span v-if="field.is_foreign_key" class="field-help-fk" title="外键，支持Value Help"><AppIcon name="link" :size="12" /> {{ field.relation_object }}</span>
                    </div>
                  </div>
                </div>
                <textarea v-model="customCondition" rows="3" :readonly="props.readonly" placeholder="如：product_id IN (1, 2, 3) AND domain_type = 'CORE'    （AND/OR 是表达式关键字，等同于「且 / 或」）" class="condition-input"></textarea>
                <div class="condition-hint">
                  支持格式：field = value | field IN (v1, v2) | field != value | 多个条件用「且 / 或」组合
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="form-group scope-section">
          <label class="form-label">规则作用域</label>
          <el-radio-group v-model="scopeMode" size="small" class="scope-radio-group" :disabled="props.readonly">
            <el-radio-button label="none">仅本级</el-radio-button>
            <el-radio-button label="down">
              <AppIcon name="arrow-down" :size="12" /> 向下继承
            </el-radio-button>
            <el-radio-button label="up">
              <AppIcon name="arrow-up" :size="12" /> 向上传播
            </el-radio-button>
            <el-radio-button label="both">双向</el-radio-button>
          </el-radio-group>
          <div class="scope-hint">
            <span v-if="scopeMode === 'none'">规则仅作用于直接选中的资源层级（如仅 BO），不影响子级 / 父级</span>
            <span v-else-if="scopeMode === 'down'">条件自动覆盖子级资源（如 BO 条件应用到服务模块、子领域、领域）</span>
            <span v-else-if="scopeMode === 'up'">子级权限提供父级只读可见性（如有「子领域 X」权限的用户能看见 X 所属的「领域」）</span>
            <span v-else>同时启用向下继承与向上传播（最常见默认配置）</span>
          </div>
        </div>

        <!-- [2026-08-28 v61] 预览区改造（方案 A 轻量修正）：
             1. 错误显性化 — 条件解析失败显示红色提示，不再伪装成「匹配 0 个」
             2. 全表对比 — 匹配数 / 全表数 / 占比，过高提示「接近全放行」
             3. stale 标记 — 条件变更后旧结果标灰，等待 600ms debounce 自动刷新 -->
        <div v-if="previewResult" class="preview-section">
          <label class="preview-label">
            匹配资源预览
            <span v-if="previewStale && !previewing" class="preview-stale-tag">条件已变更</span>
          </label>
          <div class="preview-result" :class="{ 'preview-result--error': previewResult.error }">
            <template v-if="previewResult.error">
              <span class="preview-error">
                <AppIcon name="alert-triangle" :size="12" />
                条件解析失败：{{ previewResult.error }}
              </span>
            </template>
            <template v-else>
              <span class="preview-count">
                匹配 {{ previewResult.count }}<template v-if="previewResult.total > 0"> / 全表 {{ previewResult.total }} 个资源</template>
                <span v-if="previewRatio !== null" class="preview-ratio">（{{ ratioText }}）</span>
              </span>
              <span v-if="previewRatio !== null && previewRatio >= 0.9" class="preview-hint">
                范围接近全表，请确认是否符合预期
              </span>
              <div v-if="previewResult.resources?.length" class="preview-list">
                <span v-for="r in previewResult.resources.slice(0, 10)" :key="r.id" class="preview-item">
                  {{ r.name || r.code || `#${r.id}` }}
                </span>
                <span v-if="previewResult.count > 10" class="preview-more">...等 {{ previewResult.count }} 个</span>
              </div>
            </template>
          </div>
        </div>
      </div>

    <template #footer>
      <!-- [v45 2026-08-27] 浏览态只读弹窗：隐藏 预览·保存，仅保留「关闭」 -->
      <template v-if="props.readonly">
        <AppButton variant="primary" @click="$emit('close')">关闭</AppButton>
      </template>
      <template v-else>
        <AppButton variant="secondary" @click="$emit('close')">取消</AppButton>
        <!-- [2026-08-28 v61] trivial 不再置灰 — 单值/≤3项 IN 也自动预览显示 name
             （呼应用户「显示 name 而非 ID」诉求）；已有结果后按钮转为手动刷新 -->
        <AppButton
          variant="secondary"
          :loading="previewing"
          :disabled="!form.condition"
          :title="!form.condition ? '请先配置条件' : '查看当前条件实际匹配的资源'"
          @click="doPreview"
        >
          {{ previewing ? '预览中...' : (previewResult ? '刷新预览' : '预览匹配') }}
        </AppButton>
        <AppButton
          variant="primary"
          :loading="saving"
          :disabled="!form.condition"
          @click="handleSave"
        >
          {{ saving ? '保存中...' : (isEditMode ? '保存修改' : '确认添加') }}
        </AppButton>
      </template>
    </template>
  </AppModal>
</template>

<script setup>
import { computed, watch } from 'vue'
import { AppModal, AppButton } from '@/components/common'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import { ConditionRuleBuilder } from '@/components/common/ConditionRuleBuilder'
import * as permService from '@/services/permissionService'
import { useConditionRuleDialog } from '@/composables/useConditionRuleDialog'

/**
 * [C 方案 2026-09-16] ConditionRuleDialog 瘦身
 *   - 业务逻辑 (Rule Builder state + preview + save + 字段水合 + scopeMode 互映)
 *     全部下沉到 useConditionRuleDialog composable
 *   - dialog 仅保留: props/emits + 解构 composable + readonly 模式下的 dialogTitle 计算 + init watch
 *   - 原 846 行 → 现 ~280 行 (模板 + style ~210 + script ~70)
 *
 * 历史：
 *   - [Phase 3.13 2026-08-25] v13 简化：去掉 permission_level/is_denied/dimension mode
 *   - [v45 2026-08-27] 浏览态只读弹窗 (props.readonly = true)
 *   - [v52 2026-08-27] 高级模式手编表达式 → 直接作为保存源
 *   - [Spec 22 PM 反馈第十八次 2026-09-13] 调用模板单一真源 → useConditionRuleDialog
 *   - [Spec 22 PM 反馈第二十二次 2026-09-16] 业务逻辑下放 (本 commit)
 */

const props = defineProps({
  permissionSetId: { type: [String, Number], required: true },
  editingRule: { type: Object, default: null },
  readonly: { type: Boolean, default: false },
  // [2026-09-16 C 方案] readonly 模式下 dialogTitle 前缀变「查看条件（只读） · 」,
  //   通过父组件传 isReadonly 显式告知 (避免 composable 内部 isEditing 反义推断歧义)
  isReadonlyMode: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

// 解构 composable — 业务逻辑全部下沉
const {
  form,
  isEditMode,
  scopeMode,
  customRules: _customRules, // eslint-disable-line no-unused-vars — 模板间接通过 treeRef 消费
  treeRef,
  showAdvanced,
  customCondition,
  fieldMetadata,
  showFieldHelp,
  overlapWarnings,
  previewResult,
  previewing,
  previewStale,
  previewRatio,
  ratioText,
  saving,
  // dialogTitle 从 composable 取, 但 readonly 模式下需要在本地重写
  // (composable 内部没有 readonly 概念, 只有 isEditing → isEditMode 推导)
  onTreeUpdate,
  syncCustomRules,
  doPreview,
  insertField,
  handleSave,
  init,
} = useConditionRuleDialog({
  permissionSetId: computed(() => props.permissionSetId),
  getRowScope: () => ({}), // dialog 内不直接走 scopeMatrix (父组件已通过 editingRule 装载)
  isEditing: computed(() => !props.readonly),
  // dialog 自己直接 emit 'saved' 给父组件, 不需要 composable 二次回调
  onSaved: (savedRule) => emit('saved', savedRule),
})

// [C 方案 2026-09-16] readonly 模式 dialogTitle 重写
//   composable 的 dialogTitle 不感知 readonly 概念, 这里在本地覆盖
const dialogTitleComputed = computed(() => {
  if (props.isReadonlyMode || props.readonly) {
    return '查看条件（只读） · ' + (form.rowLabel || form.resource_type || '条件规则')
  }
  const prefix = isEditMode.value ? '编辑条件 · ' : '添加条件 · '
  return prefix + (form.rowLabel || form.resource_type || '条件规则')
})

// [C 方案 2026-09-16] 编辑模式反算: dialog 卸载时 composable 状态自然 GC,
//   新打开时通过 props.editingRule 触发 init() 重装
watch(
  () => props.editingRule,
  (rule) => {
    if (rule) init(rule)
  },
  { immediate: true }
)
</script>

<style scoped>
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.form-label { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--color-text-secondary); }
.required { color: var(--color-error); }

/* [Phase 3.13 2026-08-25] v13 简化：注释保留便于历史溯源 */

/* [Phase 3.14] v14 资源类型只读标识 */
.resource-type-readonly {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: var(--font-size-sm);
  background: var(--color-bg-tertiary, #f5f5f5);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 6px);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}
.resource-type-readonly > svg {
  color: var(--color-primary, #ea580c);
}
.resource-type-label {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium, 500);
}
.resource-type-value {
  font-family: monospace;
  font-weight: 600;
  color: var(--color-primary, #ea580c);
}
.resource-type-display {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs, 12px);
}

.checkbox-label { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 2px var(--spacing-sm); font-weight: normal !important; cursor: pointer; }
.checkbox-label input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--color-primary); margin-top: 3px; }

.option-label { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
.option-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); flex: 1 0 100%; padding-left: calc(16px + var(--spacing-sm)); }

.overlap-warning {
  display: flex; align-items: center; gap: 6px;
  font-size: var(--font-size-xs);
  color: var(--color-warning, #d97706);
  background: rgba(217, 119, 6, 0.06);
  border: 1px solid rgba(217, 119, 6, 0.2);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  margin-top: 4px;
}

/* [v26 2026-08-26] Rule Builder UI 已迁移到通用组件 <ConditionRuleBuilder>
 *   以下样式属于旧版 inline rule-builder（v12-v25），保留仅为占位，实际已不渲染。
 *   新组件样式由 components/common/ConditionRuleBuilder/ConditionRuleRow.vue 管理
 */
/* 高级模式折叠 */
.advanced-toggle {
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px dashed var(--color-border-light);
}
.advanced-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 0;
}
.advanced-toggle-btn:hover {
  color: var(--color-primary, #ea580c);
}
.advanced-section {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--color-bg-tertiary, #fafafa);
  border-radius: var(--radius-sm);
}

/* [Phase 3.13 2026-08-25] v13 简化：删除 value help + 多选tag + condition-preview 相关 CSS
 *   保留 .field-help-* / .condition-input / .condition-hint（高级模式 textarea 用）
 *   保留 .preview-section / .preview-*（预览匹配）
 */

/* 字段帮助（高级模式 textarea 的字段参考）*/
.field-help-section {
  margin-bottom: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.field-help-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.toggle-icon { font-size: var(--font-size-xs); }
.field-help-content {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
}
.field-help-empty {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  text-align: center;
}
.field-help-item {
  display: flex; align-items: center; gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  border-bottom: 1px solid var(--color-border-subtle);
}
.field-help-item:hover { background: var(--color-primary-bg); }
.field-help-item:last-child { border-bottom: none; }
.field-help-name { color: var(--color-text-primary); font-weight: var(--font-weight-medium); min-width: 80px; }
.field-help-column { color: var(--color-text-tertiary); font-family: monospace; font-size: var(--font-size-xs); }
.field-help-type { color: var(--color-text-quaternary); font-size: var(--font-size-xs); background: var(--color-bg-tertiary); padding: 1px 6px; border-radius: var(--radius-sm); }
.field-help-fk { color: var(--color-primary); font-size: var(--font-size-xs); margin-left: auto; }

.condition-input {
  width: 100%; font-family: monospace; resize: vertical;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  color: var(--color-text-primary);
}
.condition-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: 2px; }

/* [2026-08-28 v61] 预览区样式 — 错误显性化 + 全表对比 + stale 标记
     - 全部使用 UI 令牌（字号 ≥ --font-size-xs，色彩用规范色阶） */
.preview-section { margin-top: var(--spacing-sm); }
.preview-label { display: inline-flex; align-items: center; gap: var(--spacing-xs); font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.preview-stale-tag { padding: 1px 6px; background: var(--color-bg-layout); border: 1px solid var(--color-border); border-radius: var(--radius-sm); font-size: var(--font-size-xs); font-weight: var(--font-weight-regular); color: var(--color-text-tertiary); }
.preview-result { display: flex; flex-direction: column; gap: var(--spacing-xs); padding: var(--spacing-sm) var(--spacing-md); background: var(--color-bg-layout); border-radius: var(--radius-md); }
.preview-result--error { background: var(--color-danger-bg, #fef0f0); }
.preview-count { font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.preview-ratio { color: var(--color-text-tertiary); font-weight: var(--font-weight-regular); }
.preview-hint { font-size: var(--font-size-xs); color: var(--color-warning, #d97706); }
.preview-error { display: inline-flex; align-items: center; gap: 4px; font-size: var(--font-size-xs); color: var(--color-danger, #f56c6c); }
.preview-list { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); }
.preview-item { padding: 2px 8px; background: var(--color-primary-bg); border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--color-primary); }
.preview-more { font-size: var(--font-size-xs); color: var(--color-text-quaternary); }

/* [2026-08-27] 规则作用域 — 与现有 .form-group / .form-label 同款
     - scope-section: 顶部加一条细分隔线，与"条件定义"区分
     - radio-group: 与 EP 按钮组默认尺寸对齐（size=small）
     - scope-hint: 行内灰色提示，承载四态文案 */
.scope-section { margin-top: var(--spacing-md); padding-top: var(--spacing-sm); border-top: 1px dashed var(--color-border-secondary, #e5e7eb); }
.scope-radio-group { width: 100%; }
.scope-radio-group :deep(.el-radio-button__inner) { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; }
.scope-hint { margin-top: var(--spacing-xs); font-size: var(--font-size-xs); color: var(--color-text-tertiary, #94a3b8); line-height: 1.5; }

/* [v45→v51 2026-08-27] 浏览态只读弹窗：双保险策略
   - 组件层: builder / scope radio 走 :disabled，textarea 走 :readonly（视觉置灰）
   - CSS 层: 内容区 pointer-events:none 兜底拦截漏网交互（如行内且/或切换），
     仅保留「展开高级模式」按钮可点 —— 用户要求浏览态可展开查看表达式
   - 字段参考可展开阅读；「点击插入」在 insertField 内有 readonly 守卫 */
.crd--readonly .custom-mode,
.crd--readonly .scope-section,
.crd--readonly .advanced-section {
  pointer-events: none;
}
/* [v53 fix] 展开高级模式按钮位于 .custom-mode 内部，
   必须显式恢复可点（后声明覆盖上面的 pointer-events:none） */
.crd--readonly .advanced-toggle {
  pointer-events: auto;
}

</style>