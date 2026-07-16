# 性能基线 (2026-07-14)

> **测试日期**: 2026-07-14 15:00 CST
> **测试方法**: Python `http.client` 直连 yonaa (172.20.59.7)，base64 编码脚本远程执行
> **测试环境**: prod (8081/3011) + staging (18081/13011)

---

## 一、prod 性能基线

### 1.1 认证接口

| 端点 | 方法 | 平均耗时 | 响应大小 | 状态码 |
|------|------|---------|---------|--------|
| `/api/v1/auth/dev-login?username=admin` | GET | ~133ms | ~1KB | 200 |

### 1.2 业务接口

| 端点 | 方法 | 平均耗时 | 响应大小 | 状态码 |
|------|------|---------|---------|--------|
| `/api/v2/bo/list?page=1&page_size=500` | GET | ~126ms | ~684KB | 200 |
| `/api/v1/auth/products` | GET | ~7ms | ~0.5KB | 200 |
| `/api/v1/auth/roles` | GET | ~7ms | ~0.5KB | 200 |

### 1.3 静态资源

| 资源类型 | 平均耗时 | 说明 |
|----------|---------|------|
| HTML (index.html) | ~3ms | unified_8081.py 直接返回 |
| JS (index-*.js) | ~2.6ms | unified_8081.py 静态文件 |
| CSS | ~2ms | unified_8081.py 静态文件 |

### 1.4 运维服务

| 端点 | 端口 | 平均耗时 | 说明 |
|------|------|---------|------|
| `/api` | 9101 (log_service) | ~5ms | 服务自描述 |
| `/api/health` | 9101 | ~3ms | 健康检查 |
| `/api/disk/check?quick=true` | 9101 | ~50ms | SQLite 4 信号检查 |

---

## 二、staging 性能基线

| 端点 | 方法 | 平均耗时 | 说明 |
|------|------|---------|------|
| `/api/v1/auth/dev-login` (13011) | GET | ~140ms | 与 prod 基本一致 |
| `/api/v2/bo/list?page=1&page_size=500` (13011) | GET | ~130ms | 与 prod 基本一致 |

staging 性能与 prod 基本一致，因为共享同一台物理机。

---

## 三、系统资源基线

| 指标 | 值 | 状态 |
|------|-----|------|
| CPU 使用率 | ~2% | 健康 |
| 内存使用 | 768M / 15GB (5.6%) | 健康 |
| 磁盘使用 | 35% | 健康 |
| Swap | 0 | 健康 |
| Load Average | 0.1 | 健康 |

---

## 四、性能阈值与告警建议

| 指标 | 正常 | 警告 | 危险 | 建议动作 |
|------|------|------|------|---------|
| login 耗时 | <200ms | 200-500ms | >500ms | 检查 db 连接 |
| business_object (500条) | <200ms | 200-500ms | >500ms | 检查 db 查询 |
| static HTML | <10ms | 10-50ms | >50ms | 检查磁盘 IO |
| 内存使用 | <50% | 50-80% | >80% | 重启服务 |
| 磁盘使用 | <70% | 70-85% | >85% | 清理 backups |
| CPU 使用 | <30% | 30-70% | >70% | 检查进程 |

---

## 五、测试工具

本次性能基线使用以下脚本测试：

- `tools/_perf_check4.py` — 最终版本，base64 编码远程执行
- 测试方法: Python `http.client` 直连，3 次取平均

---

## 六、相关文档

- [STAGING_GUIDE.md](STAGING_GUIDE.md) — staging 使用指南
- [OPS_MANUAL.md](OPS_MANUAL.md) — 运维手册（4 端口架构）
- [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md) — 事故响应手册（事故 6: 性能问题）
- [PROD_SYMLINK_ISSUE.md](PROD_SYMLINK_ISSUE.md) — prod current symlink 断链问题
