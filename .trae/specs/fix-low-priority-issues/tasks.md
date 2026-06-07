# Tasks

## Task 1: 修复 externalBoCodes 逻辑错误
修复 `diagramDataStore.js` 中 `externalBoCodes` 计算逻辑。

- [ ] SubTask 1.1: 添加 `centerScope` 状态到 Store
- [ ] SubTask 1.2: 修复 `externalBoCodes` computed 使用 `centerScope` 计算差集
- [ ] SubTask 1.3: 添加 `setCenterScope` action

## Task 2: HierarchyConfigLoader 缓存失效
为 `HierarchyConfigLoader` 添加 `reload()` 方法。

- [ ] SubTask 2.1: 添加 `reload()` 类方法，清除 `_config` 缓存
- [ ] SubTask 2.2: 添加 `clear_cache()` 类方法

## Task 3: _enrich_record 不修改原始数据
修改 `_enrich_record_with_names` 返回新字典而非修改原字典。

- [ ] SubTask 3.1: 修改函数开头创建 `enriched = dict(record)` 副本
- [ ] SubTask 3.2: 所有赋值操作使用 `enriched` 而非 `record`
- [ ] SubTask 3.3: 函数返回 `enriched`，调用处使用返回值
- [ ] SubTask 3.4: 更新所有调用点使用返回值

## Task 4: Token 存储安全标记（仅标记，不实现）
标记 Token 存储安全改进为待办。

- [ ] SubTask 4.1: 在 authStore.js 中添加 TODO 注释标记未来迁移到 HttpOnly Cookie

---

# Task Dependencies

- Task 1 独立
- Task 2 独立
- Task 3 独立（需更新 manage_api.py 中所有调用点）
- Task 4 独立

# Parallelizable Work

所有任务可并行执行。

# 注意事项

- Task 3 需要仔细检查所有调用 `_enrich_record_with_names` 的地方，确保使用返回值
- Task 4 仅添加 TODO 注释，不做实际代码修改
