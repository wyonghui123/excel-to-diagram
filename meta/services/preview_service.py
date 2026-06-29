"""Preview 服务: 聚合 architecture preview 所需的额外字段。

目前仅包含 annotation 聚合, 后续可扩展。
"""
from typing import List, Dict


def aggregate_annotations_for_targets(
    target_type: str,
    target_ids: List[int],
    db_connection,
) -> Dict[int, Dict[str, str]]:
    """聚合指定对象类型的 annotation 内容。

    Args:
        target_type: 目标类型 (business_object/relationship/sub_domain/service_module/domain)
        target_ids: 目标 ID 列表
        db_connection: SQLite 连接

    Returns:
        {target_id: {"content": "|||分隔的多条内容|||", "category": "|||分隔的多类别|||"}}
    """
    # 占位实现 - Task 2 替换为真实 SQL 聚合
    return {tid: {"content": "", "category": ""} for tid in target_ids}