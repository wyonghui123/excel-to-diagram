# -*- coding: utf-8 -*-
"""
[V007.52] Materialization Registry — 审计 updated_at 物化策略 SSOT

读取 `meta/schemas/_audit_materialization.yaml`，提供：
- 按 table_name 查询 strategy
- 统一的 get_updated_at(table_name, object_id) helper
- 缓存物化目标表清单（供 v007_51 迁移 + AuditAsyncQueue 使用）

设计目标：
- 新表加 updated_at 时，只需在 SSOT 加一行，无需改代码
- 读取统一调用 helper，自动选最优路径
- 测试可独立验证（mock registry）

版本: v007.52
日期: 2026-07-14
"""
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import yaml

logger = logging.getLogger(__name__)


# 策略常量
STRATEGY_BUSINESS_TRIGGER = "business_trigger"     # 业务表 UPDATE 触发器
STRATEGY_AUDIT_CALLBACK = "audit_callback"         # V007.51 审计反写
STRATEGY_APPLICATION_EXPLICIT = "application_explicit"  # 应用层显式写
STRATEGY_AUDIT_DERIVED = "audit_derived"           # 无物化列，从 v_audit_all 聚合
STRATEGY_NONE = "none"                             # 不需要 updated_at

# 物化策略（可直接 SELECT column 零开销读）
MATERIALIZED_STRATEGIES = frozenset({
    STRATEGY_BUSINESS_TRIGGER,
    STRATEGY_AUDIT_CALLBACK,
    STRATEGY_APPLICATION_EXPLICIT,
})


class MaterializationRegistry:
    """审计 updated_at 物化策略注册表（线程安全单例）"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._by_table: Dict[str, Dict[str, Any]] = {}
        self._by_object_type: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    @classmethod
    def instance(cls) -> "MaterializationRegistry":
        """获取单例（双重检查锁）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._load_default()
        return cls._instance

    @classmethod
    def reset(cls):
        """测试时重置单例"""
        with cls._lock:
            cls._instance = None

    def _load_default(self):
        """从默认 SSOT 文件加载"""
        ssot_path = Path(__file__).parent.parent / "schemas" / "_audit_materialization.yaml"
        if ssot_path.exists():
            self.load_from_file(str(ssot_path))
        else:
            logger.warning("[MaterializationRegistry] SSOT file not found: %s", ssot_path)

    def load_from_file(self, file_path: str):
        """从 YAML 文件加载"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return

            entries = data.get("audit_materialization", [])
            for entry in entries:
                table_name = entry.get("name")
                if not table_name:
                    continue
                self._by_table[table_name] = entry
                obj_type = entry.get("object_type")
                if obj_type:
                    self._by_object_type[obj_type] = entry
            self._loaded = True
            logger.info(
                "[MaterializationRegistry] Loaded %d entries (%d materialized, %d audit_derived, %d none)",
                len(self._by_table),
                sum(1 for e in self._by_table.values() if e.get("strategy") in MATERIALIZED_STRATEGIES),
                sum(1 for e in self._by_table.values() if e.get("strategy") == STRATEGY_AUDIT_DERIVED),
                sum(1 for e in self._by_table.values() if e.get("strategy") == STRATEGY_NONE),
            )
        except Exception as e:
            logger.error("[MaterializationRegistry] Failed to load %s: %s", file_path, e)

    def get(self, table_name: str) -> Optional[Dict[str, Any]]:
        """按表名获取物化策略 entry"""
        return self._by_table.get(table_name)

    def get_by_object_type(self, object_type: str) -> Optional[Dict[str, Any]]:
        """按 object_type 获取策略"""
        return self._by_object_type.get(object_type)

    def get_strategy(self, table_name: str) -> Optional[str]:
        """获取表的 strategy（如 'audit_callback'），未注册返回 None"""
        entry = self.get(table_name)
        return entry.get("strategy") if entry else None

    def is_materialized(self, table_name: str) -> bool:
        """表是否有物化 updated_at 列（直接 SELECT 零开销读）"""
        strategy = self.get_strategy(table_name)
        return strategy in MATERIALIZED_STRATEGIES if strategy else False

    def needs_audit_derived(self, table_name: str) -> bool:
        """表是否需要从 audit_logs 派生（无物化列）"""
        return self.get_strategy(table_name) == STRATEGY_AUDIT_DERIVED

    def has_updated_at(self, table_name: str) -> bool:
        """表是否应该有 updated_at 列（任何物化策略或 none 都不返回 False，
        只返回 True 表示可直接读取）

        严格语义：
        - materialized (business_trigger / audit_callback / application_explicit): True
        - audit_derived: False（无列）
        - none: False（无列）
        - 未注册: False（默认无）
        """
        return self.is_materialized(table_name)

    def get_materialized_tables(self) -> List[str]:
        """获取所有有物化列的表名（V007.51 迁移 + AuditAsyncQueue 用）"""
        return [
            name for name, entry in self._by_table.items()
            if entry.get("strategy") in MATERIALIZED_STRATEGIES
        ]

    def get_audit_callback_tables(self) -> List[Tuple[str, str]]:
        """获取所有 audit_callback 策略的 (table_name, object_type) 元组"""
        return [
            (entry["name"], entry["object_type"])
            for entry in self._by_table.values()
            if entry.get("strategy") == STRATEGY_AUDIT_CALLBACK
            and entry.get("object_type")
        ]

    def get_all_entries(self) -> Dict[str, Dict[str, Any]]:
        """获取全部 entries（调试用）"""
        return dict(self._by_table)


# 全局单例便捷访问
def get_registry() -> MaterializationRegistry:
    """获取注册表单例"""
    return MaterializationRegistry.instance()


# ─────────────────────────────────────────────────────────────
# 统一读取接口（V007.52 SSOT）
# ─────────────────────────────────────────────────────────────
def get_updated_at(
    ds,
    table_name: str,
    object_id: Any,
    object_type: Optional[str] = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """统一的 updated_at 读取入口（V007.52 SSOT）

    根据 SSOT 中注册的 strategy 自动选择最优路径：
    - materialized (business_trigger / audit_callback / application_explicit):
        直接 SELECT table.updated_at
    - audit_derived:
        从 v_audit_all 聚合 MAX(created_at) WHERE action='UPDATE'
    - none / 未注册:
        返回 fallback（默认 None）

    Args:
        ds: data source（DataSource 或 sqlite3.Connection）
        table_name: 业务表名（必须经过 validate_table_name 校验）
        object_id: 对象 ID
        object_type: 审计对象类型（audit_derived 时需要）
        fallback: 兜底值（无数据时返回）

    Returns:
        ISO 字符串 或 fallback
    """
    from meta.core.table_name_validator import validate_table_name
    table_name = validate_table_name(table_name)

    registry = get_registry()
    strategy = registry.get_strategy(table_name)

    # 1. Materialized: 直接读列
    if registry.is_materialized(table_name):
        try:
            row = ds.execute(
                f"SELECT updated_at FROM {table_name} WHERE id = ? LIMIT 1",
                (object_id,),
            ).fetchone()
            if row:
                if isinstance(row, dict):
                    return row.get("updated_at") or fallback
                # tuple: (updated_at,)
                return row[0] or fallback
            return fallback
        except Exception as e:
            logger.warning(
                "[get_updated_at] SELECT failed for %s/%s: %s",
                table_name, object_id, e,
            )
            return fallback

    # 2. audit_derived: 从 v_audit_all 聚合
    if strategy == STRATEGY_AUDIT_DERIVED:
        if not object_type:
            # 没传 object_type 时尝试从 registry 推断
            entry = registry.get(table_name)
            object_type = entry.get("object_type") if entry else None
        if not object_type:
            return fallback
        try:
            row = ds.execute(
                "SELECT MAX(created_at) FROM v_audit_all "
                "WHERE object_type = ? AND object_id = ? AND action = 'UPDATE'",
                (object_type, str(object_id)),
            ).fetchone()
            # 注意: MAX() 聚合即使无匹配行也返回一行 (None,)，必须判空再 fallback
            if row:
                value = row[0] if isinstance(row, tuple) else row.get("MAX(created_at)")
                return value or fallback
            return fallback
        except Exception as e:
            logger.warning(
                "[get_updated_at] audit_derived failed for %s/%s: %s",
                table_name, object_id, e,
            )
            return fallback

    # 3. none / 未注册：返回 fallback
    return fallback