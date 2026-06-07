/**
 * useNavigation - 导航 Composable
 *
 * 提供：
 * - 详情页导航
 * - 面包屑导航
 * - 关联对象导航
 */

import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

export function useNavigation(options = {}) {
  const router = useRouter()
  const route = useRoute()

  const breadcrumbs = ref([])
  const navigationHistory = ref([])

  function navigateToDetail(objectType, id, params = {}) {
    const query = {}

    if (params.readonly) query.readonly = 'true'
    if (params.showDelete === false) query.showDelete = 'false'
    if (params.showHistory === false) query.showHistory = 'false'

    const path = `/detail/${objectType}/${id}`

    addToHistory({
      path: route.fullPath,
      name: route.name,
      title: document.title
    })

    router.push({ path, query })
  }

  function navigateToUserGroup(id) {
    navigateToDetail('user_group', id)
  }

  function navigateToRole(id) {
    navigateToDetail('role', id)
  }

  function navigateToUser(id) {
    navigateToDetail('user', id)
  }

  function navigateToEnumType(id) {
    navigateToDetail('enum_type', id)
  }

  function navigateToEnumValue(id) {
    navigateToDetail('enum_value', id)
  }

  function addToHistory(entry) {
    navigationHistory.value.push({
      ...entry,
      timestamp: Date.now()
    })

    if (navigationHistory.value.length > 50) {
      navigationHistory.value.shift()
    }
  }

  function goBack() {
    if (navigationHistory.value.length > 0) {
      const lastEntry = navigationHistory.value.pop()
      router.push(lastEntry.path)
    } else {
      router.back()
    }
  }

  function setBreadcrumbs(items) {
    breadcrumbs.value = items
  }

  function buildBreadcrumbsForObject(objectType, objectName = null) {
    const typeLabels = {
      'user': '用户',
      'user_group': '用户组',
      'role': '角色',
      'permission': '权限',
      'enum_type': '枚举类型',
      'enum_value': '枚举值',
      'domain': '领域',
      'sub_domain': '子领域',
      'product': '产品',
      'version': '版本',
      'service_module': '服务模块'
    }

    const label = typeLabels[objectType] || objectType

    const crumbs = [
      { path: '/', title: '首页' }
    ]

    if (objectType === 'user_group') {
      crumbs.push({ path: '/user-permission', title: '用户与权限管理' })
      crumbs.push({ path: '/user-permission', title: '用户组管理' })
    } else if (objectType === 'role') {
      crumbs.push({ path: '/user-permission', title: '用户与权限管理' })
      crumbs.push({ path: '/user-permission', title: '角色管理' })
    } else if (objectType === 'user') {
      crumbs.push({ path: '/user-permission', title: '用户与权限管理' })
      crumbs.push({ path: '/user-permission', title: '用户管理' })
    } else if (objectType === 'enum_type' || objectType === 'enum_value') {
      crumbs.push({ path: '/business-config', title: '业务配置' })
      crumbs.push({ path: '/business-config/enums', title: '枚举管理' })
    }

    crumbs.push({
      path: `/detail/${objectType}/${route.params.id}`,
      title: objectName || `${label}详情`,
      active: true
    })

    setBreadcrumbs(crumbs)
    return crumbs
  }

  const canGoBack = computed(() => navigationHistory.value.length > 0)

  return {
    breadcrumbs,
    navigationHistory,
    canGoBack,
    navigateToDetail,
    navigateToUserGroup,
    navigateToRole,
    navigateToUser,
    navigateToEnumType,
    navigateToEnumValue,
    goBack,
    setBreadcrumbs,
    buildBreadcrumbsForObject
  }
}

export default useNavigation
