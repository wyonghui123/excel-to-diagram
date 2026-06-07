# 测试覆盖率基线报告

## 测试覆盖率基线建立

**建立日期**: 2026-05-29
**pytest-cov 版本**: 7.1.0
**Python 版本**: 3.x

---

## 当前覆盖率状态

| 模块 | 覆盖率 | 目标 | 差距 |
|------|:-------:|:----:|:----:|
| meta/core | ~40% | 80% | -40% |
| meta/services | ~35% | 70% | -35% |
| meta/api | ~50% | 80% | -30% |
| meta/interceptors | ~60% | 80% | -20% |
| **总计** | **~45%** | **75%** | **-30%** |

---

## 覆盖率改进建议

### 1. 增加断言覆盖

当前测试主要验证 API 响应状态码，缺少对返回数据结构的深度验证。

**建议**:
```python
# 当前
assert resp.status_code == 200

# 建议增强
assert resp.status_code == 200
data = resp.get_json()
assert 'data' in data
assert 'id' in data['data']
assert data['data']['name'] == expected_name
```

### 2. 补充边界条件测试

当前测试覆盖了 Happy Path，缺少边界条件测试。

**建议增加**:
- 空字符串、None 值、最大长度
- 特殊字符、SQL 注入、 XSS
- 并发冲突、事务回滚

### 3. 使用覆盖率工具

运行覆盖率测试:
```bash
# 单元测试覆盖率
pytest --cov=meta.core --cov-report=term-missing tests/unit/

# 集成测试覆盖率
pytest --cov=meta --cov-report=html tests/integration/

# 生成 HTML 报告
pytest --cov=meta --cov-report=html tests/
```

---

## 测试分层执行命令

```bash
# 只运行单元测试
pytest -m unit tests/

# 只运行集成测试
pytest -m integration tests/

# 只运行 E2E 测试
pytest -m e2e tests/

# 跳过慢速测试
pytest -m "not slow" tests/

# 生成覆盖率报告
pytest --cov=meta tests/ --cov-report=html
```

---

## 覆盖率目标

| 阶段 | 覆盖率目标 | 时间 |
|------|:----------:|:----:|
| Phase 1 | 50% | 当前 |
| Phase 2 | 65% | 1 周 |
| Phase 3 | 75% | 2 周 |
| 最终 | 80%+ | 持续 |

---

## 相关工具

- pytest-cov: 覆盖率测量
- coverage.py: 覆盖率分析
- coverage.py html: HTML 报告生成
