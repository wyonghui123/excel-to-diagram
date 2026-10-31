# -*- coding: utf-8 -*-
"""平台统一入口的回滚开关（NFR-005）。

三个开关可独立设置，每个开关取三种状态（大小写不敏感）：

- ``strict``（1 / true / yes / on / strict / enforce）—— 强制：违反统一入口约定即失败
- ``shadow``（shadow / log / warn / observe）—— 影子：只记日志，行为不变
- ``off``（0 / false / no / off / disabled / none）—— 关闭该机制（回到迁移前行为）

未设置时使用各开关的默认值；非法取值记 warning 后回落默认值。

默认值（对齐 2026-10-31 现状，见 Spec FR-001 / FR-002 / FR-005）：

- ``PLATFORM_STRICT_CONTRACT``  = shadow —— 存量 46 处 ``json_response`` 逃生口仍在，先观察
- ``PLATFORM_TX_GUARD``         = shadow —— 事务基线已达成，先观察再强制
- ``PLATFORM_PERMISSION_GATE``  = strict —— 鉴权已是现行行为；默认 shadow 会 fail-open，
  违反 NFR-001（行为兼容）。该开关用于**回滚**，显式设为 shadow / off 才放行。

环境变量在每次调用时读取（不做模块级缓存），便于测试与运行时切换。
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

STRICT = "strict"
SHADOW = "shadow"
OFF = "off"

ENV_STRICT_CONTRACT = "PLATFORM_STRICT_CONTRACT"
ENV_TX_GUARD = "PLATFORM_TX_GUARD"
ENV_PERMISSION_GATE = "PLATFORM_PERMISSION_GATE"

_STRICT_VALUES = {"1", "true", "yes", "on", "strict", "enforce"}
_SHADOW_VALUES = {"shadow", "log", "warn", "observe"}
_OFF_VALUES = {"0", "false", "no", "off", "disabled", "none"}


def parse_mode(raw: Optional[str], default: str, env_name: str = "") -> str:
    """把环境变量原始值解析成 strict / shadow / off；非法值回落 default。"""
    value = (raw or "").strip().lower()
    if not value:
        return default
    if value in _STRICT_VALUES:
        return STRICT
    if value in _SHADOW_VALUES:
        return SHADOW
    if value in _OFF_VALUES:
        return OFF
    logger.warning(
        "[platform_flags] %s 取值 %r 无法识别，回落默认 %r",
        env_name or "<env>", raw, default,
    )
    return default


def contract_mode() -> str:
    """响应契约（FR-001）的模式。"""
    return parse_mode(
        os.environ.get(ENV_STRICT_CONTRACT), SHADOW, ENV_STRICT_CONTRACT
    )


def tx_guard_mode() -> str:
    """事务边界守卫（FR-002）的模式。"""
    return parse_mode(os.environ.get(ENV_TX_GUARD), SHADOW, ENV_TX_GUARD)


def permission_gate_mode() -> str:
    """功能权限判定（FR-005）的模式。"""
    return parse_mode(
        os.environ.get(ENV_PERMISSION_GATE), STRICT, ENV_PERMISSION_GATE
    )
