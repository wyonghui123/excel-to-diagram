# Disk IO Error 风险分析 + 提前测试方案

> **作者**: 协调智能体
> **日期**: 2026-07-13 22:00
> **触发**: 用户提问 "是否可以提前测试 disk io error 的风险?"
> **基于**: 实测生产环境 IO 状态 + 4 类 IO error 风险梳理

---

## 一、用户问题核心回答

**Q: 是否可以提前测试 disk io error 的风险?**

**A: ✅ 可以, 而且非常建议**. 4 类 IO 风险中, 至少 3 类 (read-only/磁盘满/网络存储) 可以在 staging 沙盒或本地模拟, 提前发现代码层漏洞.

---

## 二、生产 IO 现状实测 (2026-07-13 22:00)

### 2.1 硬件 / 磁盘
| 指标 | 实测 | 风险评估 |
|------|------|---------|
| **磁盘 vda** | 50G, 已用 14G (30%), ext4 rw | ✓ 当前健康 |
| **磁盘 vdb** | 200G, **完全没用** | ⚠️ 资源浪费, 应 mount 到 /opt/app/data |
| **/tmp** | 1.2GB (10% 磁盘) | ⚠️ 累积风险 |
| **inode** | 6% 使用 | ✓ 健康 |
| **/var/log/messages IO error** | 0 条 | ✓ 当前无错误 |
| **iostat util** | 0.12% (极度空闲) | ✓ 性能充足 |

### 2.2 IO 性能基线
| 测试项 | 实测 | 评估 |
|--------|------|------|
| **DB INSERT 1MB** | 6 ms | ⚡ 极快 |
| **fsync 1KB** | 5 ms | ⚠️ 偏高 (云 SSD) |
| **Write 100MB** | 0.90 s (111 MB/s) | ✓ 正常 |
| **Read 100MB** | 0.06 s (1718 MB/s) | ⚡ (page cache) |
| **await 45 ms** | 45 ms | ⚠️ 偏高 (SSD < 5ms) |

### 2.3 SQLite 配置 ⚠️
| 配置 | 当前值 | 期望值 | 风险 |
|------|--------|--------|------|
| **journal_mode** | ❌ `delete` | `wal` | **高** (V007.38 未部署) |
| **synchronous** | `2` (FULL) | `2` (FULL) | ✓ |
| **busy_timeout** | 5000 ms | 5000 ms | ✓ |
| **mmap_size** | `0` | V007.42 禁用 (按设计) | ✓ |
| **-wal / -shm 文件** | ❌ 不存在 | 应存在 | **高** (V007.38 未部署) |

### 2.4 🆘 严重发现 (本次调研附带)
- **`/opt/app/deployments/meta/server.py` 实际 mtime = 2026-07-13 09:06** (v001 部署前)
- **`/opt/app/deployments/meta/core/action_executor.py` mtime = 2026-07-13 08:47** (更早)
- **BUG-V061 修复 (今天 11:30 部署 v001)** **没生效**!
- **17:00 误删 AM-ROLE 成功**, 应该是"修复了"但实际没生效的代码 — 解释了为什么级联删除能跑通!

**实际 prod backend 跑的是 v001 部署前的老代码!**

---

## 三、4 类 IO Error 风险详解

### 3.1 风险 1: 磁盘 read-only 切换 (HIGH ⚠️)
**触发场景**:
- 磁盘物理坏道 (`/dev/vda` 不可写)
- 文件系统 corruption → kernel 切到 read-only
- 云盘故障 (AWS EBS 故障, 阿里云盘 1 分钟内切换)
- ext4 `errors=remount-ro` 触发

**实测触发难度**: ⭐⭐ (容易, `dmesg` 检查很容易, 但生产不允许)

**staging 复现方案** ✅ 推荐:
```bash
# 方案 A: 临时 remount read-only
mount -o remount,ro /opt/app/staging_meta/

# 方案 B: 模拟 SQLite write 失败
python3 -c "
import sqlite3
# 故意写满磁盘 (写入 read-only 文件)
open('/opt/app/staging_db/architecture.db', 'w').close()  # truncate
conn = sqlite3.connect('/opt/app/staging_db/architecture.db')
conn.execute('CREATE TABLE test (id INT)')  # 应该 IO 错误
"

# 方案 C: 用 strace 看 SQLite 调什么 syscall
strace -e openat,write,fsync -f python3 server.py
```

**代码层漏洞** (我们的 core_service / backend):
- 现状: write() 失败只 print, 不重试
- 改进: ENOSPC/EROFS 时 retry + 报警

**实际工作量