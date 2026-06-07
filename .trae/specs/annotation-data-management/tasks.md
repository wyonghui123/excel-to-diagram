# 架构数据备注打标功能任务列表

## 任务总览

本功能分为两个阶段：数据层改造 → UI层改造

---

## 阶段一：数据层改造（P0）

### Task 1.1: 备注对象元模型定义

- [x] Task 1.1.1: 创建 `meta/schemas/annotation.yaml` 文件
- [x] Task 1.1.2: 定义 `id`、`target_type`、`target_id` 字段
- [x] Task 1.1.3: 定义 `category`、`content` 字段
- [x] Task 1.1.4: 定义 `created_at`、`created_by`、`updated_at`、`updated_by` 字段
- [x] Task 1.1.5: 配置 `category` 字段的下拉选项（important/warning/info/tip）

### Task 1.2: 备注对象 Python 类

- [x] Task 1.2.1: 创建 `meta/objects/annotation.py` 文件
- [x] Task 1.2.2: 实现 Annotation 类，继承自 BaseObject

### Task 1.3: 数据库 Schema 同步

- [x] Task 1.3.1: 运行 `python -m meta.tools.sync_schema --diff` 检查变更
- [x] Task 1.3.2: 运行 `python -m meta.tools.sync_schema --execute` 执行同步
- [x] Task 1.3.3: 验证 `annotations` 表创建成功
- [x] Task 1.3.4: 验证索引 `idx_annotation_target` 创建成功

### Task 1.4: 备注 CRUD API

- [x] Task 1.4.1: 在 `meta/api/manage_api.py` 中添加备注 CRUD 端点
- [x] Task 1.4.2: 实现按 `target_type` 和 `target_id` 查询备注列表
- [x] Task 1.4.3: 实现备注创建、更新、删除功能
- [x] Task 1.4.4: 实现级联删除（删除对象时删除关联备注）

---

## 阶段二：UI层改造（P1）

### Task 2.1: 备注列表组件

- [x] Task 2.1.1: 创建 `src/views/ArchDataManageApp/components/AnnotationList.vue` 组件
- [x] Task 2.1.2: 实现备注列表展示（分类图标 + 内容 + 时间）
- [x] Task 2.1.3: 实现"添加备注"按钮
- [x] Task 2.1.4: 实现备注项的"编辑"和"删除"按钮
- [x] Task 2.1.5: 实现无备注时的空状态展示

### Task 2.2: 备注表单弹窗

- [x] Task 2.2.1: 创建 `src/views/ArchDataManageApp/components/AnnotationForm.vue` 组件
- [x] Task 2.2.2: 实现分类下拉选择框
- [x] Task 2.2.3: 实现内容文本框
- [x] Task 2.2.4: 实现表单验证（内容必填）
- [x] Task 2.2.5: 实现保存和取消按钮

### Task 2.3: 详情视图集成

- [x] Task 2.3.1: 在 `DynamicDetail.vue` 中集成 AnnotationList 组件
- [x] Task 2.3.2: 实现备注数据加载（根据当前对象类型和ID）
- [x] Task 2.3.3: 实现备注添加后的列表刷新
- [x] Task 2.3.4: 实现备注编辑后的列表刷新
- [x] Task 2.3.5: 实现备注删除后的列表刷新

### Task 2.4: 列表视图备注预览

- [ ] Task 2.4.1: 在 `DynamicTable.vue` 中添加备注列渲染逻辑
- [ ] Task 2.4.2: 实现备注数量显示 `[N]`
- [ ] Task 2.4.3: 实现第一条备注内容截取（前20字）
- [ ] Task 2.4.4: 实现悬停 Tooltip 显示所有备注
- [ ] Task 2.4.5: 实现无备注时显示 `-`

**注：此任务为 P1 优先级，暂不实现，后续迭代中完成。**

### Task 2.5: API 集成

- [x] Task 2.5.1: 在 `useApi.js` 中添加备注相关 API 方法
- [x] Task 2.5.2: 实现 `listAnnotations(targetType, targetId)` 方法
- [x] Task 2.5.3: 实现 `createAnnotation(data)` 方法
- [x] Task 2.5.4: 实现 `updateAnnotation(id, data)` 方法
- [x] Task 2.5.5: 实现 `deleteAnnotation(id)` 方法

---

## 任务依赖关系

```
Task 1.1 (元模型定义) ──→ Task 1.2 (Python类) ──→ Task 1.3 (Schema同步)
                                                      │
                                                      ↓
                          Task 1.4 (CRUD API) ────────┤
                                                      │
                                                      ↓
Task 2.1 (备注列表组件) ──────────────────────────────┤
Task 2.2 (备注表单弹窗) ──────────────────────────────┼──→ Task 2.6 (集成测试)
Task 2.3 (详情视图集成) ──────────────────────────────┤
Task 2.4 (列表备注预览) ──────────────────────────────┤
Task 2.5 (API集成) ──────────────────────────────────┘
```

**并行任务**：
- Task 2.1, Task 2.2, Task 2.5 可并行开发

---

## 优先级排序

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | Task 1.1 | 备注对象元模型定义 |
| P0 | Task 1.2 | 备注对象 Python 类 |
| P0 | Task 1.3 | 数据库 Schema 同步 |
| P0 | Task 1.4 | 备注 CRUD API |
| P1 | Task 2.1 | 备注列表组件 |
| P1 | Task 2.2 | 备注表单弹窗 |
| P1 | Task 2.3 | 详情视图集成 |
| P1 | Task 2.4 | 列表视图备注预览 |
| P1 | Task 2.5 | API 集成 |

---

## 验证要点

### 数据层验证

- [ ] YAML 文件字段定义完整
- [ ] 数据库表创建成功
- [ ] 索引创建成功
- [ ] CRUD API 正常工作

### UI层验证

- [ ] 备注列表显示正确
- [ ] 备注添加功能正常
- [ ] 备注编辑功能正常
- [ ] 备注删除功能正常
- [ ] 列表视图备注预览正确
- [ ] 悬停 Tooltip 显示正确
