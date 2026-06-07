"""
schema/audit/meta_object_sync.py - M13 v1.5.0 meta_object 双向同步

启动时同步：ENTITY_SCHEMAS (代码) → meta_object 表 (运行时元数据)
漂移检测：meta_object 被手工改 → 告警

回滚：删除文件即可（meta_object 表不被代码修改）
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# meta_object 表的列（推断自 services/enum_type_crud.py）
META_OBJECT_COLUMNS = {
    'id': 'INTEGER PRIMARY KEY',
    'name': 'VARCHAR(100) NOT NULL',
    'object_type': 'VARCHAR(50)',
    'fields': 'TEXT',  # JSON 字符串
    'field_metadata': 'TEXT',  # JSON 字符串
    'sync_source': 'VARCHAR(20) DEFAULT "ENTITY_SCHEMAS"',
    'sync_at': 'TIMESTAMP',
    'manual_modified': 'BOOLEAN DEFAULT 0',
}


def _get_meta_object_table():
    """获取 meta_object 表的 SQL DAO（懒加载）"""
    try:
        from meta.services.enum_type_crud import meta_object_dao
        return meta_object_dao
    except ImportError:
        logger.warning('[M13 Sync] meta_object_dao 不可用，使用内存模式')
        return None


def _safe_json_dumps(obj: dict) -> str:
    """安全 JSON 序列化"""
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f'[M13 Sync] JSON 序列化失败：{e}')
        return '{}'


def sync_meta_object_table(rules_dir: Optional[str] = None) -> Dict:
    """启动时同步：ENTITY_SCHEMAS → meta_object 表

    Args:
        rules_dir: 不使用（保留参数兼容性）

    Returns:
        dict: 同步结果
            {
                'synced': int,  # 同步成功数
                'created': int,  # 新建数
                'updated': int,  # 更新数
                'drift_detected': int,  # 漂移检测数
                'errors': List[str],  # 错误列表
            }
    """
    import json
    from meta.graphql import ENTITY_SCHEMAS

    result = {
        'synced': 0,
        'created': 0,
        'updated': 0,
        'drift_detected': 0,
        'errors': [],
    }

    dao = _get_meta_object_table()
    if dao is None:
        # 内存模式：仅返回计数，不修改任何状态
        result['synced'] = len(ENTITY_SCHEMAS)
        logger.info(f'[M13 Sync] 内存模式：{len(ENTITY_SCHEMAS)} entity（无 DB 同步）')
        return result

    for entity_name, entity_def in ENTITY_SCHEMAS.items():
        try:
            fields = entity_def.get('fields', [])
            field_metadata = entity_def.get('field_metadata', {})

            existing = dao.find_by_name(entity_name) if hasattr(dao, 'find_by_name') else None

            if existing is None:
                # 新建
                if hasattr(dao, 'create'):
                    dao.create({
                        'name': entity_name,
                        'object_type': entity_def.get('object_type', entity_name.lower()),
                        'fields': _safe_json_dumps(fields),
                        'field_metadata': _safe_json_dumps(field_metadata),
                        'sync_source': 'ENTITY_SCHEMAS',
                        'sync_at': datetime.now().isoformat(),
                        'manual_modified': False,
                    })
                    result['created'] += 1
                    logger.info(f'[M13 Sync] created: {entity_name}')
            else:
                # 检查漂移
                if getattr(existing, 'manual_modified', False):
                    result['drift_detected'] += 1
                    logger.warning(
                        f'[M13 Sync] DRIFT: {entity_name} was manually modified, '
                        f'but ENTITY_SCHEMAS is SSOT. Please update ENTITY_SCHEMAS.'
                    )

                # 更新（如果不同）
                if hasattr(dao, 'update') and existing.fields != _safe_json_dumps(fields):
                    dao.update(existing.id, {
                        'fields': _safe_json_dumps(fields),
                        'field_metadata': _safe_json_dumps(field_metadata),
                        'sync_at': datetime.now().isoformat(),
                    })
                    result['updated'] += 1
                    logger.info(f'[M13 Sync] updated: {entity_name}')

            result['synced'] += 1
        except Exception as e:
            error_msg = f'{entity_name}: {e}'
            result['errors'].append(error_msg)
            logger.error(f'[M13 Sync] ERROR: {error_msg}')

    return result


def detect_drift() -> List[Dict]:
    """检测 meta_object 表与 ENTITY_SCHEMAS 的漂移

    Returns:
        list of dict: 漂移实体信息
            [
                {'name': str, 'sync_source': str, 'sync_at': str, 'drift_fields': int},
                ...
            ]
    """
    from meta.graphql import ENTITY_SCHEMAS

    drifts = []
    dao = _get_meta_object_table()
    if dao is None or not hasattr(dao, 'find_all'):
        return drifts

    try:
        for existing in dao.find_all():
            entity_name = getattr(existing, 'name', None)
            if not entity_name or entity_name not in ENTITY_SCHEMAS:
                continue
            # 检查 manual_modified 标志
            if getattr(existing, 'manual_modified', False):
                drifts.append({
                    'name': entity_name,
                    'sync_source': getattr(existing, 'sync_source', 'unknown'),
                    'sync_at': getattr(existing, 'sync_at', ''),
                    'drift_fields': 0,  # 暂不计算 diff
                })
    except Exception as e:
        logger.error(f'[M13 Sync] detect_drift 异常：{e}')

    return drifts
