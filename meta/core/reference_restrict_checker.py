"""引用限制检查器（单一实现）

事实源：`MetaObject.deletion_policy.restrict_on`（「谁引用我」只在 YAML 声明一次）。

三个调用方共用本实现，不得再写第二份：
- `ActionExecutor._check_deletion_policy_restrict`（物理删除）
- `DeletionService.check_restrict_rules`（通用删除服务）
- `StateTransitionExecutor` 的 `preconditions: [reference_restrict]`（停用等转换）

独立成模块的原因：`action_executor` 与 `rule_executor` 都要用，
放进任一侧会产生循环 import（`action_executor` 已 import `rule_executor`）。

声明读取口径固定为公开属性 `meta_object.deletion_policy`（yaml_loader 同时赋了
`_deletion_policy`，二者恒等；此处不新增第三个读取入口）。
"""

import logging
from typing import Any, Dict, List, Optional

from meta.core.validation_messages import ValidationMessageRegistry

logger = logging.getLogger(__name__)


class ReferenceRestrictChecker:
    """按 `deletion_policy.restrict_on` 检查引用是否阻止动作。"""

    @staticmethod
    def check(data_source, meta_object, record_id, policy=None) -> List[str]:
        """返回违规消息列表；空列表 = 通过（`check_details` 的消息投影）。"""
        return [v['message'] for v in ReferenceRestrictChecker.check_details(
            data_source, meta_object, record_id, policy
        )]

    @staticmethod
    def check_details(data_source, meta_object, record_id, policy=None) -> List[Dict[str, Any]]:
        """返回违规明细 `[{table, foreign_key, message, count}]`；空列表 = 通过。

        Args:
            data_source: 数据源（`execute(sql, params)` 通道）
            meta_object: 被检查的 MetaObject（用于读声明与友好名称解析）
            record_id: 被检查记录的主键；为空时直接放行（记录不存在，不可能被引用）
            policy: 可选的删除策略对象（dict / dataclass）。缺省读 `meta_object.deletion_policy`

        `condition` 只做字符串拼接（与 `<foreign_key> = ?` AND 组合），
        其中的业务值由声明层负责，引擎不解释。
        """
        if record_id is None:
            return []

        if policy is None and meta_object is not None:
            policy = getattr(meta_object, 'deletion_policy', None)

        violations: List[Dict[str, Any]] = []
        for rule in _extract_rules(policy):
            table = _rule_attr(rule, 'table')
            foreign_key = _rule_attr(rule, 'foreign_key')
            if not table or not foreign_key:
                continue

            sql = "SELECT COUNT(*) FROM {0} WHERE {1} = ?".format(table, foreign_key)
            condition = _rule_attr(rule, 'condition')
            if condition:
                sql += " AND ({0})".format(condition)

            try:
                cursor = data_source.execute(sql, [record_id])
                count = _row_count(cursor.fetchone())
                if count > 0:
                    message = _rule_attr(rule, 'message')
                    violations.append({
                        'table': table,
                        'foreign_key': foreign_key,
                        'message': message or _fallback_message(table, foreign_key, count),
                        'count': count,
                    })
            except Exception as e:
                logger.warning(
                    "[ReferenceRestrictChecker] table=%s fk=%s 查询失败: %s",
                    table, foreign_key, e
                )
        return violations


def _extract_rules(policy) -> List[Any]:
    if not policy:
        return []
    if isinstance(policy, dict):
        return policy.get('restrict_on') or []
    return getattr(policy, 'restrict_on', None) or []


def _rule_attr(rule, key: str) -> Any:
    """兼容 RestrictRule dataclass 与老 dict 格式（target_object/target、fk_field/field）。"""
    if isinstance(rule, dict):
        if key == 'table':
            return rule.get('table') or rule.get('target_object') or rule.get('target')
        if key == 'foreign_key':
            return rule.get('foreign_key') or rule.get('fk_field') or rule.get('field')
        return rule.get(key)
    return getattr(rule, key, None)


def _row_count(row) -> int:
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, IndexError, KeyError):
        try:
            return int(row['cnt'])
        except Exception:
            return 0


def _fallback_message(table: str, foreign_key: str, count: int) -> str:
    """未声明 message 时回落平台消息模板，并尽量解析出友好的对象名/字段名。"""
    child_name, field_name = table, foreign_key
    try:
        from meta.core.models import registry
        for obj in registry.get_all().values():
            if getattr(obj, 'table_name', '') != table:
                continue
            child_name = obj.name or obj.id
            for f in obj.fields:
                if getattr(f, 'db_column', None) == foreign_key or f.id == foreign_key:
                    field_name = f.name or f.id
                    break
            break
    except Exception:
        pass

    return ValidationMessageRegistry.get(
        "validation.object.restrict_on_delete",
        child_name=child_name,
        field_name=field_name,
        count=count,
    )
