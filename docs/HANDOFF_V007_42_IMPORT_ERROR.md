# V007.42 部署失败紧急回滚 + dev-agent 修复交接

**日期**: 2026-07-08 15:50
**优先级**: P0 (业务中断, 5001 死)
**commit HEAD**: 1bec474f (V007.42 P7)

---

## 1. 现象 (yonaa 部署后)

```
[FAIL] 5001: 未监听
[FAIL] backend /health = 000000 (3 attempts)
[FAIL] api/v2/bo/health 不可达
[FAIL] login 失败: Connection refused (Errno 111)
```

**disk I/O error 计数 = 0** (因为 backend 死, 没人触发)

## 2. 根因 (ImportError)

`backend-v20260708_008.log` 关键一行:

```
ImportError: cannot import name 'get_bo_framework' from 'meta.core.bo_framework'
  (/opt/app/deployments/meta/core/bo_framework.py)
```

**位置**: `meta/api/intent_api.py:26`

```python
from meta.core.bo_framework import get_bo_framework  # ❌ 不存在
with get_bo_framework().transaction() as txn:        # ❌ 找不到
```

**真相**:
- `meta/core/bo_framework.py` 只有 `class BOFramework` 和单例 `bo_framework = BOFramework()`
- **没有 `get_bo_framework()` 函数**
- V007.41 P3 (`9d051f9`) 假设 `get_bo_framework()` 存在, **没验证就 commit**
- V007.42 P5/P6/P7 也没发现, **连续 5 个 dev-agent commit 没测启动**

## 3. 紧急回滚命令 (SSH yonaa)

```bash
# 回滚到 v20260708_005 (V007.40 部署版本, 最后一个工作版)
bash /tmp/rollback.sh --to v20260708_005 --port 5001 2>&1 | tee /tmp/rollback_to_v20260708_005.log
```

**回滚后**:
- `/opt/app/current` → `/opt/app/deployments/v20260708_005`
- backend 启 V007.40 (HEAD 7c71636) 代码
- 5001 端口 listening
- 业务恢复

**注意**: 旧 v20260708_005 不含 v027-pt2 fix, **会回到 BUG-V027-pt2 BUG 状态**。但比"backend 死"强, 业务至少可用。

## 4. dev-agent 需要修的 (V007.43 P0)

### 4.1 修复方案 A (推荐) — 加 get_bo_framework() 函数

```python
# meta/core/bo_framework.py 末尾追加
def get_bo_framework() -> BOFramework:
    """[V007.43 P0] 单例获取函数 (V007.41 P3 引用但漏写)"""
    return bo_framework
```

### 4.2 修复方案 B — intent_api.py 改用实例

```python
# meta/api/intent_api.py
# 旧 (错):
from meta.core.bo_framework import get_bo_framework
with get_bo_framework().transaction() as txn:
# 新 (对):
from meta.core.bo_framework import bo_framework
with bo_framework.transaction() as txn:
```

### 4.3 防退化 invariant V8q

```python
# V8q. intent_api.py 引用 get_bo_framework 时, bo_framework.py 必须有这个函数
def check_v8q_intent_api_bo_framework_consistency() -> tuple:
    """V8q. [V007.43 P0 BUG-FIX] intent_api 引用 get_bo_framework 时
    bo_framework.py 必须有同名函数, 否则启动 ImportError (V007.41 P3 BUG 复发)
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            api = zf.read("meta/api/intent_api.py").decode("utf-8", errors="ignore") if "meta/api/intent_api.py" in zf.namelist() else ""
            bf = zf.read("meta/core/bo_framework.py").decode("utf-8", errors="ignore") if "meta/core/bo_framework.py" in zf.namelist() else ""
        # 找 api 用的函数名
        import re
        funcs_used = set(re.findall(r'from meta\.core\.bo_framework import (\w+)', api))
        for f in funcs_used:
            if f == "BOFramework":
                continue  # 类导入不算
            if not re.search(rf'^\s*def\s+{f}\s*\(', bf, re.MULTILINE):
                return (False, f"intent_api 引 '{f}' 但 bo_framework.py 没这个函数 (V007.41 P3 BUG 复发)")
        if not funcs_used:
            return (True, "intent_api 未引用 bo_framework 函数, 跳过")
        return (True, f"intent_api 引用 {funcs_used} 在 bo_framework.py 全部存在")
    except Exception as e:
        return (False, f"读 zip 失败: {e}")
```

### 4.4 dev-agent 部署前必测

```bash
# 本地启 server 验证启动成功
cd /opt/app/deployments/meta
PORT=5001 FLASK_DEBUG=true PYTHONUNBUFFERED=1 /opt/miniconda3-py39/bin/python server.py &
sleep 5
ss -tlnp | grep ":5001"  # 必须 listening
# 如果死, 看 log 找 ImportError
```

## 5. 我的反思 (部署智能体)

| 失职 | 反思 |
|------|------|
| dev-agent V007.41 P3 漏函数, 我没在打包时本地启 server 验证 | **部署前必须本地启 server 5 秒, 确认 listening** |
| 5 个 dev-agent commit (P1-P7) 都没测启动 | **invariant 应加 V8q 引用一致性检查** |
| 我看 V8g 失败 (mmap=0) 还以为 V007.42 正确 | **mmap=0 是设计变化, 但 ImportError 是真问题, 我没启 server 验证** |

## 6. yonaa 当前状态 (15:50)

| 服务 | 状态 |
|------|------|
| backend 5001 | ❌ 死 (ImportError) |
| unified 8081 | ✅ 在跑 (但 5xx, 因为 5001 死) |
| log_service 9101 | ✅ v4.5 在跑 |
| architecture.db | ✅ integrity=ok (没人用, 没事) |

## 7. 修复后部署流程 (V007.43)

1. dev-agent 修代码 (方案 A 或 B)
2. dev-agent 本地 `python server.py` 5 秒验证 listening
3. 部署智能体重打 zip + 加 V8q invariant
4. 部署智能体 yonaa 部署 + 远程验证
5. 不再 ImportError = 业务恢复

---

**紧急**: 先跑回滚命令恢复业务 (命令见 §3)
**dev-agent**: 修代码 + 加测试 (方案见 §4)
**部署智能体**: 接手 V007.43 zip + 部署
