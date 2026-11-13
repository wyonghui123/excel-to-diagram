/**
 * uiMeta.ts - UI 元数据契约类型（唯一类型真源）
 *
 * 来源：docs/specs/spec-ui-logic-sinkdown-plan-2026-11-13.md §13.3
 * 红线：字段名与后端 JSON 逐字一致（snake_case），前端不做驼峰转换。
 */

export type EnumColor = 'success' | 'warning' | 'danger' | 'info' | 'primary'

export interface EnumItem {
  value: string | number | boolean
  label: string
  color?: EnumColor
  category?: string
}

export interface UiColumnMeta {
  field: string
  label: string
  width?: number
  sortable?: boolean
  filterable?: boolean
  tag_enum?: string
}

export interface UiFieldMeta {
  key: string
  label: string
  widget: string
  required?: boolean
  readonly?: boolean
  visible?: boolean
  visible_when?: string
  col_span?: 1 | 2 | 3 | 4
  enum_type?: string
  value_help?: unknown
  depends_on?: string[]
}

export interface UiSectionMeta {
  key: string
  label: string
  columns?: 1 | 2
  fields: string[]
  col_span_map?: Record<string, 1 | 2 | 3 | 4>
}

export interface UiTabMeta {
  key: string
  label: string
  section_keys: string[]
}

export interface UiActionMeta {
  id: string
  label: string
  icon?: string
  style?: EnumColor
  position?: 'toolbar' | 'row' | 'batch'
  confirm?: string
  enabled?: boolean
  reason?: string
  required_permission?: string
}

export interface UiMeta {
  schema_version: string
  object_type: string
  label: string
  partial?: boolean
  list: {
    columns: UiColumnMeta[]
    default_sort?: string
    page_size?: number
    actions: UiActionMeta[]
  }
  detail: { sections: UiSectionMeta[]; tabs?: UiTabMeta[] }
  form: {
    sections: UiSectionMeta[]
    tabs?: UiTabMeta[]
    fields: UiFieldMeta[]
    layout?: 'vertical' | 'horizontal'
  }
  filters: unknown[]
  field_policies: Record<string, { editable?: boolean; visible?: boolean; readonly?: boolean }>
  actions: UiActionMeta[]
}

export type ActionEvaluateResult = Record<
  string,
  Record<string, { enabled: boolean; reason?: string; required_permission?: string; style?: EnumColor }>
>