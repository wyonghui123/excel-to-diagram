# 枚举依赖关系通用化 — 任务分解

> Edition: v4 — 新增 UI 适配任务

---

## Phase 1: 数据模型准备

### Task 1.1: 新增 Direction 枚举类
- [ ] 在 `meta/core/models.py` 新增 `Direction` 类（PUSH/PULL/BIDIRECTIONAL）
- [ ] 验证：`python -c "from meta.core.models import Direction; print(list(Direction))"`

### Task 1.2: 注册到 migrate_enums.py
- [ ] 将 `Direction` 加入 `ENUM_CLASSES`
- [ ] 在 `ENUM_VALUE_NAME_MAP` 添加中文映射（PUSH→推 / PULL→拉 / BIDIRECTIONAL→双向）
- [ ] 验证：重启服务后枚举管理页面显示 `direction` 类型

### Task 1.3: 创建 enum_dependency_links 表
- [ ] 在 `meta/scripts/init_database.py` 添加建表SQL + `create_enum_dependency_links_table()`
- [ ] 在服务启动流程中调用建表
- [ ] 验证：`PRAGMA table_info(enum_dependency_links)` 表结构正确

---

## Phase 2: 依赖关联迁移

### Task 2.1: 现有 dimensions JSON → enum_dependency_links 迁移脚本
- [ ] 遍历 relation_type 的 enum_values，读取 `dimensions` JSON
- [ ] 若含 `direction` → INSERT 到 `enum_dependency_links`（child_enum_value=NULL）
- [ ] REFERENCES（dimensions 为空）→ 不插入
- [ ] 验证：`SELECT * FROM enum_dependency_links` 恰有 3 行

### Task 2.2: 集成到启动流程
- [ ] 在 `migrate_enums()` 中调用迁移
- [ ] 确保幂等（INSERT OR IGNORE）

---

## Phase 3: API 层 + 元模型 YAML

### Task 3.1: 枚举依赖查询 API
- [ ] `GET /api/v1/enum-dependencies/parent/<type_id>/<value>`
- [ ] 返回结构：`{ dependencies: [{ enum_type_id, enum_type_name, values: [{code, name, name_en, sort_order}] }] }`
- [ ] REFERENCES → `{ dependencies: [] }`

### Task 3.2: 维度 API 的 dimension_schema 兼容
- [ ] 从 `enum_dependency_links` 动态计算 `dimension_schema` 并返回
- [ ] 保持 JSON 格式不变

### Task 3.3: 新增 enum_dependency_link.yaml
- [ ] 定义完整的元模型（字段、UI配置、关联关系）
- [ ] 让 `MetaListPage` 和 `DetailPage` 可自动渲染依赖列表

### Task 3.4: 更新 enum_type.yaml
- [ ] 在 `child_sections` 中新增 `enum_dependency_link` 子对象区域
- [ ] `dimension_schema` 字段标记为只读 + 提示文字

---

## Phase 4: 前端适配

### Task 4.1: EnumService 扩展
- [ ] 新增 `EnumService.loadDependencyOptions(enumTypeId, enumValue)`
- [ ] 调用 `GET /api/v1/enum-dependencies/parent/...`
- [ ] 缓存与 `loadOptions` 一致

### Task 4.2: EnumDependencySelector 组件
- [ ] 创建 `src/components/common/EnumDependencySelector.vue`
- [ ] Props: `parentEnumTypeId`, `parentEnumValue`, `modelValue`
- [ ] 依赖为空时不渲染任何元素
- [ ] 支持 v-model 双向绑定维度值对象

### Task 4.3: 关系表单集成
- [ ] 在 relationship 表单中嵌入 `EnumDependencySelector`
- [ ] 选中 GENERATES/UPDATES/TRIGGERS → direction 选择器出现
- [ ] 选中 REFERENCES → 无子选择器

### Task 4.4: ObjectPage 枚举显示改造
- [ ] 替换 `ObjectPage.vue` 中 `prop="relation_code"` → 使用 `EnumFieldDisplay`
- [ ] 同步更新 `business_object.yaml` associations.columns
- [ ] 替换 `archDataConverter.js` 中的 relation_code → relation_type 透传

---

## Phase 5: 验证

### Task 5.1: 全链路验证
- [ ] 枚举管理页面：`direction` 可见可管理
- [ ] enum_type 详情页：枚举依赖子区域可增删
- [ ] 关系表单：维度选择器正确联动
- [ ] ObjectPage：关系类型显示中文名
- [ ] 导入导出：兼容

---

## 依赖关系

```
Phase 1 ──► Phase 2 ──► Phase 3 ──┬──► Phase 4a (管理端)
                                  └──► Phase 4b (业务端)
                                            │
                                       Phase 5 (验证)
```
