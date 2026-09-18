---
description: "远端 DB 同步工具规则 — 何时用 pull_db / push_db，dev 工作第一时间知道有这个工具"
---

# 远端 DB 同步 Rule (remote-db-sync)

> **目的**: 让 AI Agent 在需要 "从 staging / production 拉 DB 到本地" 或 "推本地 DB 到远端" 时，第一时间知道有 `pull_db` / `push_db` 工具可用。

---

## 🚨 何时用 (AI Agent 必查)

**当用户或你的工作涉及以下场景时，先看本文件**:

| 场景 | 用户可能的表达 |
|------|----------------|
| 从 staging 拉最新 DB | "从 staging 拉一下 DB" / "同步 staging 数据库" / "本地要 staging 的最新数据" |
| 推本地 DB 到 staging | "推上去" / "把本地数据库推到 staging" / "验证我的修复在 staging 上" |
| 拉 prod DB 回放事故 | "拉一下 prod 的 DB" / "生产数据库复现" / "prod 数据回放" |
| Round-trip 验证 | "CI 测一下 DB 同步" / "本地推到 staging 再拉回来比对" |

---

## ✅ 唯一入口

**绝对不要手写 iterdump + gzip + base64 + 分块读脚本** — 这些坑都已经踩过。

```bash
# 拉 (staging / production)
python tools/pull_db.py \
    --remote <远端 DB 路径> \
    --local <本地路径> \
    --backup <本地原 DB 备份> \
    [--target staging|production]  # 默认 staging

# 推 (staging / production)
python tools/push_db.py \
    --local <本地 DB 路径> \
    [--target staging|production]  # 默认 staging

# 仅查远端 DB 信息 (不下载)
python tools/pull_db.py --target staging \
    --remote <远端 DB 路径> --info
```

**详见**：[`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md)（326 行完整文档）

**简短摘要**：[`docs/lessons-learned/remote-db-sync.md`](../../docs/lessons-learned/remote-db-sync.md)

---

## ⚠️ 禁止事项

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 手写 base64 + cat 拼回 + sqlite3 restore | `python tools/pull_db.py` |
| 通过 staging exec 一个个 grep DB 信息 | `python tools/pull_db.py --info` |
| 直接用 `cat /opt/app/.../architecture.db` 下载 | `python tools/pull_db.py` |
| production 用 `push_db --target production` 部署 | 用 `tools/prod_deploy_orchestrator.py` |

---

## 🔑 关键事实 (5 分钟必须知道)

1. **不依赖 staging exec 白名单**: 全部用 Python 替代 (无 base64/dd/rm/sed 命令依赖)
2. **自动 chunk + 限流**: 30000 字节/块, 每 5 part sleep 1.5s, 8 次重试 + 退避
3. **token 跨小时自动重生成**: `_gen_tokens` 生成 current + previous 2 hours
4. **默认环境**: staging (172.20.59.7:19200), production 用 `--target production`
5. **测试已通过**: 6+7 unit PASS, round-trip 113s (117MB staging) + 1.5s (2.15MB test)

---

## 📚 相关

- 完整文档: [`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md)
- 简短摘要: [`docs/lessons-learned/remote-db-sync.md`](../../docs/lessons-learned/remote-db-sync.md)
- Staging deploy 通用化: [`docs/retrospectives/2026-09-13-deploy-topology-generalization.md`](../../docs/retrospectives/2026-09-13-deploy-topology-generalization.md)
- 底层 yonaa 远端客户端: [`tools/yonaa_exec.py`](../../tools/yonaa_exec.py)
- 高层 ops 封装: [`tools/staging_ops.py`](../../tools/staging_ops.py)

---

**创建日期**: 2026-09-18
**维护**: dev agent (V061 staging)