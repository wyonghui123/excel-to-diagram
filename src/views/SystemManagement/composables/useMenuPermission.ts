import { ref, type Ref } from 'vue'
import * as permService from '@/services/permissionService'
import {
  GROUP_ACTIONS_MAP,
  type Menu,
  type PermissionSource,
} from '../constants/permissionConstants'

// [2026-08-28 重构清理] 数据模型 interface 已收敛到 permissionConstants.ts（单一事实源）；
// 动作分组映射改用权威常量 GROUP_ACTIONS_MAP（原本地 ACTION_GROUPS 副本删除）。
// 注：分组/独立动作的切换交互已由 ResourceActionMatrix（矩阵 change 回写）承担，
//     原 toggleMenu / toggleActionGroup / toggleStandaloneAction 不可达，已删除。

export function useMenuPermission(permissionSetId: Ref<string>) {
  const menus = ref<Menu[]>([])
  const loading = ref(false)
  const saving = ref(false)

  // [v43 2026-08-27] 是否有未保存变更
  //   - menusSnapshot: loadMenus 时拍的快照（深拷贝）
  //   - isDirty: 与 snapshot 对比后得出
  //   - 重置时机：save() 成功后、clearAll() 后、loadMenus 后
  //   - 用途：底部「保存当前权限」按钮显隐
  let menusSnapshot: Menu[] = []
  const isDirty = ref(false)
  function refreshIsDirty() {
    isDirty.value = JSON.stringify(menus.value) !== JSON.stringify(menusSnapshot)
  }

  async function loadMenus() {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态 (permission_set 尚未保存), 后端期望 int permission_set_id
    // 不拦截会触发 GET /api/v1/permission-sets/new/unified-permissions -> 500
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      menus.value = []
      return
    }

    loading.value = true
    try {
      const r = await permService.loadUnifiedPermissions(permissionSetId.value)

      if (r.success && r.data?.menus) {
        menus.value = r.data.menus
        // [v43 2026-08-27] 加载完成后拍快照 → 重置 isDirty
        menusSnapshot = JSON.parse(JSON.stringify(menus.value))
        isDirty.value = false
      } else {
        console.error('[useMenuPermission] loadMenus unexpected result:', r)
        menus.value = []
        menusSnapshot = []
        isDirty.value = false
      }
    } catch (error) {
      console.error('[useMenuPermission] Failed to load menu permissions:', error)
      menus.value = []
      menusSnapshot = []
      isDirty.value = false
    } finally {
      loading.value = false
    }
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
    refreshIsDirty()  // [v43]
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
    refreshIsDirty()  // [v43]
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
          recalcBoGroupStatus(m, bg.bo_id)
        })
      }
    })
    refreshIsDirty()  // [v43]
  }

  async function save() {
    if (!permissionSetId.value) return
    // [GUARD 2026-06-14] 'new' 是创建态, 后端期望 int permission_set_id
    if (!/^\d+$/.test(String(permissionSetId.value))) {
      throw new Error('保存失败: 权限集尚未保存, 请先保存权限集')
    }

    saving.value = true
    try {
      // [v59 2026-08-27] 递归扁平化：menus.value 是树（后端返回嵌套 children），
      //   此前只遍历第一层 → 子菜单的 assigned / required_permissions 全部漏出 payload，
      //   表现为「勾选子菜单保存后刷新丢失」（顶层 6 项 vs 实际勾选 50 项）
      const flatMenus: Menu[] = []
      const walk = (list: Menu[]) => {
        for (const m of list || []) {
          flatMenus.push(m)
          if (m.children?.length) walk(m.children)
        }
      }
      walk(menus.value)

      const assignedCodes = flatMenus
        .filter(m => m.assigned)
        .map(m => m.menu_code)

      // [FIX v1.0.2 + BUG-V062] 收集所有需要落库的功能权限
      // source:
      //   'include' - 用户手动 include
      //   'exclude' - 用户手动 exclude
      //   'auto'    - 来自自动推导推荐 (applyDerived 已确认)
      //   'manual'  - 后端 GET 推得, 菜单未分配时
      //   ''        - 来自 bo_bindings 派生 (unbound), 不写入
      // 关键: 这里不能 filter `p.granted === true` !
      //   用户取消勾选 = source='exclude', granted=false,
      //   必须传给后端做 DELETE, 否则后端不知道要 ungrant
      //   之前版本有 `p.granted` 过滤, 导致取消勾选静默丢失
      // [BUG-V062] 之前 filter 排除了 'manual' 源, 导致后端 PFCG auto-sync
      //   把用户没传 = 没拒绝的权限也自动 sync 进 role_permissions,
      //   刷新后所有权限都显示 granted. 修复: 把 'manual' 也纳入 explicit set.
      //   这样用户没操作过的权限 = granted=false = 进入 explicit_denied,
      //   后端不会 auto-sync 它们进 role_permissions.
      const permissions = flatMenus
        .flatMap(m => m.required_permissions || [])
        .filter(p =>
          p.source === 'include' || p.source === 'exclude' ||
          p.source === 'auto'   || p.source === 'manual'
        )
        .map(p => ({ code: p.code, granted: !!p.granted }))

      const r = await permService.saveMenuPermissions(permissionSetId.value, { menu_codes: assignedCodes, permissions })

      if (!r.success) {
        throw new Error(r.message || '保存失败')
      }

      // [v43 2026-08-27] 保存成功 → 重新拍快照 → isDirty=false
      menusSnapshot = JSON.parse(JSON.stringify(menus.value))
      isDirty.value = false

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
    isDirty,             // [v43 2026-08-27] 是否有未保存变更
    loadMenus,
    selectAll,
    clearAll,
    applyDerived,
    save
  }
}

/**
 * [2026-08-28 重构清理] 从 required_permissions 重新推导某 BO 的动作分组状态。
 * 原 useMenuPermission 与 MenuPermissionMatrix 各维护一份逐行同构的实现，
 * 现收敛为此唯一实现（模块级导出，供 applyDerived 与 MenuPermissionMatrix 共用）。
 *
 * 分组来源优先级：exclude > include > auto（与 UI 徽章口径一致）。
 */
export function recalcBoGroupStatus(menu: Menu, boId: string) {
  const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
  if (!boGroup) return

  // 从 required_permissions 重新推导
  const boPerms = menu.required_permissions?.filter(p => p.code.startsWith(`${boId}:`)) || []

  Object.keys(GROUP_ACTIONS_MAP).forEach(gk => {
    const groupActions = GROUP_ACTIONS_MAP[gk as keyof typeof GROUP_ACTIONS_MAP]
    const matchingPerms = boPerms.filter(p => {
      const action = p.code.split(':')[1]
      return groupActions.includes(action as never)
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
