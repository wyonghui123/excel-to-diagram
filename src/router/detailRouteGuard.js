/**
 * 详情页路由守卫
 *
 * 验证：
 * 1. 对象类型是否有效
 * 2. ID 是否有效
 * 3. 用户是否有权限访问该对象
 */

import metaService from '@/services/metaService'

// [party 族 2026-10-21] 补齐身份轴五个类型。
//   起因（手机端报障「关系详情中业务伙伴/组织点击跳转失败」）：本白名单是硬编码的，
//   此前只列了平台早期对象，party 族全部缺席。而 party_relation 详情页的
//   业务伙伴(party2_id) / 我方组织(party1_id) / 归属法人(le_org_id) 三个字段都是
//   ObjectPageField 渲染出的 FK 链接，落点分别是 party_archive / party_internal /
//   org_legal_entity ⇒ 点击后 validateDetailRoute 判定类型不支持，
//   next({ path:'/', reason:'unsupported_object_type' }) 把用户弹回首页 = "跳转失败"。
//   口径说明: 这五个都是 party_relation 的 FK 落点或业务伙伴组，同属身份轴，
//   属受管业务对象，加进来不是放开任意类型，而是补齐本来就该可导航的类型。
const SUPPORTED_OBJECT_TYPES = [
  'user',
  'user_group',
  'org',
  'role',
  'permission',
  'permission_set',
  'permission_bundle',
  'enum_type',
  'enum_value',
  'domain',
  'sub_domain',
  'product',
  'version',
  'service_module',
  'business_object',
  'relationship',
  // 身份轴: 对外档案面 / 内部治理台账面 / 业务伙伴组 / 法人主体面
  //   刻意不含 party（身份锚基表）：F1 §7.1-4 定其「只作唯一写入路径，常规读取走两个
  //   只读面」，无 detail 配置；且全库无任何 FK 落点指向它（grep target_bo: party 仅命中
  //   party_relation 的 display_target_bo）。放进白名单只会开出一个必然白屏的详情页。
  'party_archive',
  'party_internal',
  'party_group',
  'org_legal_entity',
  // 物料轴 2026-10-23: 物料详情页的「物料组」(items.item_group_id) 与
  //   「基本单位」(items.base_uom) 都是 ObjectPageField 渲染的 FK 链接，落点分别是
  //   item_group / uom，此前同样不在白名单 ⇒ 点击后弹回首页
  //   (reason=unsupported_object_type)，用户报「物料组点击跳转失败」。
  //   item 自身也是落点（item_xref / item_uom_conversion / item_attribute_values 的
  //   target_bo: item）。三者都声明了 ui_view_config.detail，进去不会白屏。
  'item',
  'item_group',
  'uom',
  // 基础数据轴 2026-10-23: 把「全库 FK 落点 ⊆ 白名单」一次性补齐。
  //   取口径 = grep `target_bo:` / `detail_target_bo:`（display_target_bo 只管显示名
  //   解析、不产生跳转，见 models_value_help.py 三口径分工），与白名单求差集得到这五个：
  //     region     ← address 的省/市/区 FK
  //     location   ← item / address 的库位 FK
  //     calendar   ← item 的计划发货日 + party_relation 的日历 FK
  //     address    ← party_internal 的地址 FK
  //     party_relation ← 身份轴落点（本次一并纳入）
  //   前四个都是"地址/时间/仓储"这类基础数据，没有它们，地址详情与物料详情里的
  //   FK 会成片弹回首页。五个都声明了 ui_view_config.detail 且有物理表
  //   (regions / locations / calendars / addresses / party_relations)，
  //   read_bo 只做 login_required + dim scope、不校验按对象 read 权限 ⇒ 不会 403。
  'region',
  'location',
  'calendar',
  'address',
  'party_relation',
  // 销售轴 2026-10-25: 销售订单详情页承载订单行子表（含展开行操作），
  //   list.detail_mode = page 却未列入白名单 ⇒ 行点击 / 展开入口一律弹回首页。
  //   sales_order 自身声明了 ui_view_config.detail（child_sections 订单行），
  //   加进来不是放开任意类型，而是补齐 list 已声明 page 详情的对象。
  'sales_order'
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
    'user_group': '组织',
    'org': '组织',
    'role': '角色',
    'permission_set': '权限集',
    'permission_bundle': '权限包',
    'permission': '权限',
    'enum_type': '枚举类型',
    'enum_value': '枚举值',
    'domain': '领域',
    'sub_domain': '子领域',
    'product': '产品',
    'version': '版本',
    'service_module': '服务模块',
    'business_object': '业务对象',
    'relationship': '关联关系',
    // [party 族 2026-10-21] 补身份轴标签：缺了会让面包屑回退显示英文 objectType id
    'party': '身份主体',
    'party_archive': '业务伙伴',
    'party_internal': '内部治理台账',
    'party_group': '业务伙伴组',
    'org_legal_entity': '法人主体',
    // [物料轴 2026-10-23] 与 SUPPORTED_OBJECT_TYPES 同步补齐，缺了面包屑会回退显示英文 id
    'item': '物料',
    'item_group': '物料组',
    'uom': '计量单位',
    // [基础数据轴 2026-10-23] 同上，与白名单一一对应
    'region': '行政区域',
    'location': '库位',
    'calendar': '日历',
    'address': '地址',
    'party_relation': '业务伙伴关系'
  }

  const label = typeLabels[normalizedType] || objectType

  const breadcrumbs = [
    {
      path: '/',
      title: '首页'
    }
  ]

  if (normalizedType === 'org') {
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户与权限管理'
    })
    breadcrumbs.push({
      path: '/user-permission',
      title: '组织管理'
    })
  } else if (normalizedType === 'permission_set' || normalizedType === 'permission_bundle') {
    breadcrumbs.push({
      path: '/user-permission',
      title: '用户与权限管理'
    })
    breadcrumbs.push({
      path: '/user-permission',
      title: '权限集管理'
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
