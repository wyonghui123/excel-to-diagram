import { ref, type Ref } from 'vue'
import * as permService from '@/services/permissionService'

// 权限来源：auto=菜单自动派生, include=手动包含, exclude=手动排除, ''=未分配
type PermissionSource = 'auto' | 'include' | 'exclude' | ''

interface Permission {
  code: string
  label: string
  granted: boolean
  source: PermissionSource
}

interface DataScope {
  resource_type: string
  permissions: Array<{ level: string }>
}

interface ActionGroupState {
  granted: boolean
  source: PermissionSource
}

interface StandalonePerm {
  action: string
  label: string
  granted: boolean
  source: PermissionSource
}

interface BoPermissionGroup {
  bo_id: string
  bo_name: string
  groups: Record<string, ActionGroupState>
  standalone: StandalonePerm[]
}

interface Menu {
  menu_code: string
  display_name: string
  menu_path: string
  assigned: boolean
  has_data_scope: boolean
  required_permissions: Permission[]
  bo_permission_groups?: BoPermissionGroup[]
  data_scopes?: DataScope[]
  data_permission_hint?: { resource_types: string[] }
}

// 动作分组常量
const ACTION_GROUPS: Record<string, { label: string; actions: string[] }> = {
  view:   { label: '查看', actions: ['read', 'list'] },
  edit:   { label: '编辑', actions: ['read', 'list', 'create', 'update'] },
  manage: { label: '管理', actions: ['read', 'list', 'create', 'update', 'delete'] },
}

// 层级依赖：高级分组依赖低级分组
const GROUP_DEPENDENCIES: Record<string, string[]> = {
  manage: ['edit'],
  edit: ['view'],
  view: [],
}

export function useMenuPermission(roleId: Ref<string>) {
  const menus = ref<Menu[]>([])
  const loading = ref(false)
  const saving = ref(false)

  async function loadMenus() {
    if (!roleId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态 (role 尚未保存), 后端期望 int role_id
    // 不拦截会触发 GET /api/v1/roles/new/unified-permissions -> 500
    if (!/^\d+$/.test(String(roleId.value))) {
      menus.value = []
      return
    }

    loading.value = true
    try {
      const r = await permService.loadUnifiedPermissions(roleId.value)

      if (r.success && r.data?.menus) {
        menus.value = r.data.menus
      } else {
        console.error('[useMenuPermission] loadMenus unexpected result:', r)
        menus.value = []
      }
    } catch (error) {
      console.error('[useMenuPermission] Failed to load menu permissions:', error)
      menus.value = []
    } finally {
      loading.value = false
    }
  }

  function toggleMenu(menu: Menu) {
    menu.assigned = !menu.assigned

    if (menu.assigned) {
      menu.required_permissions?.forEach(p => {
        p.granted = true
        p.source = 'auto'
      })
      // 重置动作分组状态
      menu.bo_permission_groups?.forEach(bg => {
        Object.keys(bg.groups).forEach(gk => {
          bg.groups[gk].granted = true
          bg.groups[gk].source = 'auto'
        })
        bg.standalone?.forEach(sp => {
          sp.granted = true
          sp.source = 'auto'
        })
      })
    } else {
      // 取消分配时重置权限状态
      menu.required_permissions?.forEach(p => {
        p.granted = false
        p.source = ''
      })
      menu.bo_permission_groups?.forEach(bg => {
        Object.keys(bg.groups).forEach(gk => {
          bg.groups[gk].granted = false
          bg.groups[gk].source = ''
        })
        bg.standalone?.forEach(sp => {
          sp.granted = false
          sp.source = ''
        })
      })
    }
  }

  // 切换动作分组（view/edit/manage）
  function toggleActionGroup(menu: Menu, boId: string, groupKey: 'view' | 'edit' | 'manage') {
    const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
    if (!boGroup) return

    const isActive = boGroup.groups[groupKey]?.granted
    const groupActions = ACTION_GROUPS[groupKey].actions

    if (isActive) {
      // 取消当前分组：只 exclude 当前分组特有的动作，保留低级分组的动作
      const lowerActions = getLowerGroupActions(groupKey)
      const exclusiveActions = groupActions.filter(a => !lowerActions.includes(a))
      exclusiveActions.forEach(action => {
        const perm = menu.required_permissions?.find(p => p.code === `${boId}:${action}`)
        if (perm) {
          perm.granted = false
          perm.source = 'exclude'
        }
      })
    } else {
      // 激活当前分组：include 当前分组的所有动作（隐含低级分组）
      groupActions.forEach(action => {
        const perm = menu.required_permissions?.find(p => p.code === `${boId}:${action}`)
        if (perm) {
          perm.granted = true
          perm.source = 'include'
        }
      })
      // 如果菜单未分配，自动分配
      if (!menu.assigned) {
        menu.assigned = true
      }
    }

    // 重新推导分组状态
    recalcGroupStatus(menu, boId)
  }

  // 切换独立动作
  function toggleStandaloneAction(menu: Menu, boId: string, action: string) {
    const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
    if (!boGroup) return

    const standalone = boGroup.standalone?.find(sp => sp.action === action)
    if (!standalone) return

    standalone.granted = !standalone.granted
    standalone.source = standalone.granted ? 'include' : 'exclude'

    // 同步到 required_permissions
    const perm = menu.required_permissions?.find(p => p.code === `${boId}:${action}`)
    if (perm) {
      perm.granted = standalone.granted
      perm.source = standalone.source
    }

    // 如果激活独立动作且菜单未分配，自动分配
    if (standalone.granted && !menu.assigned) {
      menu.assigned = true
    }
  }

  // 获取低级分组的动作列表
  function getLowerGroupActions(groupKey: string): string[] {
    const deps = GROUP_DEPENDENCIES[groupKey] || []
    let actions: string[] = []
    deps.forEach(dep => {
      actions = actions.concat(ACTION_GROUPS[dep]?.actions || [])
    })
    return [...new Set(actions)]
  }

  // 重新计算动作分组状态
  function recalcGroupStatus(menu: Menu, boId: string) {
    const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
    if (!boGroup) return

    // 从 required_permissions 重新推导
    const boPerms = menu.required_permissions?.filter(p => p.code.startsWith(`${boId}:`)) || []

    Object.keys(ACTION_GROUPS).forEach(gk => {
      const groupActions = ACTION_GROUPS[gk].actions
      const matchingPerms = boPerms.filter(p => {
        const action = p.code.split(':')[1]
        return groupActions.includes(action)
      })

      if (matchingPerms.length === 0) return

      const allGranted = matchingPerms.every(p => p.granted)
      const sources = new Set(matchingPerms.map(p => p.source))

      let groupSource: PermissionSource = ''
      if (sources.has('exclude')) groupSource = 'exclude'
      else if (sources.has('include')) groupSource = 'include'
      else if (sources.has('auto')) groupSource = 'auto'

      if (boGroup.groups[gk]) {
        boGroup.groups[gk].granted = allGranted
        boGroup.groups[gk].source = groupSource
      }
    })
  }

  function selectAll() {
    menus.value.forEach(m => {
      m.assigned = true
      m.required_permissions?.forEach(p => {
        p.granted = true
        p.source = 'auto'
      })
      m.bo_permission_groups?.forEach(bg => {
        Object.keys(bg.groups).forEach(gk => {
          bg.groups[gk].granted = true
          bg.groups[gk].source = 'auto'
        })
        bg.standalone?.forEach(sp => {
          sp.granted = true
          sp.source = 'auto'
        })
      })
    })
  }

  function clearAll() {
    menus.value.forEach(m => {
      m.assigned = false
      m.required_permissions?.forEach(p => {
        p.granted = false
        p.source = ''
      })
      m.bo_permission_groups?.forEach(bg => {
        Object.keys(bg.groups).forEach(gk => {
          bg.groups[gk].granted = false
          bg.groups[gk].source = ''
        })
        bg.standalone?.forEach(sp => {
          sp.granted = false
          sp.source = ''
        })
      })
    })
  }

  function applyDerived(recommendedMenuCodes: string[], derivedPermCodes: string[]) {
    const menuSet = new Set(recommendedMenuCodes)
    const permSet = new Set(derivedPermCodes)

    menus.value.forEach(m => {
      if (menuSet.has(m.menu_code)) {
        m.assigned = true
        m.required_permissions?.forEach(p => {
          if (permSet.has(p.code)) {
            p.granted = true
            p.source = 'auto'
          }
        })
        // 重新推导分组状态
        m.bo_permission_groups?.forEach(bg => {
          recalcGroupStatus(m, bg.bo_id)
        })
      }
    })
  }

  async function save() {
    if (!roleId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int role_id
    if (!/^\d+$/.test(String(roleId.value))) {
      throw new Error('保存失败: 角色尚未保存, 请先保存角色')
    }

    saving.value = true
    try {
      const assignedCodes = menus.value
        .filter(m => m.assigned)
        .map(m => m.menu_code)

      // [FIX v1.0.2] 收集所有需要落库的功能权限
      // source:
      //   'include' - 用户手动 include
      //   'exclude' - 用户手动 exclude
      //   'auto'    - 来自自动推导推荐 (applyDerived 已确认)
      //   'unbound' - 来自 bo_bindings 派生但未勾选, 不写入
      // 'auto' 必须写入, 因为用户看到推荐后没再手动改 = 接受推荐
      // 关键: 这里不能 filter `p.granted === true` !
      //   用户取消勾选 = source='exclude', granted=false,
      //   必须传给后端做 DELETE, 否则后端不知道要 ungrant
      //   之前版本有 `p.granted` 过滤, 导致取消勾选静默丢失
      const permissions = menus.value
        .flatMap(m => m.required_permissions || [])
        .filter(p =>
          p.source === 'include' || p.source === 'exclude' || p.source === 'auto'
        )
        .map(p => ({ code: p.code, granted: !!p.granted }))

      const r = await permService.saveMenuPermissions(roleId.value, { menu_codes: assignedCodes, permissions })

      if (!r.success) {
        throw new Error(r.message || '保存失败')
      }

      return r
    } catch (error) {
      console.error('Failed to save menu permissions:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  return {
    menus,
    loading,
    saving,
    loadMenus,
    toggleMenu,
    toggleActionGroup,
    toggleStandaloneAction,
    selectAll,
    clearAll,
    applyDerived,
    save,
    ACTION_GROUPS
  }
}
