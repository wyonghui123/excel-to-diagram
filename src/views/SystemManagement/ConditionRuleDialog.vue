<template>
  <AppModal
    :model-value="true"
    :title="dialogTitle"
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
                       :tree 传入 tree.value
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
                <!-- [v25 2026-08-26] placeholder 改用中文示例 + 注释提示用户 connector 关键字
       - 高级模式 textarea 仍接受 AND / OR（后端 Python 表达式兼容）
       - 用户在 builder 用「且 / 或」, 写表达式时用 AND / OR
       - placeholder 双语示例便于过渡 -->
                  <textarea v-model="customCondition" rows="3" :readonly="props.readonly" placeholder="如：product_id IN (1, 2, 3) AND domain_type = 'CORE'    （AND/OR 是表达式关键字，等同于「且 / 或」）" class="condition-input"></textarea>
                <div class="condition-hint">
                  支持格式：field = value | field IN (v1, v2) | field != value | 多个条件用「且 / 或」组合
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- [Phase 3.13 2026-08-25] v13 简化：
             去掉「生成的条件表达式」+「业务语义」预览块。
             原因：与高级模式 textarea / Rule Builder 显示的「表达式」重复。
             Rule Builder 已经实时显示当前表达式状态（用户配置即可见）；
             高级模式 textarea 本身也是表达式源码 — 「生成的条件表达式」是冗余。
             「业务语义」（绿色块）翻译后的中文描述 — 可保留在高级模式下（折叠时仍显示）。
             -->

        <!-- [2026-08-27] 旧的两个 checkbox 已删除 — 由顶部"规则作用域"四态枚举替代
             避免与下面"匹配资源预览"在视觉上粘连，并消除"两 checkbox 任意组合"歧义 -->

        <!-- [2026-08-27] 规则作用域：合并"向下继承 / 向上传播"为四态枚举
             - 原两独立 checkbox 易组合出"两个都不勾"的歧义
             - 四态: none(仅本级) / down(向下) / up(向上) / both(双向)
             - UI → 后端两列映射:
                 none → false/false | down → true/false | up → false/true | both → true/true
             - 默认 both（对齐 v25 默认）；编辑模式从两列反算 -->
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
      <!-- [v45 2026-08-27] 浏览态只读弹窗：隐藏 预览/保存，仅保留「关闭」 -->
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
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { AppModal, AppButton } from '@/components/common'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import * as permService from '@/services/permissionService'
// [v26 2026-08-26] 引入通用 ConditionRuleBuilder 组件 + 业务主键 helper
//   - 业务主键判定用 operators.ts 版本（含 *_id/*_code 前缀），更普适
// [v28 2026-08-26] 引入 initRuleForField — loadFieldMetadata 预填路径与 Row.onFieldChange 共享同一逻辑
//   - 修复: 默认字段是 boolean/datetime 类型时, operator='IN' 不在合法操作符集合内导致 UI 异常
import { ConditionRuleBuilder, initRuleForField } from '@/components/common/ConditionRuleBuilder'
// [v26 2026-08-26] 引入通用 ConditionRuleBuilder 的序列化器
//   - 取代 v25 的 35 行硬编码 IN/LIKE/boolean/datetime/number 分支
//   - 单层 v1 序列化结果与 v25 100% 一致
//   - Phase 4 嵌套组支持时无需修改本文件
import { serialize, serializeDisplay, parseConditionToRuleRows } from '@/components/common/ConditionRuleBuilder/serializers.ts'

// [Phase 3.13 2026-08-25] v13 简化：
//   - 删掉 CONDITION_RULE_PERMISSION_LEVELS / permissionLevels — 字段已去除
//   - 删掉 sortDimensionsByHierarchy / filterHiddenDimensions / buildConditionFromDimensions 引用
//     — 维度 mode 已废弃（被 picker/expression 替代）
//   - 删掉 translateToFriendlyCondition / parseConditionToDimConfigs 引用 — 业务语义预览已去除
//   - 保留 conditionExpressionService 文件（未来需要完整解析 Rule Builder 时再用）

const props = defineProps({
  roleId: { type: [String, Number], required: true },  // [Plan C 2026-08-29] 暂保留 roleId prop 名（向后兼容 PermissionConfigPanel 透传），内部已统一使用此值
  editingRule: { type: Object, default: null },  // 编辑模式时传入的规则
  // [v45 2026-08-27] 浏览态只读模式：可打开查看，但内容不可编辑、无保存按钮
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])
const message = useMessage()

// [Phase 3.14] v14 删掉 resourceTypeOptions — 资源类型由父组件传入，不再让用户选
//   保留 permService 引用（loadFieldMetadata 等 API 仍需）

// [Phase 3.13] 简化 form：去掉 permission_level / is_denied
//   - permission_level 由资源行的 action 列（create/read/update/delete/export/manage）决定
//   - is_denied 与 picker「排除」重复，已去除 UI
// [Phase 3.14] v14：form 加 rowLabel — 显示资源类型的中文名（如「业务对象」）
//   - 由父组件 handleOpenConditionDialog 通过 payload.rowLabel 提供
const form = reactive({
  resource_type: '',
  rowLabel: '',  // [Phase 3.14] 资源类型的中文显示名（业务对象/领域/子领域/服务模块）
  condition: '',
  // [v45 2026-08-27] 人类可读表达式：字段用中文 label、值用 picker 显示名
  condition_display: '',
  inherit_to_children: true,
  propagate_to_parents: true,
})

// [Phase 3.13] v13 dialog 只有「custom mode」（Rule Builder），不再有 dimension mode
//   mode / dimensions / dimConfigs / sortedDimensions / availableDimensions / isDimSelected /
//   toggleDimension / onOperatorChange / onDisplayValueInput / getValuePlaceholder /
//   activeValueHelp / activeMultiSelect / valueHelpOptions / valueHelpSearch / valueHelpTimeout
//   全部删除 — 这些是旧版 dimension mode 的代码

// [2026-08-27] 规则作用域四态枚举（UI 单源 → 后端两列映射）
const SCOPE_MODES = ['none', 'down', 'up', 'both']
const SCOPE_MODE_MAP = {
  none: { inherit: false, propagate: false },
  down: { inherit: true,  propagate: false },
  up:   { inherit: false, propagate: true  },
  both: { inherit: true,  propagate: true  },
}

const isEditMode = ref(false)  // 是否为编辑模式
const customCondition = ref('')
const previewResult = ref(null)
const saving = ref(false)
const previewing = ref(false)

// [2026-08-27] 规则作用域四态枚举 — UI 单源，序列化时再折回后端两列
//   none/down/up/both 与 inherit_to_children / propagate_to_parents 互映
const scopeMode = ref('both')

// UI 单源 → 后端两列；保存与 emit 都走这里，杜绝"两 checkbox 任意组合"歧义
watch(scopeMode, (mode) => {
  const m = SCOPE_MODE_MAP[mode]
  if (!m) return
  form.inherit_to_children = m.inherit
  form.propagate_to_parents = m.propagate
})

// 后端两列 → UI 单源（编辑模式反算）
watch(
  () => [form.inherit_to_children, form.propagate_to_parents],
  ([inherit, propagate]) => {
    scopeMode.value = SCOPE_MODES.find(
      (k) => SCOPE_MODE_MAP[k].inherit === inherit && SCOPE_MODE_MAP[k].propagate === propagate
    ) || 'both'
  }
)

// [2026-08-28 v61] 预览必要性判断 — 已废弃 trivial 置灰逻辑。
//   原逻辑对单值 ID / ≤3 项 IN 禁用预览，但这恰是用户最想确认
//   「选的是不是这几个（显示 name）」的场景，与「显示 name 而非 ID」诉求相悖。
//   现在：条件变更（已有预览结果时）自动 debounce 600ms 刷新，trivial 也显示 name。
const previewStale = ref(false)
let previewTimer = null

watch(() => form.condition, () => {
  if (!previewResult.value) return  // 尚未预览过，等用户首次点击或保存前不主动请求
  previewStale.value = true
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => { doPreview() }, 600)
})

onBeforeUnmount(() => clearTimeout(previewTimer))

// [2026-08-28 v61] 全表占比 — 帮助用户判断范围是否合理（32/3230 精细 vs 3200/3230 近全放行）
const previewRatio = computed(() => {
  const r = previewResult.value
  if (!r || r.error || !r.total) return null
  return r.count / r.total
})

const ratioText = computed(() => {
  const r = previewRatio.value
  if (r === null) return ''
  const pct = r > 0 && r < 0.1 ? (r * 100).toFixed(1) : Math.round(r * 100)
  return pct + '%'
})

// [Phase 3.14] v14 dialog 标题 — 含资源类型显示名（如「添加条件 · 业务对象」）
const dialogTitle = computed(() => {
  // [v45 2026-08-27] 浏览态只读弹窗标题
  if (props.readonly) return '查看条件（只读） · ' + (form.rowLabel || form.resource_type || '条件规则')
  const prefix = isEditMode.value ? '编辑条件 · ' : '添加条件 · '
  return prefix + (form.rowLabel || form.resource_type || '条件规则')
})

// [v12 + v26 2026-08-25/26] Rule Builder 状态
// [v26] 数据模型升级: 引入 rootGroup 树形包装 (GroupNode), 但 customRules 保持扁平
//   - 序列化时: serialize(rootGroup) 自动递归遍历 children
//   - 兼容性: 现有 addCustomRule/removeCustomRule/onCustomRuleFieldChange 等函数无需改动
//   - Phase 4 嵌套组支持时, 只需把 rootGroup 升级为完整树, 函数无影响
// 每行规则: { id, connector(首行无), field, operator, value, fieldType, relationObject }
// 头部产品对照: SAP/AWS IAM/Salesforce/Airtable 都是「字段 + 操作符 + 值」多行
// [BUG fix] ruleIdCounter 必须在 createDefaultRule 调用前声明（TDZ 报错修复）
let ruleIdCounter = 1
function createDefaultRule(connector, defaultField = '') {
  return {
    type: 'rule',                  // [v26] 树形节点类型
    id: ruleIdCounter++,
    connector: connector || 'AND',  // 仅非首行有效
    field: defaultField,
    // [Phase 3.19 2026-08-26] v19: 默认操作符改为 IN（多选「在列表中」）
    //   头部产品对照：SAP/Salesforce 范围类规则默认都是 IN/包含语义
    //   用户反馈：「默认是 include」= 默认就是「包含这些值」语义
    //   IN 自动多选 picker，与业务主键字段天然契合
    operator: 'IN',
    value: '',
    fieldType: 'string',
    relationObject: '',
    isBusinessKey: false,
    // [v21 2026-08-26] 枚举字段标识：固定值（enum_values）或引用枚举（enum_ref）
    isEnum: false,
    enumValues: null,
    enumRef: null,
    // [Phase 3.16] v16: picker 状态 + FK picker 的已选 ID 缓存
    pickerVisible: false,
    pickerSelectedIds: [],  // 已选 ID（数组，多选用）
    pickerSelectedItems: [],  // 已选项 [{id, name, code}]，用于 display
  }
}

// [v26 2026-08-26] 顶层 root group — UI 不可见, 仅作序列化 anchor
//   - 用 ref 而非 computed: 让 ConditionRuleBuilder 的 @update:tree 能直接赋值
//   - children 始终引用 customRules.value 的同一引用 (Vue reactivity 自动同步)
//   - 序列化时 serialize(treeRef.value) 会输出 flat 表达式 (顶层不带括号, 与 v25 一致)
//   - Phase 4 嵌套组支持时, 升级 treeRef 为真正的嵌套树, 函数无影响
const customRules = ref([createDefaultRule()])
const treeRef = ref({
  type: 'group',
  id: 'root',
  connector: 'AND',
  children: customRules.value,
})

/**
 * ConditionRuleBuilder 内部 emit('update:tree', newTree) 时回写
 *   - 把 newTree.children 同步回 customRules（保持单层 v1 的 flat 数据源）
 *   - 同步后更新 treeRef.children 引用，避免组件 prop 引用漂移
 */
function onTreeUpdate(newTree) {
  if (!newTree) return
  // 用新 children 替换原 customRules（保留引用以便组件继续响应式追踪）
  customRules.value = newTree.children || []
  treeRef.value = { ...newTree, children: customRules.value }
}

const showAdvanced = ref(false)

// [v52 2026-08-27] 高级模式手编表达式 → 直接作为保存源
//   此前 textarea 只写 customCondition，handleSave 读 form.condition，
//   手编公式根本不会落库（隐性断裂）。对齐头部产品「源码视图即真相」惯例：
watch(customCondition, (val) => {
  form.condition = val
})

// [Phase 3.18 2026-08-26] v18: 找出资源的业务主键字段（优先 id，兜底 code）
//   - 后端 field-metadata 接口返回 is_business_key 标志（基于 YAML semantics.business_key）
//   - 头部产品对照：
//     - SAP PFCG Authorization: 自身字段（业务主键）支持 F4 Search Help，按 Object 自身取候选
//     - Salesforce Lookup Dialog: default field 是 Id（业务键），返回值也是 Id
//   - 用于：Rule Builder 默认第一行字段 = 业务主键，自动触发 self-reference picker
//   - 注意：id 在 backend 不一定有 is_business_key=true（它是技术主键，YAML 可能未标 business_key）
//   - 但用户已确认 id 为默认，所以前端主动识别 id/code/db_column 为「业务主键候选」
function getBusinessKeyField() {
  // 优先 id（用户选择「id (技术主键)」）
  const idField = fieldMetadata.value.find(f => f.db_column === 'id')
  if (idField) return idField
  // 兜底 code
  const codeField = fieldMetadata.value.find(f => f.db_column === 'code')
  if (codeField) return codeField
  // 再兜底：任意 is_business_key=true 字段
  return fieldMetadata.value.find(f => f.is_business_key) || null
}

function syncCustomRules() {
  // [Phase 3.13] v13 简化: 删掉 mode 检查 (v13 只有 custom mode)
  const generated = serialize(treeRef.value)
  // 写回 customCondition + form.condition, 让高级模式 textarea 同步显示
  customCondition.value = generated
  form.condition = generated
  // [v45 2026-08-27] 同步生成人类可读表达式（字段中文 label + picker 显示名）
  const labelMap = {}
  fieldMetadata.value.forEach((f) => { if (f.db_column) labelMap[f.db_column] = f.name || f.db_column })
  if (!generated) {
    form.condition_display = ''
    return
  }
  // [v57 2026-08-27] 纯业务主键条件（只含资源自身 id 的 IN/=，无 AND/OR 混合其他字段）
  //   → 描述直接展示名称项列表（「供应链计划BO、库存管理BO」），
  //   不再重复「业务对象 IN (...)」的字段前缀（对齐 Salesforce/Fiori：越简单越业务化）
  const flatRules = []
  const walk = (n) => {
    if (!n) return
    if (n.type === 'rule') flatRules.push(n)
    else (n.children || []).forEach(walk)
  }
  walk(treeRef.value)
  const pureBizKeyIn = flatRules.length > 0
    && flatRules.every((r) => r.isBusinessKey && ['IN', '='].includes(r.operator))
  if (pureBizKeyIn) {
    const names = []
    for (const r of flatRules) {
      const itemNames = (r.pickerSelectedItems || []).map((i) => i.name || String(i.id ?? '')).filter(Boolean)
      if (itemNames.length) names.push(...itemNames)
      else {
        const fallback = String(r.value || '').trim()
        if (fallback) names.push(fallback)
      }
    }
    form.condition_display = names.join('、')
  } else {
    form.condition_display = serializeDisplay(treeRef.value, labelMap)
  }
}

// [Phase 3.13 2026-08-25] v13 简化：删掉 dimension mode 全部相关 state 和 function
//   - 删掉 valueNameMap / activeValueHelp / activeMultiSelect / valueHelpOptions /
//     valueHelpSearch / valueHelpTimeout / HIDDEN_DIMS / sortedDimensions /
//     availableDimensions / isDimSelected / toggleDimension / onOperatorChange /
//     onDisplayValueInput / getValuePlaceholder / updateCondition / getFriendlyCondition

// 字段元数据（Rule Builder 需要）
const fieldMetadata = ref([])
const showFieldHelp = ref(false)

// [Phase 3.14] v14 删掉 onResourceTypeChange — 不再有 select 触发 onChange
//   资源类型由父组件传入 → editingRule 初始化时 loadFieldMetadata() 已足够

// FR-005 OverlapWarning: 查询 Section 1 (权限维度) 与本规则（Section 3）的字段重复
const overlapWarnings = ref([])

async function fetchOverlapWarnings() {
  if (!props.roleId || !form.resource_type) return
  try {
    const r = await permService.loadOverlapWarnings(props.roleId, form.resource_type)
    if (r.success) {
      overlapWarnings.value = r.data?.overlaps || r.data?.warnings || []
    }
  } catch (e) {
    console.warn('overlap check failed', e)
  }
}

// [Phase 3.13 2026-08-25] v13 简化：删掉 dimension mode 全部辅助函数
//   - onDeniedChange — is_denied 已去除
//   - onDimValueFocus / onMultiSelectFocus / searchMultiSelect / isValueSelected /
//     toggleMultiSelectValue / removeTag / refreshChildDimensions /
//     onDimValueBlur / loadValueHelp / searchValueHelp / selectValueHelp /
//     clearSingleValue — 维度 value help 流程已废弃

// [Phase 3.13 2026-08-25] v13 简化：清理 dimension mode 残留
//   - loadDimensions — 不再需要 dimensions 数据（picker/expression 在 ResourceActionMatrix 中处理）
//   - parseConditionToDimConfigs / loadValueHelpForEdit / loadSingleValueHelpForEdit
//     — 旧的反向填充逻辑（dimConfigs 已被删）
//   - handleSave 中不再传 permission_level / is_denied（已去除）

// ========== 字段元数据（Rule Builder 用） ==========

async function loadFieldMetadata() {
  if (!form.resource_type) return
  try {
    const r = await permService.loadFieldMetadata(form.resource_type)
    if (r.success) {
      fieldMetadata.value = r.data || []
      // [v18+v28 2026-08-26] 默认第一行规则的字段 = 资源自身的业务主键（id 优先，code 兜底）
      //   v18 头部产品对照：SAP/Salesforce Rule Builder 默认字段都是业务主键
      //   v28 修复: 委托 initRuleForField 完成 operator/value/picker 缓存同步
      //   解决历史 bug: 默认字段是 boolean/datetime 时 operator='IN' 非法导致 UI 显示异常
      if (!isEditMode.value && fieldMetadata.value.length > 0 && customRules.value.length > 0) {
        const firstRule = customRules.value[0]
        if (!firstRule.field) {
          const businessKey = getBusinessKeyField()
          if (businessKey) {
            // v28: 用纯函数 initRuleForField 替换原手工 5 行字段赋值,
            //   确保与 Row.onFieldChange 走完全一致的初始化逻辑
            const newRule = initRuleForField(firstRule, businessKey)
            // 保留自定义字段 (id/connector), 其他按 newRule 覆盖
            customRules.value[0] = newRule
            syncCustomRules()
          }
        }
      }
    }
  } catch (e) {
    console.error('Failed to load field metadata:', e)
  }
}

function insertField(field) {
  // [v49 2026-08-27] 浏览态只读：字段参考仅可查看，不可插入
  if (props.readonly) return
  // [Phase 3.13] v13 简化：高级模式 textarea 仍可用「字段参考」点击插入
  const current = customCondition.value
  const fieldRef = field.db_column
  if (current) {
    customCondition.value = current + ' ' + fieldRef
  } else {
    customCondition.value = fieldRef
  }
  // 同步 Rule Builder 的显示（这里只更新 textarea，不回写 builder）
  form.condition = customCondition.value
}

async function doPreview() {
  if (!form.condition || !form.resource_type) return
  previewing.value = true
  try {
    const r = await permService.previewCondition({
      condition: form.condition,
      resource_type: form.resource_type,
    })
    if (r.success) {
      previewResult.value = r.data
      previewStale.value = false  // [v61] 刷新完成，移除「条件已变更」标记
    } else {
      message.error(r.message || '预览规则失败，请稍后重试')
    }
  } catch (e) {
    message.error('预览规则失败，请检查网络后重试', e)
  } finally {
    previewing.value = false
  }
}

async function handleSave() {
  if (!form.condition) return
  saving.value = true
  try {
    // [Phase 3.13] v13 简化：save payload 不再含 permission_level / is_denied
    const payload = {
      permission_set_id: props.roleId,
      resource_type: form.resource_type,
      condition: form.condition,
      inherit_to_children: form.inherit_to_children,
      propagate_to_parents: form.propagate_to_parents,
    }
    // [v48 2026-08-27] 区分新建/更新：
    //   父组件打开弹窗时传入后端 rule_id（来自 mergeSavedConditionRules 回读）
    //   → 有 id 走 PUT 更新原记录；无 id 走 POST 新建。
    //   修复"变更条件后保存，库里堆积多条规则，刷新读最旧一条"的 bug。
    const existingRuleId = props.editingRule?.rule_id
    const r = existingRuleId
      ? await permService.updateConditionRule(existingRuleId, payload)
      : await permService.saveConditionRule(payload)
    if (r.success) {
      message.success(existingRuleId ? '权限规则更新成功' : '权限规则添加成功')
      // [Phase 3.16 2026-08-25] v16：把当前 form 数据传给父组件
      //   让父组件（PermissionConfigPanel）把 expression 同步到 scopeMatrixLocal
      //   这样 ResourceActionMatrix 的「已配置」chip 状态可识别
      emit('saved', {
        resource_type: form.resource_type,
        condition: form.condition,
        condition_display: form.condition_display,  // [v45 2026-08-27] 人类可读表达式
        inherit_to_children: form.inherit_to_children,
        propagate_to_parents: form.propagate_to_parents,
        rule_id: existingRuleId || r.data?.id || null,  // [v48] 新建时回填后端 id
        // [v46 2026-08-27] 结构化规则快照（含 pickerSelectedItems 显示名缓存）
        //   父组件存入 scopeMatrix.__rules，再次打开弹窗时精确回填 builder
        rules: JSON.parse(JSON.stringify(customRules.value)),
      })
      emit('close')
    } else {
      message.error(r.message || '保存权限规则失败，请稍后重试')
    }
  } catch (e) {
    message.error('保存权限规则失败，请检查网络后重试', e)
  } finally {
    saving.value = false
  }
}

// [v47 2026-08-27] 从解析行重建完整规则对象（fieldType/relationObject/enum 等来自 fieldMetadata）
// 注意：本文件是纯 JS <script setup>，禁止 TS 类型注解
function buildRuleFromParsed(row) {
  const meta = fieldMetadata.value.find((f) => f.db_column === row.field)
  return {
    type: 'rule',
    id: ruleIdCounter++,
    connector: row.connector || 'AND',
    field: row.field,
    operator: row.operator,
    value: row.value || '',
    fieldType: meta?.field_type || 'string',
    relationObject: meta?.relation_object || '',
    isBusinessKey: !!(meta?.is_business_key || row.field === 'id'),
    isEnum: !!meta?.is_enum,
    enumValues: meta?.enum_values || null,
    enumRef: meta?.enum_ref || null,
    pickerVisible: false,
    pickerSelectedIds: [],
    pickerSelectedItems: [],
  }
}

// [v47+v54] 名称水合：反解析出的规则没有 pickerSelectedItems 缓存，
//   拉一次实例列表，把 ID 映射回显示名（与 picker 同源，展示一致）
async function hydratePickerNames(rules) {
  for (const r of rules) {
    const ids = String(r.value || '').split(',').map((s) => s.trim()).filter(Boolean)
    if (!ids.length) continue
    if (r.isEnum && Array.isArray(r.enumValues)) {
      r.pickerSelectedIds = ids.slice()
      r.pickerSelectedItems = ids.map((id) => {
        const ev = r.enumValues.find((e) => String(e.value) === id)
        return { id, name: ev?.label || id, code: id }
      })
      continue
    }
    if (r.fieldType === 'datetime' || r.fieldType === 'boolean') continue
    const targetBo = r.isBusinessKey ? form.resource_type : r.relationObject
    if (!targetBo) continue
    try {
      // [v54 2026-08-27] 后端 instances 接口 page_size 上限 100，超限静默回退 20
      //   （permission_dimension_api.get_dimension_instances L1409）。
      //   此前一次请求 page_size=500 实际只拿到前 20 条，
      //   目标 ID 不在其中时名称水合失败，tag 显示裸 ID。
      //   修复：按需循环翻页（每页 100）直至凑齐全部目标 ID 或遍历完毕。
      const pending = new Set(ids.map(String))
      const byId = new Map()
      for (let page = 1; page <= 100 && pending.size > 0; page++) {
        const res = await permService.loadDimensionInstances(targetBo, { page, page_size: 100 })
        const insts = res.data?.instances || res.data || []
        if (!Array.isArray(insts) || insts.length === 0) break
        for (const inst of insts) {
          byId.set(String(inst.id), inst)
          pending.delete(String(inst.id))
        }
        const total = Number(res.data?.pagination?.total_count || 0)
        if (total && page * 100 >= total) break
      }
      r.pickerSelectedIds = ids.slice()
      r.pickerSelectedItems = ids.map((id) => {
        const inst = byId.get(String(id))
        return { id, name: inst?.name || inst?.code || String(id), code: inst?.code || '' }
      })
    } catch (e) {
      console.warn('[ConditionRuleDialog] hydratePickerNames failed:', targetBo, e)
    }
  }
}

onMounted(async () => {
  // [Phase 3.14] v14 dialog 现在 100% 由父组件传入的 props.editingRule 初始化
  //   资源类型不是用户选的，而是父组件 handleOpenConditionDialog 传进来的（来自资源行）
  if (props.editingRule) {
    const rule = props.editingRule
    form.resource_type = rule.resource_type || ''
    form.rowLabel = rule.rowLabel || ''  // [Phase 3.14] 新增 rowLabel 字段（来自 payload）
    form.condition = rule.condition || ''
    form.inherit_to_children = rule.inherit_to_children !== false
    form.propagate_to_parents = rule.propagate_to_parents !== false

    // [Phase 3.18 2026-08-26] v18: 只有「已存在条件」才算编辑模式
    isEditMode.value = !!rule.condition

    // [Phase 3.14] v14 资源类型是确定的，初始化时直接调 loadFieldMetadata
    if (form.resource_type) {
      await loadFieldMetadata()   // [v47] 改为 await：解析表达式依赖 fieldMetadata
      fetchOverlapWarnings()
    }

    // [v46 2026-08-27] 【会话内回填】保存时缓存的 __rules 快照（含 picker 显示名）精确回填
    if (Array.isArray(rule.initialRules) && rule.initialRules.length > 0) {
      customRules.value = JSON.parse(JSON.stringify(rule.initialRules))
      treeRef.value = { type: 'group', id: 'root', connector: 'AND', children: customRules.value }
      syncCustomRules()
    } else if (form.condition && String(form.condition).trim()) {
      // [v47+v52 2026-08-27] 刷新后回填：无快照但有持久化表达式
      //   头部产品惯例（AWS IAM 可视化/JSON 双视图、Datadog builder/searchbar 双模式）：
      //     - 表达式能完整反解析成结构化规则 → Builder 可视化展示
      //     - 反解析有损（嵌套括号 / LIKE 等手写式）→ 回退「源码视图」并默认展开高级模式，
      //       公式原文不被静默截断、也不藏进折叠区
      const termCount = form.condition.split(/\s+(?:AND|OR)\s+/).filter((p) => p.trim()).length
      const rows = parseConditionToRuleRows(form.condition)
      // [v54] 仅当公式无法完整还原为结构化规则（手写式/复杂式）才默认展开；
      //   基础规则由 Builder 完整表达，保持折叠
      if (rows.length > 0 && rows.length === termCount) {
        customRules.value = rows.map(buildRuleFromParsed)
        treeRef.value = { type: 'group', id: 'root', connector: 'AND', children: customRules.value }
        await hydratePickerNames(customRules.value)
        syncCustomRules()
      } else {
        customCondition.value = form.condition
        showAdvanced.value = true
      }
    }
  }
})
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

/* [Phase 3.13 2026-08-25] v13 简化：
 *   删掉 .level-options / .denied-label / .denied-hint / .level-hint-denied / .condition-tabs /
 *   .dimension-item / .dim-label / .dim-name / .dim-field / .dim-meta / .dim-config /
 *   .dim-operator / .dim-value / .empty-dim — 这些是 dimension mode 的样式
 *   删掉 .dim-value-wrapper / .value-help-dropdown / .value-help-search / .value-help-list /
 *   .value-help-item / .value-help-checkbox / .value-help-id / .value-help-name /
 *   .value-help-path / .multi-select-wrapper / .single-select-wrapper / .selected-tags /
 *   .value-tag / .single-tag / .tag-remove / .multi-select-input / .single-select-input —
 *     维度 value help 流程已废弃
 *   删掉 .condition-preview / .condition-friendly / .friendly-label / .friendly-text —
 *     「生成的条件表达式」+「业务语义」已去除
 *
 *   保留（v13 仍需要）：
 *     - .form-group / .form-label / .required / .checkbox-label
 *     - .overlap-warning (FR-005 仍生效)
 *     - .option-label / .option-hint（向下继承/向上传播）
 *     - .rule-builder / .rule-row / .rule-*（v12 Rule Builder）
 *     - .advanced-toggle*（v12 高级模式折叠）
 *     - .field-help-* + .condition-input + .condition-hint（高级模式 textarea 用）
 *     - .preview-section / .preview-*（预览匹配）
 *
 * [Phase 3.14 2026-08-25] v14 新增：
 *   .resource-type-readonly / .resource-type-label / .resource-type-value / .resource-type-display
 *     — 资源类型只读标识（替代原 select）*/

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
/* 说明文字换行到下一行, 左缩进对齐标题文字起点(checkbox 16px + gap), 用 xs 浅灰弱化 */
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
  /* 三列统一 xs 字号, 避免 name(sm) 与 column/type(xs) 在同一行大小不一 */
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