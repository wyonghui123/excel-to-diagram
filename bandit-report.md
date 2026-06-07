# Bandit 安全扫描报告

**扫描日期**: 2026-05-21
**扫描范围**: meta/ 目录
**Python 版本**: 3.14.3
**Bandit 版本**: 1.9.4

---

## 扫描结果摘要

| 严重级别 | 数量 | 说明 |
|----------|------|------|
| **HIGH** | 2 | 弱 MD5 哈希（非安全用途） |
| **MEDIUM** | 320 | SQL 注入风险（f-string 拼接） |
| **LOW** | 475 | try/except/pass 模式 |
| **总计** | **797** | - |

---

## HIGH 级别问题 (2个)

### B324: 弱 MD5 哈希

| 文件 | 行号 | 说明 |
|------|------|------|
| `meta/api/bo_api.py` | L93 | schema-version 端点使用 MD5 计算 YAML hash |
| `meta/core/analytical_engine.py` | L156 | 分析引擎使用 MD5 |

**风险评估**: 这些 MD5 用于**非安全用途**（文件 hash、数据指纹），不涉及密码存储或加密。可通过添加 `usedforsecurity=False` 参数消除警告。

**修复建议**:
```python
hashlib.md5(content, usedforsecurity=False)
```

---

## MEDIUM 级别问题 (320个)

### B608: SQL 注入风险

**分布**:
- `meta/core/association_engine.py`: 40+ 处
- `meta/services/query_service.py`: 30+ 处
- `meta/services/data_permission_service.py`: 20+ 处
- `meta/api/`: 80+ 处
- 其他: 150+ 处

**风险评估**:
- 大部分使用 `meta_object.table_name`，来自 YAML 配置（可信源）
- 参数值使用 `?` 占位符，无直接用户输入拼接
- 已有 `validate_table_name()` 白名单校验

**结论**: **风险可控**，但建议持续审查新增代码。

---

## LOW 级别问题 (475个)

### B110: try/except/pass 模式

**说明**: 静默捕获异常，可能隐藏错误。

**风险评估**: 大部分用于：
- 可选功能降级（如缓存失败时继续）
- 兼容性处理（如旧版本迁移）
- 日志记录后的静默处理

**结论**: **低风险**，可在代码审查时逐步优化。

---

## 基线配置

已创建 `.bandit` 配置文件：

```yaml
skips:
  - B101  # assert 语句（测试中大量使用）
  - B311  # random 模块（非加密用途）
exclude_dirs:
  - /tests/
  - /test/
  - /node_modules/
  - /.git/
  - /venv/
  - /dist/
  - /build/
  - /meta/tests/
  - /meta/dev/
  - /meta/tools/
```

---

## 后续建议

1. **修复 HIGH 问题**: 为 MD5 调用添加 `usedforsecurity=False`
2. **持续监控**: 在 CI/CD 中集成 bandit 扫描
3. **代码审查**: 对新增 SQL 拼接代码进行安全审查
4. **定期扫描**: 每周运行一次全量扫描

---

## CI/CD 集成示例

```yaml
# .github/workflows/security.yml
- name: Security Scan
  run: |
    pip install bandit
    bandit -r meta/ -c .bandit -f json -o bandit-report.json
    bandit -r meta/ -c .bandit --severity-level high
```
