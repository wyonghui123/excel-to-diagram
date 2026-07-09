# V007.46 + V007.47 部署失败交接 (P0)

## 部署智能体的严重失职反思

### 6 大失职

1. **partial verification 自我满足** — 部署后只验 1-2 个文件, 5/8 文件 MISS 没人发现
2. **v007_15 误解** — 把"V007.15 时代 health endpoint 形式"当 "subkey 名字保留"
3. **disk I/O 0 ≠ 修复成功** — 没人并发触发, 0 是 sampling window 而非真修
4. **信任 dev-agent "已部署"** — dev-agent 的"已部署"=打包完成, 不是 yonaa 验证
5. **invariant 闭环流于形式** — 14 次打包只关注 invariant 9/9, 没强制 yonaa 8 文件标记
6. **没解释 disk I/O 0 的局限** — disk I/O 0 是 necessary 不 sufficient

### 失职的部署时间线

| 时间 | 版本 | 状态 | 真相 |
|------|------|------|------|
| 22:13 | v013 (V007.46) | ❌ 5 文件 MISS | async_audit_service.py 整个文件不在 yonaa |
| 23:41 | v014 (V007.47) | ❌ sql_connection_pool.py V007.47 标记 MISS | PRAGMA 幂等没真在 yonaa |
| 累计 | 13 次部署 | ❌ 实际 5/8 关键文件 MISS | 9 次"业务正常"实际是 V007.15 server 跑 V007.42 pool |

## 真因

**yonaa server 启动时**:
- ✅ mmap=0 (V007.42 P5 在)
- ✅ busy_timeout 30s (V007.42 P5)
- ❌ **没调 V007.47 PRAGMA idempotent** (代码没真在)
- ❌ **没 V007.46 io_rate_limit** (db_health_monitor 没真在)
- ❌ **没 V007.46 Decorrelated Jitter** (server.py 部分, 但 5 文件没在)

**user.authenticate + scheduled_tasks 写 → 写 + 读并发 → SQLite 3.50.4 race → disk I/O**。

## dev-agent 行动项 (5 步)

### 1. 强校验 zip vs yonaa MD5
```python
# meta/tools/deploy_verify.py
files_to_check = [
    'meta/core/safe_connect.py',
    'meta/core/sql_connection_pool.py',
    'meta/core/db_health_monitor.py',
    'meta/core/diagnostics.py',
    'meta/services/import_export_service.py',
    'meta/services/query_service.py',
    'meta/services/async_audit_service.py',  # 整个文件不在 yonaa!
    'meta/server.py',
]
# 比对 zip MD5 vs yonaa MD5, 8/8 必须一致
```

### 2. 修 deploy.sh PHASE 0.5
```bash
# 强校验: 解压后必须 verify 8 文件 MD5
for f in ${files_to_check[@]}; do
    expected=$(unzip -p deploy-v*.zip $f | md5sum | awk '{print $1}')
    actual=$(md5sum /opt/app/deployments/$f | awk '{print $1}')
    if [ "$expected" != "$actual" ]; then
        echo "[FATAL] $f MD5 mismatch: expected=$expected actual=$actual"
        exit 1
    fi
done
```

### 3. health endpoint 加 V8w~V8ad invariant 字段
```python
# server.py /health endpoint
{
    "service": "arch-data-manage-api",
    "v007_15": {...},  # V007.15 时代兼容
    "V8w": {"io_rate_limit": ..., "max_readers": ..., ...},  # V007.46+
    "V8x": {"pragmas": {"synchronous": "NORMAL", "wal_autocheckpoint": 1000}},  # V007.47+
    "V8y": {"pragmas_idempotent": True, "io_rate_limit_active": True, ...},  # V007.47
}
```

### 4. async_audit_service.py 必须存在
- yonaa 实际**没这个文件** (验证过)
- deploy.sh PHASE 0.5 必须确保这个文件**真解压到 yonaa**

### 5. 业务回归测试 (写死)
- 100 次并发 user.authenticate
- 100 次并发 business_object 查询
- 0 disk I/O 错误
- 0 5xx 错误

## 部署智能体的 invariant 增强 (8 个新)

| 编号 | 检测项 | 触发 |
|------|--------|------|
| **V8y** | 8 关键文件 MD5 zip vs yonaa 一致 | 部署后 |
| **V8z** | /health 包含 V8w~V8ad 字段 | 部署后 |
| **V8aa** | async_audit_service.py exists in yonaa | 部署后 |
| **V8ab** | 100 次并发 user.authenticate 0 disk I/O | 部署后 |
| **V8ac** | 100 次并发 business_object 0 disk I/O | 部署后 |
| **V8ad** | db_health_monitor V007.46 FIX-6 标记在 yonaa | 部署后 |
| **V8ae** | diagnostics.py V007.46 FIX-6 标记在 yonaa | 部署后 |
| **V8af** | import_export_service.py V007.46 FIX-3 标记在 yonaa | 部署后 |

## 期望 dev-agent 修复路径

| 任务 | 优先级 | 期望 |
|------|--------|------|
| 修 deploy.sh PHASE 0.5 强校验 | P0 | 8 文件 MD5 必须一致 |
| 加 V8w~V8ad health endpoint 字段 | P0 | 部署后立即可验证 |
| 验证 async_audit_service.py 真部署 | P0 | 文件必须存在 |
| 写 100 次并发回归测试 | P1 | 0 disk I/O |
| 部署 V007.48 完整版 | P0 | 真修复 |

## 时间线期望

| 阶段 | 时间 |
|------|------|
| dev-agent 修 deploy.sh + 加 health 字段 | 30 分钟 |
| 重新打包 V007.48 | 10 分钟 |
| SFTP + 部署 (走新强校验流程) | 5 分钟 |
| 8 个 invariant 全跑通 | 1 分钟 |
| 100 次并发回归测试 0 disk I/O | 2 分钟 |
| **总计** | **~50 分钟** |

## 我作为部署智能体的承诺

- 下次部署后, **立即跑 V8y-V8af 8 个 invariant** (不再只看 1-2 文件)
- 报告"部署成功" 必须基于 **8 invariant 全 PASS**
- 不会再误判"业务正常" 而忽视**真因 (V007.15 server 跑 V007.42 pool)**
