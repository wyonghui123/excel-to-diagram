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

export function useConditionRules(roleId: Ref<string>) {
  const rules = ref<ConditionRule[]>([])
  const loading = ref(false)
  const saving = ref(false)

  async function loadRules() {
    if (!roleId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态 (role 尚未保存), 后端期望 int role_id
    if (!/^\d+$/.test(String(roleId.value))) {
      rules.value = []
      return
    }

    loading.value = true
    try {
      const r = await permService.loadConditionRules({ role_id: roleId.value })

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
    if (!roleId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int role_id
    if (!/^\d+$/.test(String(roleId.value))) {
      throw new Error('添加失败: 角色尚未保存, 请先保存角色')
    }

    saving.value = true
    try {
      const r = await permService.saveConditionRule({
        ...rule,
        role_id: roleId.value
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
    if (!roleId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int role_id (Number('new')=NaN, 路径异常)
    if (!/^\d+$/.test(String(roleId.value))) {
      throw new Error('更新失败: 角色尚未保存, 请先保存角色')
    }
    saving.value = true
    try {
      const r = await permService.savePermissionRules(
        Number(roleId.value),
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
    if (!roleId.value) return
    // [GUARD 2026-06-14] 创建态不触发删除 (rules 为空, 不会到这)
    if (!/^\d+$/.test(String(roleId.value))) {
      throw new Error('删除失败: 角色尚未保存')
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
