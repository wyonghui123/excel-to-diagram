# 性能优化快速启动指南

## 快速开始

### 1. 执行数据库索引优化

```bash
# 进入项目目录
cd d:\filework\excel-to-diagram

# 执行索引迁移
python -m meta.migrations.add_performance_indexes

# 验证索引
python -m meta.migrations.add_performance_indexes --verify
```

**预期输出**:
```
🚀 开始执行索引迁移: meta/architecture.db

📋 创建索引:
  [HIGH] idx_permission_rules_role_id
    表: permission_rules, 列: role_id
    说明: 角色ID索引，加速按角色查询权限规则
  ✅ 创建索引: idx_permission_rules_role_id (12.34ms)
  ...

✅ 索引迁移完成
```

### 2. 预热热点角色

```bash
# 预热 TOP 50 热点角色
python -m meta.scripts.preload_hot_roles --top-n 50 --verbose
```

**预期输出**:
```
🔥 开始预热热点角色权限规则 (TOP 50)...
📊 识别到 50 个热点角色
✅ 预热完成: 50/50 个角色, 150 条规则, 500 个对象, 耗时 2345.67ms

============================================================
预热结果统计
============================================================
总角色数: 50
成功数: 50
失败数: 0
总规则数: 150
总对象数: 500
耗时: 2345.67ms

缓存统计:
  缓存大小: 50
  最大大小: 500
  TTL: 300秒
============================================================
```

### 3. 查看缓存监控

```bash
# 查看缓存性能报告
python -m meta.services.cache_monitor
```

**预期输出**:
```
======================================================================
缓存性能监控报告
======================================================================

时间: 2026-05-09T10:30:00

📊 缓存统计:
  缓存大小: 50/500
  TTL: 300秒

⚡ 性能指标:
  总请求数: 1000
  缓存命中: 970
  缓存未命中: 30
  命中率: 97.00%
  平均命中时间: 0.0500ms
  平均未命中时间: 45.2300ms
  运行时间: 0:05:30
  QPS: 3.03

💚 健康状态:
  状态: ✅ 健康
  分数: 98/100

💡 优化建议:
  - 缓存性能良好，继续保持当前配置

======================================================================
```

### 4. 执行性能压测

```bash
# 确保应用已启动
python meta/server.py

# 在另一个终端执行性能测试
python meta/tests/performance/run_performance_test.py \
    --host http://localhost:5000 \
    --users 50 \
    --spawn-rate 10 \
    --run-time 5m
```

**预期输出**:
```
======================================================================
管理维度权限系统性能测试开始
======================================================================
目标主机: http://localhost:5000
用户数: 50
======================================================================

[性能测试执行中...]

======================================================================
管理维度权限系统性能测试结束
======================================================================

性能统计:
  总请求数: 10000
  总失败数: 50
  失败率: 0.50%
  平均响应时间: 145.23ms
  中位数响应时间: 120.45ms
  95% 响应时间: 380.67ms
  99% 响应时间: 520.34ms
  RPS: 33.33

性能评估:
  ✅ 平均响应时间达标 (< 200ms)
  ✅ 95% 响应时间达标 (< 500ms)
  ✅ 错误率达标 (< 1%)
======================================================================
```

## 集成到应用启动流程

### 方式 1: 修改 server.py

```python
# meta/server.py

from meta.core.datasource import get_data_source
from meta.services.management_dimension_engine import ManagementDimensionEngine
from meta.scripts.preload_hot_roles import preload_hot_roles

# 初始化数据源和引擎
db_path = os.path.join(os.path.dirname(__file__), 'architecture.db')
data_source = get_data_source('sqlite', database=db_path)
engine = ManagementDimensionEngine(data_source, ttl_seconds=300)

# 预热热点角色
print("🔥 预热热点角色...")
preload_hot_roles(engine, data_source, top_n=50)

# 启动应用
app.run(host='0.0.0.0', port=5000)
```

### 方式 2: 使用启动脚本

```bash
# scripts/start_with_preload.sh
#!/bin/bash

echo "执行数据库索引优化..."
python -m meta.migrations.add_performance_indexes

echo "预热热点角色..."
python -m meta.scripts.preload_hot_roles --top-n 50 &

echo "启动应用..."
python meta/server.py
```

## 监控 API 使用

### 获取缓存统计

```bash
curl http://localhost:5000/api/v1/cache/stats
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "cache_size": 50,
    "max_size": 500,
    "ttl_seconds": 300,
    "hits": 970,
    "misses": 30,
    "hit_rate": "97.00%"
  }
}
```

### 获取性能报告

```bash
curl http://localhost:5000/api/v1/cache/performance
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "timestamp": "2026-05-09T10:30:00",
    "cache_stats": {...},
    "performance_metrics": {...},
    "health_status": {
      "is_healthy": true,
      "score": 98,
      "issues": [],
      "warnings": []
    },
    "recommendations": [
      "缓存性能良好，继续保持当前配置"
    ]
  }
}
```

### 检查健康状态

```bash
curl http://localhost:5000/api/v1/cache/health
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "is_healthy": true,
    "health_status": {
      "is_healthy": true,
      "score": 98,
      "issues": [],
      "warnings": []
    }
  }
}
```

## 性能调优建议

### 1. 缓存命中率低 (< 90%)

**原因分析**:
- 预热角色数量不足
- 缓存 TTL 过短
- 缓存失效过于频繁

**解决方案**:
```bash
# 增加预热角色数量
python -m meta.scripts.preload_hot_roles --top-n 100

# 调整缓存 TTL（在代码中）
engine = ManagementDimensionEngine(data_source, ttl_seconds=600)  # 10分钟
```

### 2. 响应时间慢 (> 200ms)

**原因分析**:
- 数据库索引缺失
- 查询语句未优化
- 缓存未命中

**解决方案**:
```bash
# 重新执行索引迁移
python -m meta.migrations.add_performance_indexes

# 检查慢查询
# 在应用日志中查找 "slow query" 关键字
```

### 3. 错误率高 (> 1%)

**原因分析**:
- 服务器资源不足
- 并发配置不当
- 数据库连接池耗尽

**解决方案**:
```bash
# 检查服务器资源
top
df -h

# 调整并发配置
# 在 locustfile.py 中降低 spawn_rate
python meta/tests/performance/run_performance_test.py --spawn-rate 5
```

## 常见问题

### Q1: 预热脚本执行失败

**错误**: `ModuleNotFoundError: No module named 'meta'`

**解决**:
```bash
# 确保在项目根目录执行
cd d:\filework\excel-to-diagram
python -m meta.scripts.preload_hot_roles
```

### Q2: 索引创建失败

**错误**: `table permission_rules has no column named xxx`

**解决**:
```bash
# 检查表结构
sqlite3 meta/architecture.db "PRAGMA table_info(permission_rules);"

# 如果表不存在，先初始化数据库
python -m meta.scripts.init_database
```

### Q3: 性能测试连接失败

**错误**: `Connection refused: http://localhost:5000`

**解决**:
```bash
# 确保应用已启动
python meta/server.py

# 或使用不同的端口
python meta/tests/performance/run_performance_test.py --host http://localhost:3000
```

## 性能检查清单

启动前检查:
- [ ] 数据库索引已创建
- [ ] 热点角色已预热
- [ ] 缓存监控已启动
- [ ] 应用正常运行

运行时监控:
- [ ] 缓存命中率 > 95%
- [ ] 平均响应时间 < 200ms
- [ ] 错误率 < 1%
- [ ] 服务器资源充足

定期维护:
- [ ] 每周查看性能报告
- [ ] 每月执行性能压测
- [ ] 每季度优化索引
- [ ] 每半年容量规划

## 相关文档

- [性能优化报告](file:///d:/filework/excel-to-diagram/docs/performance/PERFORMANCE_REPORT.md)
- [前端性能优化指南](file:///d:/filework/excel-to-diagram/docs/performance/FRONTEND_OPTIMIZATION.md)
- [热点角色预热脚本](file:///d:/filework/excel-to-diagram/meta/scripts/preload_hot_roles.py)
- [数据库索引迁移脚本](file:///d:/filework/excel-to-diagram/meta/migrations/add_performance_indexes.py)
- [缓存监控服务](file:///d:/filework/excel-to-diagram/meta/services/cache_monitor.py)
- [性能压测脚本](file:///d:/filework/excel-to-diagram/meta/tests/performance/locustfile.py)

---

**文档版本**: 1.0
**更新时间**: 2026-05-09
