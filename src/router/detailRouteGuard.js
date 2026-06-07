/**
 * 详情页路由守卫
 *
 * 验证：
 * 1. 对象类型是否有效
 * 2. ID 是否有效
 * 3. 用户是否有权限访问该对象
 */

import metaService from '@/services/metaService'

const SUPPORTED_OBJECT_TYPES = [
  'user',
  'user_group',
  'role',
  'permission',
  'enum_type',
  'enum_value',
  'domain',
  'sub_domain',
  'product',
  'version',
  'service_module',
  'business_object',
  'relationship'
]

export async function validateDetailRoute(to, from, next) {
  const { objectType, id } = to.params

  if (!objectType) {
    next({ path: '/', query: { reason: 'invalid_object_type' } })
    return false
  }

  const normalizedType = objectType.toLowerCase()
  if (!SUPPORTED_OBJECT_TYPES.includes(normalizedType)) {
    next({
      path: '/',
      query: { reason: 'unsupported_object_type', type: objectType }
    })
    return false
  }

  if (id) {
    const validId = id && String(id).trim().length > 0
    if (!validId) {
      next({
        path: '/',
        query: { reason: 'invalid_id_format', id: id }
      })
      return false
    }
  }

  return true
}

export function getBreadcrumbs(objectType, id, objectName = null) {
  const normalizedType = objectType.toLowerCase()

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
    'service_module': '服务模块',
    'business_object': '业务对象',
    'relationship': '关联关系'
  }

  const label = typeLabels[normalizedType] || objectType

  const breadcrumbs = [
    {
      path: '/',
      title: '首页'
    }
  ]

  if (normalizedType === 'user_group') {
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户与权限管理'
    })
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户组管理'
    })
  } else if (normalizedType === 'role') {
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户与权限管理'
    })
    breadcrumbs.push({
      path: '/user-permission',
      title: '角色管理'
    })
  } else if (normalizedType === 'user') {
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户与权限管理'
    })
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户管理'
    })
  } else if (normalizedType === 'enum_type' || normalizedType === 'enum_value') {
    breadcrumbs.push({
      path: '/business-config',
      title: '业务配置'
    })
    breadcrumbs.push({
      path: '/business-config/enums',
      title: '枚举管理'
    })
  }

  breadcrumbs.push({
    path: `/detail/${objectType}/${id}`,
    title: objectName || `${label}详情`,
    active: true
  })

  return breadcrumbs
}

export default {
  validateDetailRoute,
  getBreadcrumbs
}
