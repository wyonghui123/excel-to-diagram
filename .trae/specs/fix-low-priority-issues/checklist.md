# Checklist

## Task 1: 修复 externalBoCodes 逻辑错误
- [ ] `diagramDataStore.js` 添加 `centerScope` 状态
- [ ] `externalBoCodes` 正确计算差集（relationBoCodes - centerScope）
- [ ] `setCenterScope` action 可用
- [ ] centerScope 为空时 externalBoCodes 等于 relationBoCodes

## Task 2: HierarchyConfigLoader 缓存失效
- [ ] `reload()` 方法清除 `_config` 缓存
- [ ] `clear_cache()` 方法可用
- [ ] 调用 `reload()` 后 `get_config()` 返回最新配置

## Task 3: _enrich_record 不修改原始数据
- [ ] `_enrich_record_with_names` 返回新字典
- [ ] 原始 record 字典不被修改
- [ ] 所有调用点使用返回值
- [ ] `list_records` 中使用返回值
- [ ] `get_record` 中使用返回值

## Task 4: Token 存储安全标记
- [ ] authStore.js 中添加 TODO 注释
