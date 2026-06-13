/**
 * 共享类型定义 - W4 PR-4.3
 *
 * 用途：
 * 1. 为现有 .js 文件提供 JSDoc 类型提示（通过 TypeScript 编译时检查）
 * 2. 为未来 .ts 迁移提供基础类型
 * 3. 避免在多文件中重复定义相同的 interface
 *
 * 使用方式：
 *   // .js 文件中（JSDoc）
 *   /** @type {import('@/types/common').BusinessObject} *​/
 *   const bo = ...
 *
 *   // .ts 文件中（import）
 *   import type { BusinessObject } from '@/types/common'
 *
 * 命名约定：
 *   - 业务对象类型：BusinessObject, SubDomain, ServiceModule, Domain, Relationship
 *   - 配置类型：ChartConfig, LayoutConfig, ColorConfig
 *   - 通用类型：ID, Code, ISODateString
 */

// ========== 基础类型 ==========
export type ID = number | string
export type Code = string
export type ISODateString = string
export type Nullable<T> = T | null
export type Optional<T> = T | undefined

// ========== 业务对象类型 ==========
export interface BaseObject {
  id: ID
  code: Code
  name: string
  description?: string
  version_id?: ID
  created_at?: ISODateString
  updated_at?: ISODateString
}

export interface Domain extends BaseObject {
  type: 'domain'
}

export interface SubDomain extends BaseObject {
  type: 'sub_domain'
  domain_id: ID
}

export interface ServiceModule extends BaseObject {
  type: 'service_module'
  sub_domain_id: ID
  domain_id: ID
}

export interface BusinessObject extends BaseObject {
  type: 'business_object'
  service_module_id: ID
  sub_domain_id: ID
  domain_id: ID
}

export interface Relationship extends BaseObject {
  type: 'relationship'
  source_code: Code
  target_code: Code
  source_bo_id?: ID
  target_bo_id?: ID
  relation_type: string
  scope_type?: 'internal' | 'cross-boundary' | 'external'
  category_type?: 'same-module' | 'same-subdomain-cross-module' | 'same-domain-cross-subdomain' | 'cross-domain'
}

export type AnyBusinessObject = Domain | SubDomain | ServiceModule | BusinessObject

// ========== 图表配置类型 ==========
export interface ChartConfig {
  chartType: 'businessObject' | 'serviceModule' | 'subDomain' | 'domain'
  layoutEngine: 'elk' | 'dagre'
  layoutType: 'grouped' | 'flat' | 'hierarchical'
  colorScheme: 'default' | 'blue' | 'green' | 'red' | 'custom'
  showLegend: boolean
}

export interface LayoutConfig {
  enabled: boolean
  overallDirection: 'LR' | 'RL' | 'TB' | 'BT'
  groups: Array<{
    id: string
    name: string
    nodeIds: ID[]
  }>
  engine: 'elk' | 'dagre'
  preserveOrder: boolean
}

export interface ColorConfig {
  scheme: string
  groupBy: 'domain' | 'sub_domain' | 'service_module' | 'business_object'
  customColors: Record<Code, string>
  centerScopeColor: string
  centerDomainColor: string
  nodeTextColor: string
}

// ========== 分页/查询类型 ==========
export interface PaginationParams {
  page: number
  page_size: number
  filters?: Record<string, unknown>
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  total: number
  page: number
  page_size: number
}

// ========== API 响应类型 ==========
export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  message?: string
  error_code?: string
  trace_id?: string
}

// ========== 审计日志类型 ==========
export interface AuditLogEntry {
  object_type: string
  object_id: ID
  action: 'CREATE' | 'UPDATE' | 'DELETE' | 'READ'
  field_name?: string
  old_value?: unknown
  new_value?: unknown
  user_id?: ID
  user_name?: string
  ip_address?: string
  user_agent?: string
  created_at: ISODateString
  extra_data?: string  // JSON stringified
  trace_id?: string
  transaction_id?: string
  status?: 'pending' | 'written' | 'failed'
}

// ========== 用户权限类型 ==========
export interface UserContext {
  user_id: ID
  user_name: string
  ip_address: string
  user_agent: string
}

// ========== 选中数量配置类型 (FR-008 v2) ==========
export interface SelectionConfig {
  max_count: number
  warning_threshold: number  // 0-1
  allow_override: boolean
}

export interface SelectionSource {
  source: 'url' | 'user' | 'page' | 'bo' | 'system' | 'default'
  source_label_zh: string
}
