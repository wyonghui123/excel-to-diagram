# -*- coding: utf-8 -*-
"""
Action Models — Action 强化模型 (FR-LOG-001/002)
【2026-06-05 Spec v1.0 实施】

定义：
  - ActionKind 枚举（2 种）：INSTANCE / STATIC
  - ActionOutcome 枚举（4 种）：SUCCESS / FAILURE / DENIED / RETRY
  - ActionMeta dataclass：action 元数据（kind/audit/handler/category/verb）
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class ActionKind(Enum):
    """Action 类型（FR-LOG-001 用户决策：2 种）"""
    INSTANCE = "instance"   # 绑定到具体实例（如 set_current_version on product #42）
    STATIC = "static"       # 不绑实例（如 export_all_users, batch_reset_passwords）


class ActionOutcome(Enum):
    """Action 执行结果（FR-LOG-002）"""
    SUCCESS = "success"     # 成功
    FAILURE = "failure"     # 失败（异常）
    DENIED = "denied"       # 拒绝（无权限/校验失败）
    RETRY = "retry"         # 重试中


@dataclass
class ActionMeta:
    """Action 元数据（YAML 加载或代码注册）"""
    id: str                                           # action 唯一 ID，如 'set_current_version'
    kind: ActionKind = ActionKind.INSTANCE            # FR-LOG-003
    audit: bool = True                                # FR-LOG-003: 默认自动记录
    handler: Optional[str] = None                     # handler 名（从 registry 查）
    category: str = "business"                        # business/security/operation/performance/system
    verb: str = "updated"                             # resource.verb 格式中的 verb 部分
    description: str = ""                             # 人类可读描述
    before_triggers: List[str] = field(default_factory=list)
    after_triggers: List[str] = field(default_factory=list)
    requires_object_id: bool = True                   # INSTANCE action 必须有 object_id

    @property
    def resource_verb(self) -> str:
        """完整 resource.verb 命名（对齐 Stripe）"""
        return self.verb

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict（用于 audit_log 存储）"""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "audit": self.audit,
            "category": self.category,
            "verb": self.verb,
        }


# 默认配置常量
DEFAULT_RETENTION_DAYS = 180  # FR-LOG-008: Stripe 模式 6 个月保留
SENSITIVE_FIELDS = {"password", "token", "secret", "api_key", "private_key"}  # TBD-5

# 预定义 action verb 列表（与 auditLogMeta.js L79-84 同步）
ACTION_VERBS = {
    "create", "created",
    "read", "read",
    "update", "updated",
    "delete", "deleted",
    "associate", "associated",
    "dissociate", "dissociated",
    "batch_create", "batch_update", "batch_delete",
    "export", "exported",
    "import", "imported",
    "login", "logout",
    "approve", "rejected", "submit",
}
