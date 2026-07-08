# -*- coding: utf-8 -*-
"""
Subflow Template Store (v3.7)
================================

服务端命名 subflow 模板存储:
- 注册: PUT /_subflow_template/<name>
- 列出: GET /_subflow_template
- 删除: DELETE /_subflow_template/<name>
- 调用: POST /_chain with {"template": "name", "params": {...}}

存储: subflow_templates 表 (新建) + 内存缓存
"""
import json
import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# [V007.40 BUG-FIX] 统一直接连接 helper
# 背景: subflow_template_store.py 4 处 sqlite3.connect() 都没有 timeout, 撞
#       lock / disk I/O error 时直接 5s 抛错, template CRUD 失败.
# 修法: 集中到 _safe_connect() helper, 统一加 timeout=30.0 + check_same_thread=False
#       + PRAGMA busy_timeout=30000, 跟 sql_connection_pool 一致.
def _safe_connect(db_path: str) -> sqlite3.Connection:
    """[V007.40] 统一的 sqlite3 直接连接 helper"""
    conn = sqlite3.connect(
        db_path,
        timeout=30.0,
        check_same_thread=False,
    )
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


class SubflowTemplateStore:
    _cache: Dict[str, List[Dict[str, Any]]] = {}
    _cache_meta: Dict[str, Dict[str, Any]] = {}  # name -> {description, created_at, ...}

    @staticmethod
    def _get_db_path() -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )

    @classmethod
    def _ensure_table(cls):
        """确保 subflow_templates 表存在"""
        try:
            # [V007.40 BUG-FIX] 用 _safe_connect() 统一加 timeout
            conn = _safe_connect(cls._get_db_path())
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subflow_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    steps_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER,
                    is_active INTEGER DEFAULT 1
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.exception(f"[TemplateStore] ensure_table failed: {e}")

    @classmethod
    def _load_cache(cls):
        """从 DB 加载到内存"""
        cls._ensure_table()
        try:
            # [V007.40 BUG-FIX] 用 _safe_connect() 统一加 timeout
            conn = _safe_connect(cls._get_db_path())
            rows = conn.execute(
                "SELECT name, description, steps_json, created_at FROM subflow_templates WHERE is_active=1"
            ).fetchall()
            conn.close()
            cls._cache = {}
            cls._cache_meta = {}
            for r in rows:
                try:
                    cls._cache[r[0]] = json.loads(r[2])
                    cls._cache_meta[r[0]] = {
                        'description': r[1] or '',
                        'created_at': r[3] or '',
                    }
                except Exception as e:
                    logger.warning(f"[TemplateStore] parse {r[0]} failed: {e}")
        except Exception as e:
            logger.exception(f"[TemplateStore] _load_cache failed: {e}")

    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        """列出所有模板"""
        with _lock:
            if not cls._cache:
                cls._load_cache()
            return [
                {'name': name, **meta, 'step_count': len(cls._cache.get(name, []))}
                for name, meta in cls._cache_meta.items()
            ]

    @classmethod
    def get(cls, name: str) -> Optional[List[Dict[str, Any]]]:
        """获取模板步骤"""
        with _lock:
            if not cls._cache:
                cls._load_cache()
            return cls._cache.get(name)

    @classmethod
    def set(cls, name: str, steps: List[Dict[str, Any]], description: str = '',
           created_by: Optional[int] = None) -> Dict[str, Any]:
        """创建/更新模板"""
        with _lock:
            if not cls._cache:
                cls._load_cache()
            steps_json = json.dumps(steps, ensure_ascii=False)

            try:
                cls._ensure_table()
                # [V007.40 BUG-FIX] 用 _safe_connect() 统一加 timeout
                conn = _safe_connect(cls._get_db_path())
                # 存在则更新, 不存在则插入
                cursor = conn.execute(
                    "SELECT id FROM subflow_templates WHERE name = ?", [name]
                )
                if cursor.fetchone():
                    conn.execute(
                        """UPDATE subflow_templates
                           SET steps_json = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE name = ?""",
                        [steps_json, description, name]
                    )
                    op = 'updated'
                else:
                    conn.execute(
                        """INSERT INTO subflow_templates
                           (name, description, steps_json, created_by) VALUES (?, ?, ?, ?)""",
                        [name, description, steps_json, created_by]
                    )
                    op = 'created'
                conn.commit()
                conn.close()

                # 更新缓存
                cls._cache[name] = steps
                cls._cache_meta[name] = {
                    'description': description,
                    'created_at': '',
                }
                return {'success': True, 'message': f'模板 {op}成功', 'operation': op}
            except Exception as e:
                logger.exception(f"[TemplateStore] set {name} failed: {e}")
                return {'success': False, 'message': f'保存失败: {e}'}

    @classmethod
    def delete(cls, name: str) -> Dict[str, Any]:
        """删除模板"""
        with _lock:
            try:
                cls._ensure_table()
                # [V007.40 BUG-FIX] 用 _safe_connect() 统一加 timeout
                conn = _safe_connect(cls._get_db_path())
                cursor = conn.execute("SELECT id FROM subflow_templates WHERE name = ?", [name])
                if not cursor.fetchone():
                    conn.close()
                    return {'success': False, 'message': f'模板 {name} 不存在'}

                conn.execute("DELETE FROM subflow_templates WHERE name = ?", [name])
                conn.commit()
                conn.close()

                cls._cache.pop(name, None)
                cls._cache_meta.pop(name, None)
                return {'success': True, 'message': f'模板 {name} 已删除'}
            except Exception as e:
                logger.exception(f"[TemplateStore] delete {name} failed: {e}")
                return {'success': False, 'message': f'删除失败: {e}'}

    @classmethod
    def render_template(cls, name: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        渲染模板 (params 替换占位符 {{param_name}})

        Returns:
            渲染后的 steps 列表
        """
        template_steps = cls.get(name)
        if not template_steps:
            return []

        def _replace_placeholder(obj):
            if isinstance(obj, str):
                for k, v in params.items():
                    obj = obj.replace('{{' + k + '}}', str(v))
                return obj
            elif isinstance(obj, dict):
                return {k: _replace_placeholder(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_replace_placeholder(item) for item in obj]
            return obj

        return [_replace_placeholder(step) for step in template_steps]
