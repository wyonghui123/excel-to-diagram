import { describe, it, expect } from 'vitest'
import {
  sortColumnsByDefaultOrder,
  classifyField,
  COLUMN_BUCKETS,
} from '@/services/columnOrderService'

// 工具: 提取排序后列的 key 序列
const keysOf = (cols) => cols.map(c => c.prop || c.key || c.field || c.id)

describe('columnOrderService', () => {
  // ===== 入口边界 =====
  describe('sortColumnsByDefaultOrder - 边界', () => {
    it('空数组 → 空数组', () => {
      expect(sortColumnsByDefaultOrder([])).toEqual([])
    })

    it('非数组输入 → 空数组(防御性)', () => {
      expect(sortColumnsByDefaultOrder(null)).toEqual([])
      expect(sortColumnsByDefaultOrder(undefined)).toEqual([])
      expect(sortColumnsByDefaultOrder('not-array')).toEqual([])
    })

    it('不修改原数组(纯函数)', () => {
      const original = [
        { prop: 'updated_at' },
        { prop: 'code' },
        { prop: 'name' },
      ]
      const snapshot = JSON.parse(JSON.stringify(original))
      sortColumnsByDefaultOrder(original, [], { strategy: 'smart_default' })
      expect(original).toEqual(snapshot)
    })

    it('默认策略是 smart_default', () => {
      // 不传 strategy → 按 smart_default 规则
      const cols = [{ prop: 'updated_at' }, { prop: 'code' }]
      const sorted = sortColumnsByDefaultOrder(cols, [], {})
      expect(keysOf(sorted)).toEqual(['code', 'updated_at'])
    })
  })

  // ===== classifyField 单字段分类 =====
  describe('classifyField - 6 桶分类', () => {
    const fieldMap = new Map()

    it('businessKey: true → business_key 桶', () => {
      const col = { prop: 'code', businessKey: true }
      expect(classifyField(col, fieldMap)).toBe('business_key')
    })

    it('business_key: true → business_key 桶', () => {
      const col = { prop: 'customer_code', business_key: true }
      expect(classifyField(col, fieldMap)).toBe('business_key')
    })

    it('field.semantics === "business_key" → business_key 桶', () => {
      const col = { prop: 'id' }
      const fields = [{ name: 'id', semantics: 'business_key' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('business_key')
    })

    it('field.semantics === "display_name" → primary 桶', () => {
      const col = { prop: 'title' }
      const fields = [{ name: 'title', semantics: 'display_name' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('primary')
    })

    it('字段名 "name" / "display_name" → primary 桶', () => {
      expect(classifyField({ prop: 'name' }, fieldMap)).toBe('primary')
      expect(classifyField({ prop: 'display_name' }, fieldMap)).toBe('primary')
    })

    it('status/state/type/category → status 桶', () => {
      expect(classifyField({ prop: 'status' }, fieldMap)).toBe('status')
      expect(classifyField({ prop: 'state' }, fieldMap)).toBe('status')
      expect(classifyField({ prop: 'type' }, fieldMap)).toBe('status')
      expect(classifyField({ prop: 'category' }, fieldMap)).toBe('status')
      expect(classifyField({ prop: 'is_active' }, fieldMap)).toBe('status')
    })

    it('field.semantics === "status" → status 桶', () => {
      const col = { prop: 'workflow' }
      const fields = [{ name: 'workflow', semantics: 'status' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('status')
    })

    it('系统字段(created_at/updated_at/id/uuid/...) → system 桶', () => {
      for (const key of ['id', 'uuid', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at', 'is_deleted']) {
        expect(classifyField({ prop: key }, fieldMap)).toBe('system')
      }
    })

    it('hierarchy.parent_id 指向自己 → parent_ref 桶', () => {
      const col = { prop: 'parent_id' }
      const fields = [{ name: 'parent_id', id: 'parent_id', hierarchy: { parent_id: 'parent_id', level: 1 } }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('parent_ref')
    })

    it('field.semantics === "parent_key" → parent_ref 桶', () => {
      const col = { prop: 'org_id' }
      const fields = [{ name: 'org_id', semantics: 'parent_key' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('parent_ref')
    })

    it('字段名 _id + foreign_key=true → parent_ref 桶', () => {
      const col = { prop: 'category_id' }
      const fields = [{ name: 'category_id', foreign_key: true }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('parent_ref')
    })

    it('字段名 _id 但无 foreign_key → business 桶(不误判)', () => {
      const col = { prop: 'category_id' }
      // field 没标 foreign_key
      expect(classifyField(col, fieldMap)).toBe('business')
    })

    it('未识别的业务字段 → business 桶(默认)', () => {
      expect(classifyField({ prop: 'price' }, fieldMap)).toBe('business')
      expect(classifyField({ prop: 'description' }, fieldMap)).toBe('business')
    })

    it('override.business_keys 优先于所有推断', () => {
      // status 字段名,但 override 强制划入 business_key
      const col = { prop: 'status' }
      const result = classifyField(col, fieldMap, { business_keys: ['status'] })
      expect(result).toBe('business_key')
    })

    it('override.primary_fields 覆盖 name 推断', () => {
      const col = { prop: 'description' }
      const result = classifyField(col, fieldMap, { primary_fields: ['description'] })
      expect(result).toBe('primary')
    })

    it('override.parent_ref_fields 强制划入 parent_ref', () => {
      const col = { prop: 'random_field' }
      const result = classifyField(col, fieldMap, { parent_ref_fields: ['random_field'] })
      expect(result).toBe('parent_ref')
    })

    it('override.system_fields 强制划入 system (可覆盖 businessKey 标注)', () => {
      // name 字段有 businessKey 标注,但 override.system_fields 强制进 system 桶
      const col = { prop: 'name', businessKey: true }
      const result = classifyField(col, fieldMap, { system_fields: ['name'] })
      expect(result).toBe('system')
    })

    it('field.semantics === "businessId" → business_key 桶', () => {
      const col = { prop: 'biz_id' }
      const fields = [{ name: 'biz_id', semantics: 'businessId' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('business_key')
    })

    it('field.semantics === "displayName" → primary 桶 (大写 D)', () => {
      const col = { prop: 'title' }
      const fields = [{ name: 'title', semantics: 'displayName' }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('primary')
    })

    it('field.semantics === "parent_id" / "parent" → parent_ref 桶', () => {
      const map1 = new Map([['pid', { name: 'pid', semantics: 'parent_id' }]])
      const map2 = new Map([['pid', { name: 'pid', semantics: 'parent' }]])
      expect(classifyField({ prop: 'pid' }, map1)).toBe('parent_ref')
      expect(classifyField({ prop: 'pid' }, map2)).toBe('parent_ref')
    })

    it('field.semantics === "state" / "category" → status 桶', () => {
      const map1 = new Map([['workflow', { name: 'workflow', semantics: 'state' }]])
      const map2 = new Map([['type', { name: 'type', semantics: 'category' }]])
      expect(classifyField({ prop: 'workflow' }, map1)).toBe('status')
      expect(classifyField({ prop: 'type' }, map2)).toBe('status')
    })

    it('field.foreignKey === true (大写 K) → parent_ref 桶', () => {
      const col = { prop: 'region_id' }
      const fields = [{ name: 'region_id', foreignKey: true }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('parent_ref')
    })

    it('field.isForeignKey === true → parent_ref 桶', () => {
      const col = { prop: 'zone_id' }
      const fields = [{ name: 'zone_id', isForeignKey: true }]
      const map = new Map(fields.map(f => [f.name, f]))
      expect(classifyField(col, map)).toBe('parent_ref')
    })

    it('col.label === "name" 但 prop 不是 name → primary 桶', () => {
      // prop 是 'fullname' 但 label 是 'name',按 label 归入 primary
      const col = { prop: 'fullname', label: 'name' }
      expect(classifyField(col, fieldMap)).toBe('primary')
    })

    it('override 优先级: business_keys > primary_fields > status_fields > parent_ref_fields > system_fields > 自动推断', () => {
      // name 既是 primary 字段名,又进 status_fields override
      // 代码里 primary_fields 在 status_fields 之前,所以 primary_fields 先匹配,返回 'primary'
      const col = { prop: 'name' }
      const result = classifyField(col, fieldMap, {
        status_fields: ['name'],
        primary_fields: ['name'],
      })
      expect(result).toBe('primary')
    })
  })

  // ===== smart_default 排序 =====
  describe('smartDefault 策略 - 6 桶排序', () => {
    it('基本 6 桶顺序: code(业务键) → name(主标识) → status → category_id(父级) → price(业务) → created_at(系统)', () => {
      const cols = [
        { prop: 'created_at' },
        { prop: 'price' },
        { prop: 'category_id', foreign_key: true },
        { prop: 'status' },
        { prop: 'name' },
        { prop: 'code', businessKey: true },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual([
        'code', 'name', 'status', 'category_id', 'price', 'created_at',
      ])
    })

    it('桶内按 hierarchy.level 升序(根节点在前)', () => {
      const cols = [
        { prop: 'grandchild_id' },   // level 2
        { prop: 'child_id' },         // level 1
        { prop: 'root_id' },          // level 0
      ]
      const fields = [
        { name: 'root_id',      foreign_key: true, hierarchy: { level: 0 } },
        { name: 'child_id',     foreign_key: true, hierarchy: { level: 1 } },
        { name: 'grandchild_id', foreign_key: true, hierarchy: { level: 2 } },
      ]
      const fieldMap = new Map(fields.map(f => [f.name, f]))
      const sorted = sortColumnsByDefaultOrder(cols, fields, { strategy: 'smart_default' })
      // 都进 parent_ref 桶,按 level 升序: root → child → grandchild
      expect(keysOf(sorted)).toEqual(['root_id', 'child_id', 'grandchild_id'])
    })

    it('同 level 桶内按字段名字母序', () => {
      const cols = [
        { prop: 'z_field' },
        { prop: 'a_field' },
        { prop: 'm_field' },
      ]
      const fields = [
        { name: 'a_field', foreign_key: true, hierarchy: { level: 0 } },
        { name: 'm_field', foreign_key: true, hierarchy: { level: 0 } },
        { name: 'z_field', foreign_key: true, hierarchy: { level: 0 } },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, fields, { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['a_field', 'm_field', 'z_field'])
    })

    it('有 position 的列保持原位,无 position 的列进 6 桶追加到尾部', () => {
      // 模拟 relationship.yaml: code(p1) → relation_desc(p2) → name → status → created_at(p90)
      const cols = [
        { prop: 'created_at', position: 90 },
        { prop: 'name' },
        { prop: 'status' },
        { prop: 'code', position: 1, businessKey: true },
        { prop: 'relation_desc', position: 2 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      // 有 position 升序(在前): code(1) → relation_desc(2) → created_at(90)
      // 无 position 智能桶(在后): name(primary) → status(status)
      expect(keysOf(sorted)).toEqual([
        'code', 'relation_desc', 'created_at', 'name', 'status',
      ])
    })

    it('override.status_fields 强制 status 桶优先级', () => {
      const cols = [
        { prop: 'name' },
        { prop: 'state' },
      ]
      // 把 'name' 强制划入 status 桶
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'smart_default',
        override: { status_fields: ['name'] },
      })
      // 现在 'name' 进了 status 桶,'state' 也进 status 桶,按字母序
      expect(keysOf(sorted)).toEqual(['name', 'state'])
    })

    it('position: 0 视为有效 position', () => {
      // position: 0 是有效数字,应排在最前
      const cols = [
        { prop: 'a' },
        { prop: 'b', position: 0 },
        { prop: 'c', position: 1 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['b', 'c', 'a'])
    })

    it('override 多桶组合: 同时强制多个不同桶的字段', () => {
      const cols = [
        { prop: 'status' },                    // 推断进 status 桶
        { prop: 'desc' },                      // 推断进 business 桶
        { prop: 'code', businessKey: true },   // 推断进 business_key 桶
        { prop: 'updated_at' },                 // 推断进 system 桶
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'smart_default',
        override: {
          status_fields: ['desc'],   // desc 强制进 status 桶
          system_fields: ['code'],   // code 强制进 system 桶(覆盖 businessKey)
        },
      })
      // 显式 position 无,全部进智能桶
      // status(status+override): desc, status
      // business_key(无override): code → 但 code 被 override.system_fields 强制进 system
      // system(override): code
      // business(无override): 无
      expect(keysOf(sorted)).toEqual(['desc', 'status', 'code', 'updated_at'])
    })

    it('全部列都有 position 时智能桶不参与排序', () => {
      // 无 position 列不存在,智能桶为空,输出严格按 position 升序
      const cols = [
        { prop: 'z', position: 3 },
        { prop: 'a', position: 1 },
        { prop: 'm', position: 2 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['a', 'm', 'z'])
    })

    it('空 fields 数组时,按字段名推断(不崩)', () => {
      const cols = [
        { prop: 'created_at' },
        { prop: 'name' },
        { prop: 'code', businessKey: true },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['code', 'name', 'created_at'])
    })

    it('支持 prop/key/field/id 多种 key 命名', () => {
      const cols = [
        { key: 'created_at' },
        { field: 'name' },
        { id: 'code', businessKey: true },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['code', 'name', 'created_at'])
    })
  })

  // ===== yaml_position 策略 =====
  describe('yaml_position 策略 - 严格按 position 升序', () => {
    it('基本排序', () => {
      const cols = [
        { prop: 'updated_at', position: 91 },
        { prop: 'code', position: 1 },
        { prop: 'name', position: 2 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      expect(keysOf(sorted)).toEqual(['code', 'name', 'updated_at'])
    })

    it('无 position 的列追加到尾部(不丢列)', () => {
      const cols = [
        { prop: 'orphan' },
        { prop: 'code', position: 1 },
        { prop: 'name' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      expect(keysOf(sorted)).toEqual(['code', 'orphan', 'name'])
    })

    it('全部无 position 时保持原顺序', () => {
      const cols = [
        { prop: 'a' },
        { prop: 'b' },
        { prop: 'c' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      expect(keysOf(sorted)).toEqual(['a', 'b', 'c'])
    })

    it('position: 0 视为有效 position(排在最前)', () => {
      const cols = [
        { prop: 'c', position: 1 },
        { prop: 'a', position: 0 },
        { prop: 'b' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      expect(keysOf(sorted)).toEqual(['a', 'c', 'b'])
    })

    it('position 为 null/undefined/空字符串时不识别为有效 position', () => {
      const cols = [
        { prop: 'c', position: 1 },
        { prop: 'a', position: null },
        { prop: 'b', position: undefined },
        { prop: 'd', position: '' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      // c(1) 显式,在前; a/b/d 无有效 position,保持原相对顺序在尾部
      expect(keysOf(sorted)).toEqual(['c', 'a', 'b', 'd'])
    })

    it('重复 position 值保持原相对顺序(稳定排序)', () => {
      // 两个列 position 都是 1,按原数组顺序输出
      const cols = [
        { prop: 'b', position: 2 },
        { prop: 'a', position: 1 },
        { prop: 'c', position: 1 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      // position 1 的列有两个: a 在前,c 在后(稳定)
      expect(keysOf(sorted)).toEqual(['a', 'c', 'b'])
    })
  })

  // ===== manual 策略 =====
  describe('manual 策略 - 按 manual_order 顺序', () => {
    it('按 manual_order 指定的顺序排列', () => {
      const cols = [
        { prop: 'updated_at' },
        { prop: 'code' },
        { prop: 'name' },
        { prop: 'created_at' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'manual',
        manual_order: ['name', 'code', 'created_at', 'updated_at'],
      })
      expect(keysOf(sorted)).toEqual(['name', 'code', 'created_at', 'updated_at'])
    })

    it('manual_order 中未列出的列追加到尾部', () => {
      const cols = [
        { prop: 'orphan' },
        { prop: 'name' },
        { prop: 'code' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'manual',
        manual_order: ['code', 'name'],
      })
      expect(keysOf(sorted)).toEqual(['code', 'name', 'orphan'])
    })

    it('manual_order 为空 → 保持原顺序', () => {
      const cols = [
        { prop: 'a' },
        { prop: 'b' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'manual', manual_order: [] })
      expect(keysOf(sorted)).toEqual(['a', 'b'])
    })

    it('支持 key 字段名匹配', () => {
      const cols = [
        { key: 'name' },
        { key: 'code' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'manual',
        manual_order: ['code', 'name'],
      })
      expect(keysOf(sorted)).toEqual(['code', 'name'])
    })
  })

  // ===== COLUMN_BUCKETS 导出 =====
  describe('COLUMN_BUCKETS 常量', () => {
    it('权重严格升序: business_key(10) < primary(20) < status(30) < parent_ref(40) < business(50) < system(90)', () => {
      const weights = [
        COLUMN_BUCKETS.BUSINESS_KEY.weight,
        COLUMN_BUCKETS.PRIMARY.weight,
        COLUMN_BUCKETS.STATUS.weight,
        COLUMN_BUCKETS.PARENT_REF.weight,
        COLUMN_BUCKETS.BUSINESS.weight,
        COLUMN_BUCKETS.SYSTEM.weight,
      ]
      const sorted = [...weights].sort((a, b) => a - b)
      expect(weights).toEqual(sorted)
    })

    it('6 个桶 id 全部唯一', () => {
      const ids = Object.values(COLUMN_BUCKETS).map(b => b.id)
      expect(new Set(ids).size).toBe(6)
    })
  })

  // ===== 实际场景模拟 =====
  describe('实际场景模拟', () => {
    it('关系对象 (relationship.yaml 已部署列序)', () => {
      // code(p1) → source_bo_name(p2) → target_bo_name(p3) → relation_desc(p4) → relation_type(p5)
      //   → source_code(p6) → target_code(p7) → relation_direction(p8) → category_label(p9)
      //   → created_at(p90) → updated_at(p91)
      const cols = [
        { prop: 'updated_at', position: 91 },
        { prop: 'created_at', position: 90 },
        { prop: 'category_label', position: 9 },
        { prop: 'target_bo_name', position: 3 },
        { prop: 'source_bo_name', position: 2 },
        { prop: 'relation_direction', position: 8 },
        { prop: 'target_code', position: 7 },
        { prop: 'source_code', position: 6 },
        { prop: 'relation_type', position: 5 },
        { prop: 'relation_desc', position: 4 },
        { prop: 'code', position: 1, businessKey: true },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual([
        'code', 'source_bo_name', 'target_bo_name', 'relation_desc', 'relation_type',
        'source_code', 'target_code', 'relation_direction', 'category_label',
        'created_at', 'updated_at',
      ])
    })

    it('业务对象 (无 position, 走 smart_default 智能桶)', () => {
      const cols = [
        { prop: 'description' },                    // business
        { prop: 'created_at' },                     // system
        { prop: 'category_id', foreign_key: true }, // parent_ref
        { prop: 'name' },                           // primary
        { prop: 'code', businessKey: true },        // business_key
        { prop: 'status' },                         // status
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual([
        'code', 'name', 'status', 'category_id', 'description', 'created_at',
      ])
    })

    it('业务对象 + 补充字段(部分有 position, 部分无)', () => {
      // code(p1)/name/price/status/created_at(p90)
      const cols = [
        { prop: 'name' },
        { prop: 'price' },
        { prop: 'status' },
        { prop: 'code', position: 1, businessKey: true },
        { prop: 'created_at', position: 90 },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      // 显式 position 列(在前,按 position 升序): code(1) → created_at(90)
      // 无 position 列(在后,按 6 桶): name(pri) → status(sta) → price(bus)
      expect(keysOf(sorted)).toEqual([
        'code', 'created_at', 'name', 'status', 'price',
      ])
    })
  })

  // ===== 健壮性 =====
  describe('健壮性', () => {
    it('fields 中包含空对象不崩', () => {
      const cols = [{ prop: 'code' }, { prop: 'name' }]
      const fields = [null, undefined, {}, { name: 'name' }]
      expect(() => sortColumnsByDefaultOrder(cols, fields, { strategy: 'smart_default' })).not.toThrow()
    })

    it('col.position 是字符串时不识别为有效 position', () => {
      // "1" (string) 不算 position,进 6 桶
      const cols = [
        { prop: 'code', position: '1', businessKey: true },
        { prop: 'name' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      // code 进 business_key,name 进 primary
      expect(keysOf(sorted)).toEqual(['code', 'name'])
    })

    it('override 中包含非数组值不崩', () => {
      const cols = [{ prop: 'code' }, { prop: 'name' }]
      expect(() => sortColumnsByDefaultOrder(cols, [], {
        strategy: 'smart_default',
        override: { business_keys: 'not-array' },
      })).not.toThrow()
    })

    it('fields 为 undefined 等同于空数组(不崩)', () => {
      const cols = [
        { prop: 'code', businessKey: true },
        { prop: 'name' },
      ]
      expect(() => sortColumnsByDefaultOrder(cols, undefined, { strategy: 'smart_default' })).not.toThrow()
      const sorted = sortColumnsByDefaultOrder(cols, undefined, { strategy: 'smart_default' })
      expect(keysOf(sorted)).toEqual(['code', 'name'])
    })

    it('空字符串 key 不崩溃,归入 business 桶', () => {
      const cols = [
        { prop: 'name' },
        { prop: '' },
        { prop: 'code', businessKey: true },
      ]
      expect(() => sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })).not.toThrow()
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      // 空字符串 keyOf('') 返回 '',归 business 桶;keysOf 把空字符串 prop 转为 undefined
      expect(keysOf(sorted)).toEqual(['code', 'name', undefined])
    })

    it('列同时有 prop 和 key,优先用 prop', () => {
      const cols = [
        { key: 'z', prop: 'a' },  // prop 和 key 不同,keyOf 用 prop
        { key: 'b', prop: 'b' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'smart_default' })
      // 都进 business 桶,按字母序: a(a) < b(b)
      expect(keysOf(sorted)).toEqual(['a', 'b'])
    })

    it('NaN/Infinity position 不识别为有效 position', () => {
      const cols = [
        { prop: 'c', position: 1 },
        { prop: 'a', position: NaN },
        { prop: 'b', position: Infinity },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'yaml_position' })
      // NaN/Infinity 不是有限数,不识别为有效 position
      expect(keysOf(sorted)).toEqual(['c', 'a', 'b'])
    })

    it('strategy 为未知值时 fallback 到 smart_default', () => {
      const cols = [
        { prop: 'created_at' },
        { prop: 'code', businessKey: true },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], { strategy: 'unknown_strategy' })
      expect(keysOf(sorted)).toEqual(['code', 'created_at'])
    })

    it('manual_order 中出现重复 key 只取第一个(Map 自动去重)', () => {
      const cols = [
        { prop: 'a' },
        { prop: 'b' },
        { prop: 'c' },
      ]
      const sorted = sortColumnsByDefaultOrder(cols, [], {
        strategy: 'manual',
        manual_order: ['b', 'a', 'b', 'c'],
      })
      // 遍历保留第一个出现: ['b','a','b','c'] → {b:0, a:1, c:3}
      // a,c 不在 manual_order 里,保持原相对顺序追加在末尾
      expect(keysOf(sorted)).toEqual(['b', 'a', 'c'])
    })
  })
})
