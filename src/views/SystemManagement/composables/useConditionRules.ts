import { ref, type Ref } from 'vue'
import * as permService from '@/services/permissionService'

interface ConditionRule {
  id: number | string
  resource_type: string
  condition: string
  friendly_condition?: string
  permission_level: 'none' | 'read' | 'write' | 'manage'
  inherit_to_children: boolean
  is_denied: boolean
}

export function useConditionRules(permissionSetId: Ref<string>) {
  const rules = ref<ConditionRule[]>([])
  const loading = ref(false)
  const saving = ref(false)

  async function loadRules() {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态 (permission_set 尚未保存), 后端期望 int permission_set_id
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      rules.value = []
      return
    }

    loading.value = true
    try {
      // [P11 Phase 11] Panel 3 只显示 rule_type='condition' 的规则
      // (其他 rule_type 由各 Panel 自行加载: prohibition/owner/visibility)
      const r = await permService.loadConditionRules({
        permission_set_id: permissionSetId.value,
        rule_type: 'condition'
      })

      if (r.success) {
        rules.value = r.data || []
      } else {
        throw new Error(r.message || '加载条件规则失败')
      }
    } catch (error) {
      console.error('Failed to load condition rules:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function addRule(rule: Omit<ConditionRule, 'id'>) {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int permission_set_id
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      throw new Error('添加失败: 权限集尚未保存, 请先保存权限集')
    }

    saving.value = true
    try {
      const r = await permService.saveConditionRule({
        ...rule,
        permission_set_id: permissionSetId.value
      })

      if (!r.success) {
        throw new Error(r.message || '添加条件规则失败')
      }

      await loadRules()
      return r.data
    } catch (error) {
      console.error('Failed to add condition rule:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  async function updateRule(ruleId: number | string, updates: Partial<ConditionRule>) {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int permission_set_id (Number('new')=NaN, 路径异常)
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      throw new Error('更新失败: 权限集尚未保存, 请先保存权限集')
    }
    saving.value = true
    try {
      const r = await permService.savePermissionRules(
        Number(permissionSetId.value),
        { ...updates, id: ruleId },
        'update'
      )

      if (!r.success) {
        throw new Error(r.message || '更新条件规则失败')
      }

      await loadRules()
      return r.data
    } catch (error) {
      console.error('Failed to update condition rule:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  async function deleteRule(ruleId: number | string) {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 创建态不触发删除 (rules 为空, 不会到这)
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      throw new Error('删除失败: 权限集尚未保存')
    }
    saving.value = true
    try {
      const r = await permService.deleteConditionRule(Number(ruleId))

      if (!r.success) {
        throw new Error(r.message || '删除条件规则失败')
      }

      await loadRules()
      return true
    } catch (error) {
      console.error('Failed to delete condition rule:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  return {
    rules,
    loading,
    saving,
    loadRules,
    addRule,
    updateRule,
    deleteRule
  }
}
