# -*- coding: utf-8 -*-
"""[单据流 Phase 1] DOC_FLOW 边表 + 消耗视图的统一 schema 定义

职责:
- 平台提供**唯一**的边表元数据定义（BO/MetaObject 形式，spec §3.2"元数据驱动，
  非 migration 裸建"）
- 应用在 app.yaml 声明 `doc_flow: enabled` 后，由 app_registry._prepare_doc_flow
  在**该应用业务表所在的库**内建表（物理分散、结构统一，spec §12/§13.2）

设计要点（spec 2026-09-29-doc-flow-phase1-spec.md §4）:
- 17 列定稿（主文档 §3.0，VBFA 对标）+ Phase 0 预留 3 列（跨实例字段）
- 幂等键 = 7 元组唯一索引（同源同规则同目标不可重复派生，重放安全）
- 边是事实流水：append-only，无通用写 Action（唯一写入口 = derive 引擎）
- 消耗视图 v_doc_flow_consumed_qty：按 (源行, 池) 聚合已消耗量。
  **不做 open_qty 通用视图**——源行数量在异构业务表里，无法通用 JOIN；
  未结量 = 源行数量字段值 − consumed_qty（由使用方/引擎相减，spec §7）。

对应方案: docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md §3.0
          docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md §4 / §7
"""
from __future__ import annotations

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject, ObjectType,
)

# ─────────────────────────────────────────────────────────────────────────────
# 字段定义（§3.0 定稿 17 列 + Phase 0 预留 3 列）
# ─────────────────────────────────────────────────────────────────────────────

def _f(fid: str, ftype: FieldType, *, required: bool = False,
       default=None, description: str = "") -> MetaField:
    return MetaField(
        id=fid, name=fid, field_type=ftype, db_column=fid,
        required=required, default=default, description=description,
    )


DOC_FLOW_EDGE_ID = "doc_flow_edge"
DOC_FLOW_EDGE_TABLE = "doc_flow_edges"
DOC_FLOW_CONSUMED_VIEW = "v_doc_flow_consumed_qty"


def _build_edge_meta() -> MetaObject:
    """构造边表 MetaObject（每次调用返回新实例，避免共享可变状态）。"""
    fields = [
        _f("id", FieldType.STRING, required=True,
           description="边 ID（uuid4 hex）"),
        _f("source_bo", FieldType.STRING, required=True,
           description="源业务对象类型（对标 VBFA.VBTYP_V）"),
        _f("source_id", FieldType.STRING, required=True,
           description="源对象 ID（对标 VBFA.VBELV）"),
        _f("source_item", FieldType.STRING, default="",
           description="源对象行项目（对标 VBFA.POSNV；头级派生为空串）"),
        _f("target_bo", FieldType.STRING, required=True,
           description="目标业务对象类型（对标 VBFA.VBTYP_N）"),
        _f("target_id", FieldType.STRING, required=True,
           description="目标对象 ID（对标 VBFA.VBELN）"),
        _f("target_item", FieldType.STRING, default="",
           description="目标对象行项目（对标 VBFA.POSNN）"),
        _f("quantity", FieldType.FLOAT, required=True,
           description="源行侧消耗量（本边导致源行被消耗多少，≥0；对标 RFMNG）"),
        _f("amount", FieldType.FLOAT, default=0,
           description="源行侧消耗金额（对标 RFWRT）"),
        _f("currency", FieldType.STRING, default="",
           description="金额币种（对标 WAERS）"),
        _f("unit", FieldType.STRING, default="",
           description="数量单位（对标 MEINS）"),
        _f("quantity_sign", FieldType.STRING, required=True, default="normal",
           description="normal=正向 / red=红字（Phase 1 恒 normal，Phase 2 启用红字）"),
        _f("rule_id", FieldType.STRING, required=True,
           description="复制规则 ID（对标 Copy Control 变体）"),
        _f("derived_at", FieldType.DATETIME,
           description="派生时间（对标 ERDAT，引擎写入 ISO 字符串）"),
        _f("derived_by", FieldType.STRING, default="",
           description="派生执行者（对标 ERNAM）"),
        _f("status", FieldType.STRING, required=True, default="active",
           description="active / reversed（Phase 2 起冲销引擎维护）"),
        _f("pool", FieldType.STRING, required=True, default="default",
           description="消耗池（§6.5：同池规则共享上限校验，异池各自独立）"),
        # Phase 0 预留（跨实例字段，Phase 1 恒空串）
        _f("source_instance_id", FieldType.STRING, default="",
           description="预留：源实例 ID（跨实例派生，Phase 3 启用）"),
        _f("target_instance_id", FieldType.STRING, default="",
           description="预留：目标实例 ID（跨实例派生，Phase 3 启用）"),
        _f("derive_key", FieldType.STRING, default="",
           description="预留：业务幂等键（调用方自定义去重维度，Phase 3 启用）"),
    ]

    indexes = [
        MetaIndex(
            fields=["source_bo", "source_id", "source_item",
                    "target_bo", "target_id", "target_item", "rule_id"],
            db_columns=["source_bo", "source_id", "source_item",
                        "target_bo", "target_id", "target_item", "rule_id"],
            name="uq_doc_flow_idem", unique=True,
            source=IndexSource.SCHEMA,
            description="7 元组幂等键（§3.0）：同源同规则同目标不可重复派生",
        ),
        MetaIndex(
            fields=["source_bo", "source_id", "status"],
            db_columns=["source_bo", "source_id", "status"],
            name="idx_doc_flow_source", source=IndexSource.SCHEMA,
            description="源侧消耗聚合（Σ 校验 / 消耗视图走此索引）",
        ),
        MetaIndex(
            fields=["target_bo", "target_id", "status"],
            db_columns=["target_bo", "target_id", "status"],
            name="idx_doc_flow_target", source=IndexSource.SCHEMA,
            description="目标侧追溯（查目标单由哪些源派生而来）",
        ),
    ]

    return MetaObject(
        id=DOC_FLOW_EDGE_ID,
        name="单据流边",
        table_name=DOC_FLOW_EDGE_TABLE,
        description="单据流派生边（事实流水，append-only；唯一写入口 = derive 引擎）",
        fields=fields,
        indexes=indexes,
    )


def _build_consumed_view_meta() -> MetaObject:
    """构造消耗视图 MetaObject。

    按池分组（§3.4 v1.4 多池修订：异池消耗不串扰扣减）。
    红字分支（quantity_sign='red'）公式一次写对，Phase 2 激活——Phase 1
    恒 normal，等价于 Σ(quantity WHERE active)。
    """
    sql = (
        "SELECT source_bo, source_id, source_item, pool, "
        "SUM(CASE WHEN status='active' AND quantity_sign='normal' "
        "         THEN quantity ELSE 0 END) "
        "- SUM(CASE WHEN status='active' AND quantity_sign='red' "
        "         THEN quantity ELSE 0 END) AS consumed_qty "
        "FROM doc_flow_edges "
        "GROUP BY source_bo, source_id, source_item, pool"
    )
    return MetaObject(
        id="doc_flow_consumed_view",
        name="单据流已消耗量视图",
        table_name=DOC_FLOW_CONSUMED_VIEW,
        description="按 (源行, 消耗池) 聚合的已消耗量；未结量 = 源行数量 − consumed_qty",
        object_type=ObjectType.VIEW,
        view_definition=sql,
    )


def ensure_doc_flow_edge_tables(data_source) -> int:
    """在指定库内建边表 + 索引 + 消耗视图（幂等，启动期调用）。

    走 sync_schema_from_meta（SchemaMigrator）：表存在则跳过、缺列则补、
    索引 CREATE INDEX IF NOT EXISTS —— 与应用 BO 补建表同一机制。

    边表是**平台机制表**（非业务 BO，不进 BO registry），故显式登记进
    表名安全白名单（table_name_validator），使引擎的边写路径通过校验。

    Returns:
        处理的元数据对象数（恒 2：边表 + 视图）。
    """
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(DOC_FLOW_EDGE_TABLE)
    register_table_name(DOC_FLOW_CONSUMED_VIEW)
    return sync_schema_from_meta(
        data_source, [_build_edge_meta(), _build_consumed_view_meta()]
    )


def edge_table_exists(data_source) -> bool:
    """指定库内是否已存在边表（legacy 回归验收用：未启用实例应返回 False）。"""
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (DOC_FLOW_EDGE_TABLE,),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库不可读视为不存在
        return False
    return bool(rows)
