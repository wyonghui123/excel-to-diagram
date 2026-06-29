"""Preview 服务: 聚合 architecture preview 所需的额外字段。

目前仅包含 annotation 聚合, 后续可扩展。
"""
from typing import List, Dict
import sqlite3


def aggregate_annotations_for_targets(
    target_type: str,
    target_ids: List[int],
    db_connection: sqlite3.Connection,
) -> Dict[int, Dict[str, str]]:
    """聚合指定对象类型的 annotation 内容。

    Args:
        target_type: 目标类型 (business_object/relationship/sub_domain/service_module/domain)
        target_ids: 目标 ID 列表
        db_connection: SQLite 连接

    Returns:
        {target_id: {"content": "|||分隔的多条内容|||", "category": "|||分隔的多类别|||"}}

    主线不受影响:
    - 输入 target_ids 为空时直接返回 {}
    - 无 annotation 的 target_id 返回 {"content": "", "category": ""}
    - LEFT JOIN 不会影响主表行数
    - target_type 不匹配返回空聚合
    """
    if not target_ids:
        return {}

    # 构建 IN 子句占位符
    placeholders = ",".join("?" * len(target_ids))

    # LEFT JOIN annotations 按 target_id 聚合, 用 ||| 作为多值分隔符
    query = f"""
        SELECT
            target_id,
            GROUP_CONCAT(content, '|||') AS contents,
            GROUP_CONCAT(category, '|||') AS categories
        FROM annotations
        WHERE target_type = ?
          AND target_id IN ({placeholders})
        GROUP BY target_id
    """

    cursor = db_connection.execute(query, [target_type, *target_ids])
    rows = cursor.fetchall()

    # 初始化所有 target_id 为空 (向后兼容: 调用方无需检查字段是否存在)
    result: Dict[int, Dict[str, str]] = {
        tid: {"content": "", "category": ""} for tid in target_ids
    }

    # 填入实际聚合结果
    for target_id, contents, categories in rows:
        result[target_id] = {
            "content": contents or "",
            "category": categories or "",
        }

    return result