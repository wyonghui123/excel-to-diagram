# ObjectPage Component Context

> **目标文件**: `src/components/common/ObjectPage/ObjectPage.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

对象详情页。展示一个对象的完整信息:头部信息、字段分组、关联项、子对象、变更历史。

**架构位置**: 核心页面组件,被几乎所有业务模块使用

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectType` | String | `''` | 对象类型 code |
| `objectId` | String | `''` | 对象 ID |
| `mode` | String | `'view'` | view / edit / create |
| `readonly` | Boolean | `false` | 只读 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `save` | `{data}` | 保存 |
| `delete` | - | 删除 |
| `change` | `{data}` | 数据变化 |

### Slot
| Name | Description |
|------|-------------|
| `header-extra` | 头部额外按钮 |
| `field-<key>` | 自定义字段 |
| `section-<key>` | 自定义分组 |

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/services/objectTypeService.js`
- `src/services/associationService.js`
- `src/services/hierarchyService.js`
- `src/components/common/ObjectPage/*`
- `src/components/common/MetaForm.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 70%(复杂页面组件)

## 5. 边界场景

- 不存在的对象 ID
- 权限不足
- 大对象(>100 字段)
- 关联项循环加载
- 并发编辑冲突

## 6. 易错点

- ⚠️ **乐观锁**: 更新必须传 version
- ⚠️ **草稿**: 编辑模式自动启用
- ⚠️ **删除二次确认**: 必须

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |