"""Preview 服务: 聚合 architecture preview 所需的额外字段。

目前仅包含 annotation 聚合, 后续可扩展。
"""
from typing import List, Dict
import sqlite3


def aggregate_annotations_for_targets(
    target_type: str,
    target_ids: List[int],
    db_connection: sqlite3.Connection,
) -> Dict[int, Dict[str, list]]:
    """聚合指定对象类型的 annotation 内容。

    Args:
        target_type: 目标类型 (business_object/relationship/sub_domain/service_module/domain)
        target_ids: 目标 ID 列表
        db_connection: SQLite 连接

    Returns:
        {target_id: {"contents": ["content1", "content2", ...], "categories": ["cat1", "cat2", ...]}}

    主线不受影响:
    - 输入 target_ids 为空时直接返回 {}
    - 无 annotation 的 target_id 返回 {"contents": [], "categories": []}
    - LEFT JOIN 不会影响主表行数
    - target_type 不匹配返回空聚合
    - [V_NEW 2026-06-29 v2] 返回数组而不是拼接字符串,
      前端 useAnnotation.parseAnnotationsFromData 拆分后逐条渲染
    """
    if not target_ids:
        return {}

    # 构建 IN 子句占位符
    placeholders = ",".join("?" * len(target_ids))

    # [FIX 2026-06-29 v2] 不用 GROUP_CONCAT 拼接, 直接返回每条 annotation
    # 这样前端可以逐条渲染每条 annotation, 而不是只渲染拼接后的字符串
    query = f"""
        SELECT
            target_id,
            content,
            category,
            created_at
        FROM annotations
        WHERE target_type = ?
          AND target_id IN ({placeholders})
        ORDER BY target_id, created_at
    """

    cursor = db_connection.execute(query, [target_type, *target_ids])
    rows = cursor.fetchall()

    # 初始化所有 target_id 为空数组 (向后兼容: 调用方无需检查字段是否存在)
    result: Dict[int, Dict[str, list]] = {
        tid: {"contents": [], "categories": []} for tid in target_ids
    }

    # 按 target_id 分组填入
    for target_id, content, category, created_at in rows:
        if target_id in result:
            result[target_id]["contents"].append(content or "")
            result[target_id]["categories"].append(category or "")

    return result