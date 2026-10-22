# -*- coding: utf-8 -*-
"""[2026-10-20] org → party 内部表示镜像（判据 = 我方主体职能 BU/LE）

背景:
  party 轴（parties 表）承载"我方"内部主体表示 —— source='org' 的行即内部表示，
  读面由 party_internal 视图（谓词 source='org'）给出；party_relation.party1_id
  （我方侧）引用的正是这些内部行。
  但此前全库**无任何写入路径**产生 source='org' 行 ⇒ party_internal 恒 0 行 ⇒
  我方侧候选为空、入口不可用。org 侧 schema 三层（视图谓词 / 1:1 部分唯一索引 /
  org 维度绑定）早已就位，缺的只有写入侧。

决策（PM 2026-10-20 拍板，即 F1 §9.1 "方案 B" 的收窄版）:
  只对**可作为我方主体**的 org 建表示 —— 判据 = 具备我方主体职能（BU/LE），而**不是全部 org**。
  依据: 全库 64 个 org 里 63 个是 department（部门不是往来主体、不是开票/发货/采购组织），
  仅 1 个（id=252）是 company 且具备 legal_entity 职能；蓝图口径为"我方侧用 org
  （BU/LE 职能）表达"。
  判据取「职能」而非 org_type: 职能可经 OrgFunctionService 增挂，而 org_type 是单一枚举；
  后续放宽（BU 级 / 内部交易）只需调整职能数据，不需改本模块。
  [2026-10-21 实施] 判据由 LEGAL_ENTITY_FUNCTION 放宽为 SUBJECT_FUNCTIONS
  （legal_entity + management_unit），与 party_internal 视图谓词同步；
  这样 party1_id 能选到 BU 而 le_org_id 仍只到法人，两字段才在业务上可分。

不删除原则:
  org 失去**全部**主体职能（BU/LE）时**不删**已建 party 行。理由: party_relations.party1_id /
  party2_id 是指向 parties.id 的真外键，删除会破坏既有关系引用；且内部表示一旦被引用
  即成为历史事实，只能停用不能抹除。

幂等:
  sync_party_for_org 先按 (source='org', org_id) 查存量 → 有则仅在有差异时 UPDATE，
  无则 INSERT；重复调用不新增行。backfill 依赖同一幂等性。

触发入口（三处，缺一会漏）:
  1. OrgFunctionService.add_function —— 职能变更走 meta/api/org_function_api.py
     **直连服务、绕过 CRUD 管线**，故必须在服务内挂钩。remove_function 无需挂钩:
     失去 legal_entity 职能按「不删除原则」不抹除已有表示。
  2. OrgPartyMirrorInterceptor（priority=94）—— 覆盖 org 的更名 / 状态变更等 CRUD。
  3. v096 回填迁移 —— 覆盖本机制落地前已存在的 LE org。
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LEGAL_ENTITY_FUNCTION = 'legal_entity'

# [2026-10-21 放宽] 可作为「我方主体」的职能集合（BU / LE）。
#   依据模块头「蓝图口径为我方侧用 org（BU/LE 职能）表达」：
#     - legal_entity  = 法人（能签约 / 开票 / 记账）
#     - management_unit = 管理单元 / BU（法人下的业务主体，不能独立签约）
#   把 BU 收进来，party1_id（我方侧）才能选到非法的内部组织，从而与
#   le_org_id（法人域）真正分开；否则两者候选恒等，界面上看起来是重复字段。
#   不放 sales / warehouse 等运营职能：它们在 SAP 里属条款/库存粒度（KNVV、库存地点），
#   不是「往来关系的一方」。
SUBJECT_FUNCTIONS = (LEGAL_ENTITY_FUNCTION, 'management_unit')

_PARTY_SCHEMA = Path(__file__).resolve().parents[1] / 'schemas' / 'party.yaml'
_party_key_template_cache: Optional[Dict[str, Any]] = None


def _load_party_key_template() -> Dict[str, Any]:
    """读取 party 的 key_template 声明（用于生成身份主体编号）。

    直接读 yaml 而非 meta registry: 迁移脚本可脱离应用启动独立执行，
    此时 registry 未必已装配。
    """
    global _party_key_template_cache
    if _party_key_template_cache is None:
        import yaml
        with open(_PARTY_SCHEMA, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        _party_key_template_cache = data.get('key_template') or {}
    return _party_key_template_cache


class OrgPartyMirrorService:
    """org → party 内部表示镜像服务。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 基础判定 ----------

    def _table_exists(self, table_name: str) -> bool:
        """表存在性检查（不经过 ds.table_exists 的白名单校验）。

        org_functions 是直建表、未在 YAML schema 登记，走 SqliteAdapter.table_exists
        会抛 ValueError: Invalid table name ⇒ _ready() 恒 False、回填被跳过。
        故此处直接查 sqlite_master；非 SQLite 适配器不支持该查询时降级回适配器方法。
        """
        try:
            cursor = self.ds.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name = ?",
                (table_name,),
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.debug(f"[OrgPartyMirror] sqlite_master 检查失败 {table_name}: {e}")
        try:
            return bool(self.ds.table_exists(table_name))
        except Exception as e:
            logger.debug(f"[OrgPartyMirror] 表存在性检查失败 {table_name}: {e}")
            return False

    def _ready(self) -> bool:
        """三张依赖表齐备才工作（多应用库路由下某库可能没有 org 表）。"""
        return all(self._table_exists(t) for t in ('orgs', 'org_functions', 'parties'))

    def is_legal_entity(self, org_id: int) -> bool:
        """是否具备法人（legal_entity）职能 —— 法人域（org_legal_entity）口径。"""
        cursor = self.ds.execute(
            "SELECT 1 FROM org_functions WHERE org_id = ? AND function_type = ? LIMIT 1",
            (org_id, LEGAL_ENTITY_FUNCTION),
        )
        return cursor.fetchone() is not None

    def is_subject_org(self, org_id: int) -> bool:
        """是否可作为「我方主体」（BU / LE 任一职能） —— 我方侧（party_internal）口径。

        与 party_internal 视图谓词 `function_type IN (...)` 同源，二者不可分裂。
        """
        placeholders = ', '.join('?' for _ in SUBJECT_FUNCTIONS)
        cursor = self.ds.execute(
            f"SELECT 1 FROM org_functions WHERE org_id = ? "  # noqa: S608
            f"AND function_type IN ({placeholders}) LIMIT 1",
            (org_id, *SUBJECT_FUNCTIONS),
        )
        return cursor.fetchone() is not None

    # ---------- 引用检测（2026-10-20） ----------

    def find_party_references(self, org_id: int) -> List[Dict[str, Any]]:
        """列出该 org 的内部表示行当前被哪些关系行引用。

        [2026-10-20] 引用面分两类，可靠性不同，本方法只覆盖 A 类：

          A 类（DB 级 FK，可查）: party_relations.party1_id / party2_id
            —— 全库 47 个 FK 均为 ``on_delete=NO ACTION``，即**数据库不阻止**
            删掉一个仍被引用的 party 行、也不会自动置空引用列 ⇒ 悬空引用全靠
            应用层自觉避免，本方法是唯一防线，不可省略。

          B 类（结构上不可能相交，主动排除）: users.party_id / person_profiles.party_id
            —— 二者语义限定 ``party_type='person'``（person_profiles 头部注释：
            「定位: party_type='person' 的 PII 专属档案载体；与 parties 1:1」），
            而 ``source='org'`` 行恒为 ``party_type='organization'`` ⇒ 不可能相交。
            实测两列取值全为空。
            **[变更警戒]** 若将来放开人员模型、允许 person 身份挂 org，必须同步改本
            方法，否则会漏扫 ⇒ 该假设已在此登记为唯一需要复查的点。

        返回: ``[{'party_id': int, 'column': 'party1_id', 'relation_id': int}, ...]``
        """
        if not self._ready():
            return []

        cursor = self.ds.execute(
            "SELECT id FROM parties WHERE source = 'org' AND org_id = ?", (org_id,)
        )
        party_ids = [row[0] for row in cursor.fetchall()]
        if not party_ids:
            return []

        refs: List[Dict[str, Any]] = []
        for party_id in party_ids:
            for column in ('party1_id', 'party2_id'):
                cur = self.ds.execute(
                    f"SELECT id FROM party_relations WHERE {column} = ?",  # noqa: S608
                    (party_id,),
                )
                for (relation_id,) in cur.fetchall():
                    refs.append({
                        'party_id': party_id,
                        'column': column,
                        'relation_id': relation_id,
                    })
        return refs

    def handle_function_revoked(self, org_id: int) -> Optional[int]:
        """org 失去某个「我方主体」职能后的处理 —— **仅检测与记录，不删数据**。

        [2026-10-21 放宽] 判据从单一 legal_entity 放宽为 SUBJECT_FUNCTIONS（BU/LE）。
        撤销其中一个职能时先看是否仍具备其它主体职能：
          - 仍具备 → 视图谓词继续命中，无需告警；
          - 不再具备 → 该行脱离 party_internal 候选集（视图实时读职能），parties 行保留。

        [2026-10-20 决策] 本方法刻意不做物理删除，理由:

          1. 全库 FK 均为 ``on_delete=NO ACTION`` ⇒ 删除无数据库兜底，删错不可逆；
          2. 「不删除原则」（模块头）方向正确，只是原实现无差别套用在所有行上；
          3. 删除动作应等真实数据验证引用扫描准确性之后再做。

        返回: 该 org 的内部表示 party id（无则 None）
        """
        if not self._ready():
            return None

        cursor = self.ds.execute(
            "SELECT id, name FROM parties WHERE source = 'org' AND org_id = ?",
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        party_id, party_name = row[0], row[1]

        if self.is_subject_org(org_id):
            logger.info(
                f"[OrgPartyMirror] org#{org_id} 撤销了一个主体职能，但仍具备其它主体职能"
                f"（{', '.join(SUBJECT_FUNCTIONS)}）⇒ party#{party_id} ({party_name!r}) "
                f"继续出现在我方主体（party_internal）候选集中"
            )
            return party_id

        refs = self.find_party_references(org_id)
        if refs:
            detail = ', '.join(
                f"party_relations#{r['relation_id']}({r['column']})" for r in refs
            )
            logger.warning(
                f"[OrgPartyMirror] org#{org_id} 已不具备任何主体职能，"
                f"其内部表示 party#{party_id} ({party_name!r}) 被引用: {detail} "
                f"—— 按不删除原则保留（正确：该关系行是历史事实）"
            )
        else:
            logger.info(
                f"[OrgPartyMirror] org#{org_id} 已不具备任何主体职能，"
                f"其内部表示 party#{party_id} ({party_name!r}) **零引用** —— "
                f"按不删除原则保留 parties 行，但视图谓词实时读职能 ⇒ "
                f"该行已不在 party_internal 候选集中。如需清理请人工确认后处理。"
            )
        return party_id

    def find_orphan_org_functions(self) -> List[int]:
        """列出 org_id 在 orgs 表中不存在的 org_functions 行（孤儿职能行）。

        [2026-10-20 问题 E] ``org_functions`` 建表 SQL 中**没有** REFERENCES 到
        ``orgs.id``（实测确认）⇒ 删除 org 不会级联清理职能行，会留孤儿。
        且 ``backfill()`` 用 ``JOIN orgs`` 遍历 ⇒ 孤儿行被 JOIN 掉、不可见；
        若同 id 的 org 将来被重建，旧职能会「复活」。

        返回: 孤儿行的 org_id 列表（可能为空）
        """
        if not self._table_exists('org_functions') or not self._table_exists('orgs'):
            return []
        cursor = self.ds.execute(
            "SELECT DISTINCT f.org_id FROM org_functions f "
            "LEFT JOIN orgs o ON o.id = f.org_id WHERE o.id IS NULL"
        )
        return [row[0] for row in cursor.fetchall()]

    # ---------- 编号生成 ----------

    def _generate_party_code(self) -> str:
        """按 party.yaml 的 key_template（PATY-{SEQ:8}）生成编号。

        生成不出来时**抛错**而非写入空 code —— parties.code 是 required + 唯一，
        空值会让问题延后到更难排查的地方。
        """
        from meta.core.key_template_engine import (
            KeyTemplateConfig, KeyTemplateEngine, KeyTemplateParser,
        )

        raw = _load_party_key_template()
        if not raw or not raw.get('enabled'):
            raise RuntimeError('party 未启用 key_template，无法生成身份主体编号')

        config = KeyTemplateConfig.from_dict('party', raw)
        engine = KeyTemplateEngine(self.ds)
        parser = KeyTemplateParser()
        tokens = parser.parse(config.pattern)
        prefix = parser.resolve_prefix(tokens, {})
        code = engine.generate_code(
            config, {}, 'party', table_name='parties', prefix_filter=prefix,
        )
        if not code:
            raise RuntimeError('party 身份主体编号生成失败（key_template 返回空）')
        return code

    # ---------- 主入口 ----------

    def sync_party_for_org(self, org_id: int) -> Optional[int]:
        """按 org 当前状态对齐其 party 内部表示行，返回该行 id。

        - 依赖表缺失 / org 不存在 → None
        - org 不具备我方主体职能（BU/LE）→ 不动已有行（见模块头「不删除原则」），返回 None
        - 具备职能: 有存量行则同步 name/status，无则新建
        """
        if org_id is None or not self._ready():
            return None

        cursor = self.ds.execute(
            "SELECT id, name, status FROM orgs WHERE id = ?", (org_id,)
        )
        org_row = cursor.fetchone()
        if not org_row:
            return None
        org_id_, org_name, org_status = org_row[0], org_row[1], org_row[2]

        if not self.is_subject_org(org_id_):
            return None

        cursor = self.ds.execute(
            "SELECT id, name, status FROM parties WHERE source = 'org' AND org_id = ?",
            (org_id_,),
        )
        existing = cursor.fetchone()

        if existing:
            party_id, party_name, party_status = existing[0], existing[1], existing[2]
            if party_name != org_name or party_status != org_status:
                self.ds.execute(
                    "UPDATE parties SET name = ?, status = ? WHERE id = ?",
                    (org_name, org_status, party_id),
                )
                logger.info(
                    f"[OrgPartyMirror] 同步 org#{org_id_} → party#{party_id} "
                    f"(name={org_name!r}, status={org_status!r})"
                )
            return party_id

        code = self._generate_party_code()
        new_id = self.ds.insert('parties', {
            'code': code,
            'name': org_name,
            'party_type': 'organization',
            'source': 'org',
            'org_id': org_id_,
            'status': org_status,
        })
        logger.info(f"[OrgPartyMirror] 新建 org#{org_id_} 的内部表示 party#{new_id} ({code})")
        return new_id

    def backfill(self) -> int:
        """为所有具备我方主体职能（BU/LE）的 org 补齐内部表示，返回**新建**行数。

        幂等: 已有行只做同步、不计入返回值，故重复执行返回 0 且不新增行。
        """
        if not self._ready():
            logger.warning('[OrgPartyMirror] 依赖表缺失，回填跳过')
            return 0

        placeholders = ', '.join('?' for _ in SUBJECT_FUNCTIONS)
        cursor = self.ds.execute(
            "SELECT o.id FROM orgs o JOIN org_functions f ON f.org_id = o.id "
            f"WHERE f.function_type IN ({placeholders}) ORDER BY o.id",  # noqa: S608
            SUBJECT_FUNCTIONS,
        )
        org_ids = [row[0] for row in cursor.fetchall()]

        created = 0
        for org_id in org_ids:
            before = self.ds.execute(
                "SELECT id FROM parties WHERE source = 'org' AND org_id = ?", (org_id,)
            ).fetchone()
            self.sync_party_for_org(org_id)
            if not before:
                created += 1
        logger.info(f"[OrgPartyMirror] 回填完成: LE org={len(org_ids)} 个, 新建 {created} 行")
        return created
