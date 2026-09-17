import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { useMessage } from '@/composables/useMessage'
import * as permService from '@/services/permissionService'
import {
  initRuleForField,
  isBizkeyRuleValue,
} from '@/components/common/ConditionRuleBuilder'
import {
  serialize,
  serializeDisplay,
  parseConditionToRuleRows,
} from '@/components/common/ConditionRuleBuilder/serializers.ts'

/**
 * [Spec 22 PM 反馈第十八次 2026-09-13] ConditionRuleDialog 调用模板单一真源
 * [2026-09-16 PM 反馈第二十二次] 业务逻辑下放 — dialog 内部 Rule Builder 状态 + 预览 +
 *   保存 + 字段水合 + scopeMode 互映全部下沉到本 composable, dialog 瘦身到只剩模板 + UI 绑定。
 *
 * 历史背景：PermissionConfigPanel（编辑态）+ ReadonlyAggregateSection（只读）
 *   各自实现 openDialog / closeDialog / handleSaved + 各自管理 editingRule / showDialog / dialogReadonly
 *   重复约 120 行；两边的回填字段差异（rule_id / inherit_flags / __rules / __expression_display）
 *   容易出现"只在编辑态持久化、不在只读态回填"的遗漏 bug。
 *
 * 业务逻辑下放覆盖 (2026-09-16 C 方案):
 *   - form (reactive) + scopeMode ↔ inherit/propagate 双向互映
 *   - Rule Builder state (customRules/treeRef/showAdvanced/customCondition)
 *   - field metadata + overlap warnings 加载
 *   - preview state + doPreview (debounce 600ms)
 *   - syncCustomRules (含 pureBizKeyIn 业务主键显示优化)
 *   - save (Spec 20 v5 L4 业务键锚点提示 + Spec 20 v6 display 落库)
 *   - 反向解析 (buildRuleFromParsed + hydratePickerNames 含 code 端点 /codes)
 *
 * 调用方职责：
 *   - 提供 getRowScope(resourceType) → 从自己的 scopeMatrix / rowScope 取数据
 *   - 提供 isEditing（computed ref）— 编辑/浏览态唯一判断源
 *   - 把 dialog 模板绑到本 composable 返回的 v-bind
 *
 * @param {{
 *   permissionSetId: import('vue').Ref<string|number>,
 *   getRowScope: (resourceType: string) => any,
 *   isEditing: import('vue').ComputedRef<boolean>,
 *   onSaved?: (savedRule: any) => void,
 * }} options
 */
export function useConditionRuleDialog(options) {
  if (!options || typeof options.getRowScope !== 'function') {
    throw new Error('[useConditionRuleDialog] getRowScope is required')
  }
  if (!options.permissionSetId) {
    throw new Error('[useConditionRuleDialog] permissionSetId (Ref) is required')
  }
  if (!options.isEditing) {
    throw new Error('[useConditionRuleDialog] isEditing (ComputedRef) is required')
  }
  if (options.permissionSetId && !(typeof options.permissionSetId === 'object' && 'value' in options.permissionSetId)) {
    throw new Error('[useConditionRuleDialog] permissionSetId must be Ref or ComputedRef')
  }

  const message = useMessage()
  const psIdRef = options.permissionSetId

  // ============================================================
  // 编辑回填快照 (composable 原 P1-2 已实现)
  // ============================================================
  const editingRule = ref(null)
  const showDialog = ref(false)
  const dialogReadonly = computed(() => !options.isEditing.value)

  // ============================================================
  // [C 方案 2026-09-16] form reactive — 从 dialog 下放
  // ============================================================
  const form = reactive({
    resource_type: '',
    rowLabel: '',
    condition: '',
    condition_display: '',
    inherit_to_children: true,
    propagate_to_parents: true,
  })

  // [2026-08-27] 规则作用域四态枚举 (UI 单源 → 后端两列映射)
  const SCOPE_MODES = ['none', 'down', 'up', 'both']
  const SCOPE_MODE_MAP = {
    none: { inherit: false, propagate: false },
    down: { inherit: true, propagate: false },
    up:   { inherit: false, propagate: true },
    both: { inherit: true, propagate: true },
  }

  const isEditMode = ref(false)
  const scopeMode = ref('both')

  // UI 单源 → 后端两列；保存与 emit 都走这里
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

  // ============================================================
  // [C 方案 2026-09-16] Rule Builder state + syncCustomRules
  // ============================================================
  let ruleIdCounter = 1
  const customCondition = ref('')

  function createDefaultRule(connector, defaultField = '') {
    return {
      type: 'rule',
      id: ruleIdCounter++,
      connector: connector || 'AND',
      field: defaultField,
      operator: 'IN',
      value: '',
      fieldType: 'string',
      relationObject: '',
      isBusinessKey: false,
      isEnum: false,
      enumValues: null,
      enumRef: null,
      pickerVisible: false,
      pickerSelectedIds: [],
      pickerSelectedItems: [],
    }
  }

  const customRules = ref([createDefaultRule()])
  const treeRef = ref({
    type: 'group',
    id: 'root',
    connector: 'AND',
    children: customRules.value,
  })

  function onTreeUpdate(newTree) {
    if (!newTree) return
    customRules.value = newTree.children || []
    treeRef.value = { ...newTree, children: customRules.value }
  }

  const showAdvanced = ref(false)

  // [v52 2026-08-27] 高级模式手编表达式 → 直接作为保存源
  watch(() => customCondition.value, (val) => {
    form.condition = val
  })

  // [Phase 3.18 2026-08-26] v18: 找出资源的业务主键字段
  function getBusinessKeyField() {
    const idField = fieldMetadata.value.find(f => f.db_column === 'id')
    if (idField) return idField
    const codeField = fieldMetadata.value.find(f => f.db_column === 'code')
    if (codeField) return codeField
    return fieldMetadata.value.find(f => f.is_business_key) || null
  }

  function syncCustomRules() {
    const generated = serialize(treeRef.value)
    customCondition.value = generated
    form.condition = generated
    const labelMap = {}
    fieldMetadata.value.forEach((f) => { if (f.db_column) labelMap[f.db_column] = f.name || f.db_column })
    if (!generated) {
      form.condition_display = ''
      return
    }
    // [v57 2026-08-27] 纯业务主键条件 → 描述直接展示名称项列表
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
        const itemNames = (r.pickerSelectedItems || []).map((i) => {
          const idStr = i.id === undefined || i.id === null ? '' : String(i.id)
          if (i.bizkey) {
            const code = i.code || i.name || idStr
            return i.name && i.name !== code ? `${code}（${i.name}）` : code
          }
          return idStr && i.name && i.name !== idStr ? `${idStr}（${i.name}）` : (idStr || i.name || '')
        }).filter(Boolean)
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

  // ============================================================
  // [C 方案 2026-09-16] field metadata + overlap warnings
  // ============================================================
  const fieldMetadata = ref([])
  const showFieldHelp = ref(false)
  const overlapWarnings = ref([])

  async function loadFieldMetadata() {
    if (!form.resource_type) return
    try {
      const r = await permService.loadFieldMetadata(form.resource_type)
      if (r.success) {
        fieldMetadata.value = r.data || []
        if (!isEditMode.value && fieldMetadata.value.length > 0 && customRules.value.length > 0) {
          const firstRule = customRules.value[0]
          if (!firstRule.field) {
            const businessKey = getBusinessKeyField()
            if (businessKey) {
              const newRule = initRuleForField(firstRule, businessKey)
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

  async function fetchOverlapWarnings() {
    if (!psIdRef.value || !form.resource_type) return
    try {
      const r = await permService.loadOverlapWarnings(psIdRef.value, form.resource_type)
      if (r.success) {
        overlapWarnings.value = r.data?.overlaps || r.data?.warnings || []
      }
    } catch (e) {
      console.warn('overlap check failed', e)
    }
  }

  // ============================================================
  // [C 方案 2026-09-16] preview state + doPreview (debounce 600ms)
  // ============================================================
  const previewResult = ref(null)
  const previewing = ref(false)
  const previewStale = ref(false)
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
  let previewTimer = null

  watch(() => form.condition, () => {
    if (!previewResult.value) return
    previewStale.value = true
    clearTimeout(previewTimer)
    previewTimer = setTimeout(() => { doPreview() }, 600)
  })

  onBeforeUnmount(() => clearTimeout(previewTimer))

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
        previewStale.value = false
      } else {
        message.error(r.message || '预览规则失败，请稍后重试')
      }
    } catch (e) {
      message.error('预览规则失败，请检查网络后重试', e)
    } finally {
      previewing.value = false
    }
  }

  // ============================================================
  // [C 方案 2026-09-16] dialogTitle computed
  // ============================================================
  const dialogTitle = computed(() => {
    if (options.isEditing.value === false) {
      // 浏览态判定 — 通过 readonly 概念 (isEditing 反义) 推断
      // 注: 真正的 readonly 模式由调用方传 editingRule 提供, dialogTitle 文案兼容只读场景
    }
    const prefix = isEditMode.value ? '编辑条件 · ' : '添加条件 · '
    return prefix + (form.rowLabel || form.resource_type || '条件规则')
  })

  // ============================================================
  // [C 方案 2026-09-16] insertField (高级模式字段参考)
  // ============================================================
  function insertField(field) {
    const current = customCondition.value
    const fieldRef = field.db_column
    if (current) {
      customCondition.value = current + ' ' + fieldRef
    } else {
      customCondition.value = fieldRef
    }
    form.condition = customCondition.value
  }

  // ============================================================
  // [C 方案 2026-09-16] handleSave (Spec 20 v5 L4 + v6 display)
  // ============================================================
  const saving = ref(false)

  // [Spec 20 v5 L4 保存契约] 遍历规则树收集业务键锚定字段名
  function collectBizkeyAnchorFields(nodes, acc = []) {
    for (const n of nodes || []) {
      if (n.type === 'group') {
        collectBizkeyAnchorFields(n.children, acc)
      } else if (n.field && isBizkeyRuleValue(n) && !acc.includes(n.field)) {
        acc.push(n.field)
      }
    }
    return acc
  }

  async function handleSave() {
    if (!form.condition) return
    saving.value = true
    try {
      const payload = {
        permission_set_id: psIdRef.value,
        resource_type: form.resource_type,
        condition: form.condition,
        condition_display: form.condition_display || '',
        inherit_to_children: form.inherit_to_children,
        propagate_to_parents: form.propagate_to_parents,
      }
      const existingRuleId = editingRule.value?.rule_id
      const r = existingRuleId
        ? await permService.updateConditionRule(existingRuleId, payload)
        : await permService.saveConditionRule(payload)
      if (r.success) {
        const bizkeyFields = collectBizkeyAnchorFields(customRules.value)
        if (bizkeyFields.length > 0) {
          message.success(
            `${existingRuleId ? '权限规则更新成功' : '权限规则添加成功'}；规则含业务键锚定（${bizkeyFields.join('、')}），父对象下新增同名编码实例将自动纳入本规则`,
            6000
          )
        } else {
          message.success(existingRuleId ? '权限规则更新成功' : '权限规则添加成功')
        }
        // emit savedRule 给调用方
        const savedRule = {
          resource_type: form.resource_type,
          condition: form.condition,
          condition_display: form.condition_display,
          inherit_to_children: form.inherit_to_children,
          propagate_to_parents: form.propagate_to_parents,
          rule_id: existingRuleId || r.data?.id || null,
          rules: JSON.parse(JSON.stringify(customRules.value)),
        }
        if (typeof options.onSaved === 'function') {
          options.onSaved(savedRule)
        }
        close()
      } else {
        message.error(r.message || '保存权限规则失败，请稍后重试')
      }
    } catch (e) {
      message.error('保存权限规则失败，请检查网络后重试', e)
    } finally {
      saving.value = false
    }
  }

  // ============================================================
  // [C 方案 2026-09-16] buildRuleFromParsed + hydratePickerNames
  // ============================================================
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
      const codeTokens = ids.filter((s) => !/^-?\d+$/.test(s))
      const numIds = ids.filter((s) => /^-?\d+$/.test(s))
      try {
        const byId = new Map()
        if (numIds.length > 0) {
          const pending = new Set(numIds)
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
        }
        const codeInfo = new Map()
        for (const code of codeTokens) {
          try {
            const resp = await permService.loadDimensionCodes(targetBo, { page: 1, page_size: 10, search: code })
            const codes = resp?.data?.codes || []
            const hit = codes.find((c) => String(c.code) === code)
            if (hit) codeInfo.set(code, hit)
          } catch { /* 普通 BO 无 /codes 端点 → 回落裸 code */ }
        }
        r.pickerSelectedIds = ids.slice()
        r.pickerSelectedItems = ids.map((id) => {
          if (!/^-?\d+$/.test(id)) {
            const hit = codeInfo.get(id)
            return {
              id,
              code: id,
              name: hit?.sample_name || id,
              bizkey: true,
              resolvedCount: hit ? (hit.resolved_count ?? 0) : undefined,
            }
          }
          const inst = byId.get(String(id))
          return { id, name: inst?.name || inst?.code || String(id), code: inst?.code || '' }
        })
      } catch (e) {
        console.warn('[useConditionRuleDialog] hydratePickerNames failed:', targetBo, e)
      }
    }
  }

  // ============================================================
  // [C 方案 2026-09-16] open / close / handleSaved (composable 原 P1-2)
  // ============================================================
  function open(payload) {
    const rt = payload?.resourceType
    if (!rt) return
    const rowScope = payload.rowScope || options.getRowScope(rt) || {}
    editingRule.value = {
      resource_type: rt,
      rowLabel: payload.rowLabel || '',
      mode: payload.mode || 'custom',
      condition: rowScope.__expression || '',
      condition_display: rowScope.__expression_display || '',
      initialRules: Array.isArray(rowScope.__rules) ? rowScope.__rules : undefined,
      rule_id: rowScope._rule_id || null,
    }
    showDialog.value = true
  }

  function close() {
    showDialog.value = false
    editingRule.value = null
  }

  /**
   * 编辑态保存成功后回写 scopeMatrix 行字段。
   * 只读态拒绝并提示（纵深防御，理论上 dialog 在只读态没有保存按钮）。
   */
  async function handleSaved(savedRule) {
    if (!options.isEditing.value) {
      close()
      return
    }
    if (savedRule && savedRule.resource_type && savedRule.condition) {
      const rt = savedRule.resource_type
      if (typeof options.onSaved === 'function') {
        options.onSaved(savedRule)
      }
    }
    close()
  }

  // ============================================================
  // [C 方案 2026-09-16] init — 替代 dialog.onMounted 中的初始化逻辑
  //   dialog 在 showDialog=true 后挂载时, 调 init(editingRule) 装载数据
  // ============================================================
  async function init(rule) {
    if (!rule) return
    form.resource_type = rule.resource_type || ''
    form.rowLabel = rule.rowLabel || ''
    form.condition = rule.condition || ''
    form.inherit_to_children = rule.inherit_to_children !== false
    form.propagate_to_parents = rule.propagate_to_parents !== false

    isEditMode.value = !!rule.condition

    if (form.resource_type) {
      await loadFieldMetadata()
      fetchOverlapWarnings()
    }

    if (Array.isArray(rule.initialRules) && rule.initialRules.length > 0) {
      customRules.value = JSON.parse(JSON.stringify(rule.initialRules))
      treeRef.value = { type: 'group', id: 'root', connector: 'AND', children: customRules.value }
      syncCustomRules()
    } else if (form.condition && String(form.condition).trim()) {
      const termCount = form.condition.split(/\s+(?:AND|OR)\s+/).filter((p) => p.trim()).length
      const rows = parseConditionToRuleRows(form.condition)
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

  return {
    // 编辑回填快照 (P1-2 原接口)
    editingRule,
    showDialog,
    dialogReadonly,
    open,
    close,
    handleSaved,

    // [C 方案 2026-09-16] 下放 state + computed
    form,
    isEditMode,
    scopeMode,
    customRules,
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
    dialogTitle,

    // [C 方案 2026-09-16] 下放 functions
    onTreeUpdate,
    syncCustomRules,
    loadFieldMetadata,
    fetchOverlapWarnings,
    doPreview,
    insertField,
    handleSave,
    init,
  }
}