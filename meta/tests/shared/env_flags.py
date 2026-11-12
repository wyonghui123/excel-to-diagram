# -*- coding: utf-8 -*-
"""
[MODULE] 测试态环境开关注册表（单一声明源）
[DESCRIPTION] 集中声明「测试期间必须设置的环境变量」，供 conftest.py 统一注入。

为什么需要这个模块：
- 过去这些开关散落在 conftest.py 的模块顶部和 pytest_configure() 里，
  新增一个开关时容易漏配（例如 CRON_JOBS_ENABLED 曾漏了，导致测试进程内
  启动 3 个 60s 轮询的 cron 调度器，与用例事务争 SQLite 锁）。
- 现在开关集中声明、集中注入，并记录「谁消费 / 为什么设置 / 事故依据」，
  其他 Agent 新增测试态开关时只需在 FLAGS 里加一行。

使用方式（仅 conftest.py 调用）：
    from meta.tests.shared.env_flags import apply_early_flags, apply_test_flags
    apply_early_flags()   # 模块导入期即生效（fixtures 导入之前）
    apply_test_flags()    # pytest_configure() 内批量生效

新增开关的约定：
1. 先判断生效时机：
   - "import"：必须在任何业务模块被导入之前生效（如 DISABLE_RATE_LIMIT）。
   - "configure"：在 pytest_configure() 内生效即可（绝大多数）。
2. 在 FLAGS 中追加一条 EnvFlag，填 purpose / owner / evidence 三个字段。
3. 不要在测试文件里再散落 `os.environ['X'] = 'y'`；需要临时反例的用例自行
   保存-修改-恢复（例如 test_security_improvements.py 验证限流时必须显式开启）。

CLI（诊断用）：
    python meta/tests/shared/env_flags.py --json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class EnvFlag:
    """一条测试态环境开关声明。"""

    name: str
    value: str
    phase: str                      # "import" | "configure"
    mode: str                       # "set" | "setdefault" | "unless_env"
    purpose: str
    owner: str = ""                 # 消费方（读取该变量的代码）
    condition_env: str = ""         # mode="unless_env" 时的条件变量
    condition_value: str = ""       # 条件变量等于该值时跳过设置
    evidence: str = ""              # 实测数据 / 事故依据


FLAGS: Tuple[EnvFlag, ...] = (
    EnvFlag(
        name="DISABLE_RATE_LIMIT",
        value="true",
        phase="import",
        mode="set",
        purpose="关闭登录限流，避免测试用例之间因失败次数累计被互相封禁",
        owner="meta/services/rate_limiter.py",
        evidence="conftest 必须在 shared.fixtures 导入前设置（历史顺序要求）",
    ),
    EnvFlag(
        name="TESTING",
        value="true",
        phase="configure",
        mode="set",
        purpose="标记测试运行态，供 create_app / 各服务分支判断",
        owner="meta/server.py 及各服务",
    ),
    EnvFlag(
        name="DISABLE_ASYNC_AUDIT_WRITER",
        value="true",
        phase="configure",
        mode="set",
        purpose="关闭异步审计写入线程，避免后台线程与用例事务耦合",
        owner="meta/services/audit_service.py",
    ),
    EnvFlag(
        name="DISABLE_TASK_SCHEDULER",
        value="true",
        phase="configure",
        mode="set",
        purpose="关闭 task_scheduler，避免进程内定时任务干扰用例",
        owner="meta/server.py",
    ),
    EnvFlag(
        name="DISABLE_WRITE_QUEUE",
        value="true",
        phase="configure",
        mode="set",
        purpose="关闭写队列后台线程，用例直接同步写库",
        owner="meta/services/write_queue.py",
    ),
    EnvFlag(
        name="CRON_JOBS_ENABLED",
        value="0",
        phase="configure",
        mode="unless_env",
        purpose="关闭 create_app() 内的 3 个 cron 调度器"
                "（maintenance / platform / workflow，各 60s 轮询）",
        owner="meta/server.py",
        condition_env="TEST_ALLOW_CRON",
        condition_value="1",
        evidence="TEST-EFF P0-1：未关闭时每个 worker 进程 12 个轮询线程，"
                 "与用例事务争 SQLite 锁并累计线程",
    ),
    EnvFlag(
        name="SKIP_DB_PREFLIGHT",
        value="1",
        phase="configure",
        mode="setdefault",
        purpose="跳过 create_app() 的整库 quick_check 预检",
        owner="meta/server.py",
        evidence="TEST-EFF P1-5：165MB 库实测 1.35-1.56s/进程；"
                 "测试库由 SQLite backup 快照产生，真损坏会在首次 SQL 操作时暴露",
    ),
)

# 只做观测、不由本模块设置的开关（供基线/诊断输出展示真实运行态）。
_OBSERVED_ONLY: Tuple[str, ...] = ("GUARD_FORCE", "PYTHONHASHSEED")


def _apply(flag: EnvFlag) -> Optional[str]:
    """按声明的 mode 应用单个开关，返回应用后的生效值（跳过时返回原值）。"""
    current = os.environ.get(flag.name)

    if flag.mode == "set":
        os.environ[flag.name] = flag.value
        return flag.value

    if flag.mode == "setdefault":
        if current is None:
            os.environ[flag.name] = flag.value
            return flag.value
        return current

    if flag.mode == "unless_env":
        if os.environ.get(flag.condition_env) == flag.condition_value:
            return current
        os.environ[flag.name] = flag.value
        return flag.value

    raise ValueError(f"{flag.name}: 未知 mode={flag.mode!r}")


def apply_phase(phase: str) -> Dict[str, Optional[str]]:
    """应用某一阶段的所有开关，返回 {name: 生效值}。"""
    return {flag.name: _apply(flag) for flag in FLAGS if flag.phase == phase}


def apply_early_flags() -> Dict[str, Optional[str]]:
    """导入期开关（必须早于任何业务模块 import）。"""
    return apply_phase("import")


def apply_test_flags() -> Dict[str, Optional[str]]:
    """pytest_configure() 期开关。"""
    return apply_phase("configure")


def snapshot() -> Dict[str, Optional[str]]:
    """当前进程内所有相关开关的取值（含未设置的 None），供基线 JSON 使用。"""
    data: Dict[str, Optional[str]] = {flag.name: os.environ.get(flag.name) for flag in FLAGS}
    data.update({name: os.environ.get(name) for name in _OBSERVED_ONLY})
    return data


def registry() -> List[dict]:
    """返回注册表本身（声明 + 当前值），供诊断/文档生成使用。"""
    current = snapshot()
    return [
        {
            "name": flag.name,
            "value": flag.value,
            "phase": flag.phase,
            "mode": flag.mode,
            "purpose": flag.purpose,
            "owner": flag.owner,
            "condition": (
                f"{flag.condition_env}={flag.condition_value}"
                if flag.mode == "unless_env"
                else ""
            ),
            "evidence": flag.evidence,
            "current": current.get(flag.name),
        }
        for flag in FLAGS
    ]


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="测试态环境开关注册表")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出注册表")
    args = parser.parse_args()

    rows = registry()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"{'NAME':<32}{'VALUE':<8}{'PHASE':<11}{'MODE':<12}CURRENT")
    for row in rows:
        print(
            f"{row['name']:<32}{row['value']:<8}{row['phase']:<11}"
            f"{row['mode']:<12}{row['current']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())